#!/usr/bin/env python3
"""Search every output cell of this repository's notebooks for the publishing secrets' names.

It reads:
  - every .ipynb that git lists in the repository (every .ipynb under it, outside a git checkout);
  - every notebook signed inline in records/*.signed.json, decoded from the signed bytes
    (package.output under raw-bytes/v1);
  - each path given on the command line: a notebook, or a signed record.

In each output of each cell, every string (stream text, data, tracebacks, metadata) is searched
for TYPEDSTANDARDS_SIGNING_SEED_B64, TYPEDSTANDARDS_GITHUB_TOKEN and the fine-grained token's
prefix github_pat_. A hit names the file, the cell, the output and what was found, and never
prints the text around it. A signed record whose output is not a notebook (the Marimo app's
source) has no outputs, and is listed as such.

Exit status: 0 when nothing is found; 1 on any hit; 2 when an input cannot be read.

  python3 scripts/scan_outputs.py [--root DIR] [PATH ...]

Python 3.9 or later, standard library only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

NEEDLES = (
    "TYPEDSTANDARDS_SIGNING_SEED_B64",
    "TYPEDSTANDARDS_GITHUB_TOKEN",
    "github_pat_",
)


class Unreadable(Exception):
    pass


def strings(value: Any) -> Iterator[str]:
    """Every string in a JSON value, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def is_notebook(value: Any) -> bool:
    return isinstance(value, dict) and value.get("nbformat") == 4 and isinstance(value.get("cells"), list)


def scan_notebook(notebook: dict, label: str) -> list[str]:
    """The hits in a parsed notebook's outputs, each naming the cell and never the value."""
    hits = []
    for c, cell in enumerate(notebook["cells"]):
        if not isinstance(cell, dict):
            raise Unreadable(f"{label}: cell {c} is not an object")
        outputs = cell.get("outputs", [])
        if not isinstance(outputs, list):
            raise Unreadable(f"{label}: cell {c}'s outputs is not a list")
        for o, output in enumerate(outputs):
            found = sorted({n for s in strings(output) for n in NEEDLES if n in s})
            for needle in found:
                hits.append(f"{label}: cell {c} ({cell.get('cell_type')}), output {o}: holds {needle}")
    return hits


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Unreadable(f"{path}: cannot be read as UTF-8 JSON ({type(error).__name__})") from None


def scan_path(path: Path, root: Path) -> tuple[list[str], str]:
    """``(hits, what was scanned)`` for a notebook or a signed record."""
    label = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    document = read_json(path)
    if is_notebook(document):
        return scan_notebook(document, label), f"{label}: notebook, {len(document['cells'])} cells"
    package = document.get("package") if isinstance(document, dict) else None
    if not isinstance(package, dict):
        raise Unreadable(f"{label}: neither a notebook nor what sign prints")
    output = package.get("output")
    if not isinstance(output, str):
        return [], f"{label}: signed record, output not inline: no notebook to scan"
    try:
        inner = json.loads(output)
    except ValueError:
        inner = None
    if not is_notebook(inner):
        return [], f"{label}: signed record, inline output is not a notebook: no outputs"
    return (
        scan_notebook(inner, f"{label} (signed notebook)"),
        f"{label}: signed record, inline notebook, {len(inner['cells'])} cells",
    )


def committed_notebooks(root: Path) -> list[Path]:
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.ipynb"], cwd=root, capture_output=True, check=True
        ).stdout.decode("utf-8")
        return [root / p for p in listed.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return sorted(p for p in root.rglob("*.ipynb") if "node_modules" not in p.parts and ".git" not in p.parts)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    targets = [*committed_notebooks(root), *sorted((root / "records").glob("*.signed.json"))]
    targets += [p.resolve() for p in args.paths]
    hits: list[str] = []
    unreadable = 0
    for path in dict.fromkeys(targets):
        try:
            found, what = scan_path(path, root)
        except Unreadable as error:
            print(f"UNREADABLE {error}")
            unreadable += 1
            continue
        print(f"{'HIT' if found else 'ok '} {what}")
        hits += found
    for hit in hits:
        print(f"HIT {hit}")
    print(
        f"scan_outputs: {len(dict.fromkeys(targets))} files, {len(hits)} hits, {unreadable} unreadable "
        f"(searched for {', '.join(NEEDLES)})"
    )
    return 1 if hits else 2 if unreadable else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
