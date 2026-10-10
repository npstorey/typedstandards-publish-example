#!/usr/bin/env python3
"""The offline rehearsal: the four publishes, in the order the README gives, against a fake
GitHub API, with the template's publish job run over each commit they make.

  fnm exec --using=24 -- uv run --no-project --with typedstandards==0.2.0 --with marimo==0.25.1 \\
    python scripts/rehearse.py

What it does, in a scratch directory it makes (nothing in this repository changes):
  1. Copies this repository's committed tree (git archive HEAD) into <scratch>/site, and runs
     npm ci there.
  2. Makes a throwaway signing seed and a stand-in token in this process. Neither is printed,
     written to a file or kept: the seed reaches the CLI only through the environment of the
     calls that sign, as the README's own setup gives it. The scratch copy's host-policy.json
     names the throwaway key as its signer, and the copy starts as the setup commit left it:
     "records": [] in host.json, and no records/. Nothing else in the copy changes.
  3. Serves the scratch copy as a GitHub repository through httpx.MockTransport: the reads and
     the Git Data API writes publish makes. Every httpx client the process builds is routed to
     it, so no request leaves the machine.
  4. Runs, in order:
       a. notebooks/colab-example.ipynb with RUN = "first", cell by cell, as Colab would, with a
          stand-in google.colab (userdata.get and the get_ipynb request);
       b. notebooks/marimo_example.py as a script with --publish;
       c. notebooks/colab-example.ipynb with RUN = "rerun": the rerun, with revises=, and then
          the withdrawal of the first run's record.
  5. After the setup commit and after each commit a publish makes, writes that commit's tree
     into the scratch copy and runs the publish job's steps: typedstandards-host build into a
     fresh directory beside docs/index.html and docs/.nojekyll, verify over it, and
     node display.mjs over the index it built.
  6. Checks: the setup commit's build fails as the template README says, every later step exits
     0, records.json shows the withdrawal with its reason, each badge links to its receipt's
     verify_url, the output scanner finds nothing, and neither the seed nor the token is in any
     file of the scratch copy, in any output or in anything this process printed.

Exit status 0 when every check holds.
"""

from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from urllib.parse import unquote

import httpx
import typedstandards as ts

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "npstorey/typedstandards-publish-example"
ORIGIN_HOST = "publish-example.typedstandards.org"
SEED_VARIABLE = "TYPEDSTANDARDS_SIGNING_SEED_B64"
TOKEN_VARIABLE = "TYPEDSTANDARDS_GITHUB_TOKEN"
STAND_IN_USER = "Rehearsal account stand-in"  # what Colab's cell metadata would name

printed = io.StringIO()  # everything this script prints, for the final leak check


def say(text: str = "") -> None:
    print(text)
    printed.write(text + "\n")


def fail(text: str) -> None:
    say(f"REHEARSAL FAILED: {text}")
    sys.exit(1)


# --- the fake GitHub API ------------------------------------------------------------------------


def git_sha(kind: str, content: bytes) -> str:
    return hashlib.sha1(f"{kind} {len(content)}\0".encode() + content).hexdigest()


class FakeGitHub:
    """One repository: blobs, flat trees (path to blob id), commits, and the main branch."""

    def __init__(self, files: dict[str, bytes], token: str) -> None:
        self.token = token
        self.blobs: dict[str, bytes] = {}
        self.trees: dict[str, dict[str, str]] = {}
        self.commits: dict[str, dict] = {}
        self.log: list[str] = []
        self.landed: list[str] = []  # commit ids, in the order main moved to them
        self.served: Path | None = None  # the last tree the publish job deployed
        tree = self._tree({path: self._blob(content) for path, content in files.items()})
        self.head = self._commit("Set up this copy for publish mode (the scratch copy)", tree, [])

    def _blob(self, content: bytes) -> str:
        sha = git_sha("blob", content)
        self.blobs[sha] = content
        return sha

    def _tree(self, entries: dict[str, str]) -> str:
        sha = git_sha("tree", json.dumps(entries, sort_keys=True).encode())
        self.trees[sha] = dict(entries)
        return sha

    def _commit(self, message: str, tree: str, parents: list[str]) -> str:
        body = json.dumps({"message": message, "tree": tree, "parents": parents, "n": len(self.commits)})
        sha = git_sha("commit", body.encode())
        self.commits[sha] = {"message": message, "tree": tree, "parents": parents}
        return sha

    def files_at(self, commit: str) -> dict[str, bytes]:
        return {path: self.blobs[sha] for path, sha in self.trees[self.commits[commit]["tree"]].items()}

    def handler(self, request: httpx.Request) -> httpx.Response:
        response = self._handle(request)
        where = "" if request.url.host == "api.github.com" else f"https://{request.url.host}"
        self.log.append(f"{request.method} {where}{request.url.path.removeprefix('/repos/' + REPOSITORY)} {response.status_code}")
        return response

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == ORIGIN_HOST and request.method == "GET":
            # The site, as the last deploy left it.
            target = (self.served / request.url.path.lstrip("/")) if self.served else None
            if target is None or not target.is_file():
                return httpx.Response(404)
            return httpx.Response(200, content=target.read_bytes(), headers={"content-type": "application/json; charset=utf-8"})
        if request.url.host != "api.github.com" or not request.url.path.startswith(f"/repos/{REPOSITORY}/"):
            return httpx.Response(404, json={"message": "the rehearsal serves one repository only"})
        path = request.url.path.removeprefix(f"/repos/{REPOSITORY}")
        writes = request.method in {"POST", "PATCH"}
        if writes and request.headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401, json={"message": "Bad credentials"})
        body = json.loads(request.content) if request.content else {}
        if request.method == "GET" and path == "/git/ref/heads/main":
            return httpx.Response(200, json={"ref": "refs/heads/main", "object": {"sha": self.head, "type": "commit"}})
        if request.method == "GET" and path.startswith("/git/commits/"):
            commit = self.commits.get(path.rsplit("/", 1)[1])
            if commit is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"sha": path.rsplit("/", 1)[1], "tree": {"sha": commit["tree"]}})
        if request.method == "GET" and path.startswith("/contents/"):
            ref = request.url.params.get("ref", "main")
            commit = self.head if ref == "main" else ref
            if commit not in self.commits:
                return httpx.Response(404, json={"message": "No commit found for the ref"})
            blob = self.trees[self.commits[commit]["tree"]].get(unquote(path.removeprefix("/contents/")))
            if blob is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, content=self.blobs[blob])
        if request.method == "POST" and path == "/git/blobs":
            return httpx.Response(201, json={"sha": self._blob(base64.b64decode(body["content"]))})
        if request.method == "POST" and path == "/git/trees":
            entries = dict(self.trees[body["base_tree"]])
            for entry in body["tree"]:
                if entry.get("mode") != "100644" or entry.get("type") != "blob" or entry.get("sha") not in self.blobs:
                    return httpx.Response(422, json={"message": "bad tree entry"})
                entries[entry["path"]] = entry["sha"]
            return httpx.Response(201, json={"sha": self._tree(entries)})
        if request.method == "POST" and path == "/git/commits":
            if body.get("tree") not in self.trees or any(p not in self.commits for p in body.get("parents", [])):
                return httpx.Response(422, json={"message": "bad commit"})
            return httpx.Response(201, json={"sha": self._commit(body["message"], body["tree"], body["parents"])})
        if request.method == "PATCH" and path == "/git/refs/heads/main":
            commit = self.commits.get(body.get("sha"))
            if commit is None or body.get("force") is not False or commit["parents"] != [self.head]:
                return httpx.Response(422, json={"message": "Update is not a fast forward"})
            self.head = body["sha"]
            self.landed.append(self.head)
            return httpx.Response(200, json={"ref": "refs/heads/main", "object": {"sha": self.head}})
        return httpx.Response(404, json={"message": f"the rehearsal does not serve {request.method} {path}"})


@contextlib.contextmanager
def routed(fake: FakeGitHub):
    """Every httpx.Client built inside the block uses the fake API's transport."""
    transport = httpx.MockTransport(fake.handler)
    real = httpx.Client

    class Routed(real):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = kwargs.get("transport") or transport
            super().__init__(*args, **kwargs)

    httpx.Client = Routed  # type: ignore[misc]
    try:
        yield
    finally:
        httpx.Client = real  # type: ignore[misc]


# --- the scratch copy and the publish job -------------------------------------------------------


def run(command: list[str], cwd: Path, *, expect: int | None = 0) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    say(f"$ {' '.join(str(c) for c in command)}")
    for line in (result.stdout + result.stderr).rstrip("\n").splitlines():
        say(f"  {line}")
    say(f"  (exit {result.returncode})")
    if expect is not None and result.returncode != expect:
        fail(f"{command[:3]} exited {result.returncode}, not {expect}")
    return result


def apply(fake: FakeGitHub, commit: str, site: Path, before: dict[str, bytes]) -> dict[str, bytes]:
    files = fake.files_at(commit)
    changed = sorted(p for p, c in files.items() if before.get(p) != c)
    for path in changed:
        target = site / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[path])
    say(f"applied {commit[:12]} ({fake.commits[commit]['message']!r}): {', '.join(changed) or 'no files'}")
    return files


def publish_job(site: Path, work: Path, label: str, *, expect_build: int = 0) -> Path | None:
    """publish.yml's build job, without the upload: build, verify, display. Returns the tree it
    would deploy, or None when the build fails as expected."""
    out = work / f"site-{label}"
    out.mkdir()
    shutil.copy(site / "docs/index.html", out)
    shutil.copy(site / "docs/.nojekyll", out)
    built = run(["npx", "typedstandards-host", "build", "--out", str(out)], site, expect=None)
    if expect_build != 0:
        if built.returncode == 0:
            fail("the setup commit's build passed; the template README says it fails")
        return None
    if built.returncode != 0:
        fail(f"build failed after {label}")
    run(["npx", "typedstandards-host", "verify", "--out", str(out)], site)
    run(["node", "display.mjs", str(out / "records.json")], site)
    return out


# --- Colab, stood in for ------------------------------------------------------------------------


def colab_frontend(notebook: dict) -> dict:
    """The notebook as Colab's frontend would hold it: nbformat_minor 0, and Colab's metadata on
    the notebook and on each cell."""
    held = copy.deepcopy(notebook)
    held["nbformat_minor"] = 0
    held["metadata"]["colab"] = {"provenance": [], "authorship_tag": "STAND-IN-AUTHORSHIP-TAG"}
    for i, cell in enumerate(held["cells"]):
        cell["metadata"] = {"id": f"cell{i:02d}"}
    return held


def install_colab(frontend: dict, secrets_held: dict[str, str]) -> None:
    google = sys.modules.get("google") or types.ModuleType("google")
    if not hasattr(google, "__path__"):
        google.__path__ = []  # type: ignore[attr-defined]
    colab = types.ModuleType("google.colab")
    colab.__path__ = []  # type: ignore[attr-defined]
    userdata = types.ModuleType("google.colab.userdata")
    message = types.ModuleType("google.colab._message")

    def get(key: str) -> str:
        if key not in secrets_held:
            raise RuntimeError(f"Secret {key} does not exist.")
        return secrets_held[key]

    def blocking_request(request_type, request="", timeout_sec=5, parent=None):
        if request_type != "get_ipynb":
            return None
        return {"ipynb": copy.deepcopy(frontend)}

    userdata.get = get  # type: ignore[attr-defined]
    message.blocking_request = blocking_request  # type: ignore[attr-defined]
    colab.userdata = userdata  # type: ignore[attr-defined]
    colab._message = message  # type: ignore[attr-defined]
    google.colab = colab  # type: ignore[attr-defined]
    sys.modules.update(
        {"google": google, "google.colab": colab, "google.colab.userdata": userdata, "google.colab._message": message}
    )


def run_colab(path: Path, run_kind: str, content: Path, secrets_held: dict[str, str]) -> dict:
    """Run every code cell in order, as Run all does, in a fresh namespace; return it."""
    notebook = json.loads(path.read_text("utf-8"))
    frontend = colab_frontend(notebook)
    if run_kind == "rerun":
        cell = next(c for c in frontend["cells"] if "".join(c["source"]).startswith("# The parameters."))
        text = "".join(cell["source"])
        if text.count('RUN = "first"\n') != 1:
            fail("the parameters cell does not hold one RUN = \"first\" line")
        cell["source"] = text.replace('RUN = "first"\n', 'RUN = "rerun"\n').splitlines(True)
    install_colab(frontend, secrets_held)
    namespace: dict = {"__name__": "__main__"}
    count = 0
    cwd = os.getcwd()
    os.chdir(content)
    try:
        for i, cell in enumerate(frontend["cells"]):
            if cell["cell_type"] != "code":
                continue
            source = "".join(cell["source"])
            if source.startswith("%pip"):
                say(f"  cell {i}: {source.strip()} (typedstandards 0.2.0 is already installed here)")
                code = "pass"
            else:
                code = source
            tree = ast.parse(code)
            last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exec(compile(tree, f"<colab cell {i}>", "exec"), namespace)
                value = eval(compile(ast.Expression(last.value), f"<colab cell {i}>", "eval"), namespace) if last else None
            count += 1
            outputs = []
            if out.getvalue():
                outputs.append({"name": "stdout", "output_type": "stream", "text": out.getvalue().splitlines(True)})
            if value is not None:
                outputs.append(
                    {"data": {"text/plain": [repr(value)]}, "execution_count": count, "metadata": {}, "output_type": "execute_result"}
                )
            cell["outputs"] = outputs
            cell["execution_count"] = count
            cell["metadata"]["executionInfo"] = {"status": "ok", "user": {"displayName": STAND_IN_USER, "userId": "0"}}
            cell["metadata"]["outputId"] = f"out{i:02d}"
            for line in out.getvalue().splitlines():
                say(f"  cell {i} | {line}")
    finally:
        os.chdir(cwd)
    namespace["__frontend__"] = frontend
    return namespace


# --- the checks ---------------------------------------------------------------------------------


def badge_link(text: str) -> str:
    start = text.index("](<https://typedstandards.org/verify?url=") + 3
    return text[start : text.index(">)", start)]


def main() -> int:
    parser = argparse.ArgumentParser(description="The offline rehearsal of the four publishes.")
    parser.add_argument("--workdir", type=Path, help="the scratch directory (default: a new temporary one)")
    parser.add_argument("--worktree", action="store_true",
                        help="copy the files git lists from the working tree, not the committed tree (for editing)")
    args = parser.parse_args()
    work = (args.workdir or Path(tempfile.mkdtemp(prefix="publish-example-rehearsal-"))).resolve()
    work.mkdir(parents=True, exist_ok=True)
    site, content, local = work / "site", work / "colab-content", work / "local"
    for d in (site, content, local):
        if d.exists():
            fail(f"{d} exists: pass an empty --workdir")
        d.mkdir()

    say("== The scratch copy")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if args.worktree:
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode()
        for name in filter(None, listed.split("\0")):
            (site / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, site / name)
        say(f"the files git lists, from the working tree at {head} (--worktree), into {site}")
    else:
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(site)], input=archive, check=True)
        say(f"git archive HEAD ({head}) into {site}")
    say(f"python {sys.version.split()[0]}, typedstandards {ts.__version__} (CLI {ts.CLI_VERSION}), from {Path(ts.__file__).parent}")
    run(["node", "--version"], site)
    run(["npm", "ci", "--no-audit", "--no-fund"], site)
    run(["npm", "ls", "@typedstandards/host-core", "@typedstandards/cli"], site)

    seed = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    token = "github_pat_" + secrets.token_hex(41)
    held = {SEED_VARIABLE: seed, TOKEN_VARIABLE: token}
    probe_file = local / "key-probe.txt"
    probe_file.write_text("The throwaway key's identifier is read from this record.\n", encoding="utf-8")
    os.environ[SEED_VARIABLE] = seed
    try:
        probe = ts.sign(
            {"type": "content/analysis/v1", "producerProfile": "scripted-recomputation/publish-example",
             "captureMethod": "script-run", "prompt": "key probe", "promptVisibility": "full_text", "queries": [],
             "dataSources": [], "cost": {"model": "none"}, "skillMetadata": {}, "trace": {},
             "signer": {"bindingTier": "pseudonymous", "displayName": "typedstandards-publish-example"}},
            output_file=probe_file,
        )
    finally:
        del os.environ[SEED_VARIABLE]
    throwaway = probe["package"]["signer"]["identifier"]
    policy_path = site / "host-policy.json"
    policy = json.loads(policy_path.read_text("utf-8"))
    kept_key = policy["signer"]
    policy["signer"] = throwaway
    policy_path.write_text(json.dumps(policy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    say(f"host-policy.json signer: {kept_key} -> {throwaway} (a throwaway key, made in this process)")
    # The rehearsal starts from the setup commit's state: no records. Records this repository
    # has published since are left out of the scratch copy; the repository keeps them.
    manifest_path = site / "host.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if manifest["records"] or (site / "records").exists():
        listed = [e["name"] for e in manifest["records"]]
        manifest["records"] = []
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.rmtree(site / "records", ignore_errors=True)
        say(f"host.json: the scratch copy starts with no records (this repository lists {listed or 'none'}), "
            "and without records/")

    files = {
        p.relative_to(site).as_posix(): p.read_bytes()
        for p in sorted(site.rglob("*"))
        if p.is_file() and "node_modules" not in p.relative_to(site).parts
    }
    fake = FakeGitHub(files, token)
    say(f"the fake repository's main: {fake.head[:12]}, {len(files)} files")

    say("\n== The setup commit: publish.yml's build fails, and deploys nothing (template README, step 5)")
    publish_job(site, work, "0-setup", expect_build=1)

    receipts: dict[str, dict] = {}
    steps: list[tuple[str, str]] = []
    tree_before = fake.files_at(fake.head)

    def deploy_new_commits(label: str) -> None:
        nonlocal tree_before
        for commit in fake.landed[len(steps):]:
            steps.append((label, commit))
            say(f"\n-- publish.yml over commit {len(steps)}, from {label}")
            tree_before = apply(fake, commit, site, tree_before)
            fake.served = publish_job(site, work, f"{len(steps)}")

    with routed(fake):
        say("\n== 1. The Colab notebook, RUN = \"first\": publishes colab-example")
        fake.log.clear()
        first = run_colab(site / "notebooks/colab-example.ipynb", "first", content, held)
        say("  API: " + "; ".join(fake.log))
        receipts["colab-example"] = first["receipt"]
        first_signed = first["signed"]
        deploy_new_commits("the Colab notebook's first run")
        for v in (SEED_VARIABLE, TOKEN_VARIABLE):
            os.environ.pop(v, None)

        say("\n== 2. The Marimo app, as a script with --publish: publishes marimo-example")
        fake.log.clear()
        app_path = site / "notebooks/marimo_example.py"
        app_before = app_path.read_bytes()
        os.environ.update(held)  # as op run sets them for the process it starts
        argv = sys.argv
        out = io.StringIO()
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location("marimo_example", app_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            sys.argv = [str(app_path), "--publish"]
            with contextlib.redirect_stdout(out):
                module.app.run()
        finally:
            sys.argv = argv
            for v in (SEED_VARIABLE, TOKEN_VARIABLE):
                os.environ.pop(v, None)
        for line in out.getvalue().splitlines():
            say(f"  app | {line}")
        say("  API: " + "; ".join(fake.log))
        if app_path.read_bytes() != app_before:
            fail("the Marimo app changed its own file")
        marimo_receipt = dict(line.split(": ", 1) for line in out.getvalue().splitlines() if ": " in line)
        receipts["marimo-example"] = marimo_receipt
        deploy_new_commits("the Marimo app")

        say("\n== 3 and 4. The Colab notebook, RUN = \"rerun\": publishes colab-example-rerun with revises=, then withdraws colab-example")
        fake.log.clear()
        rerun = run_colab(site / "notebooks/colab-example.ipynb", "rerun", content, held)
        say("  API: " + "; ".join(fake.log))
        receipts["colab-example-rerun"] = rerun["receipt"]
        rerun_signed = rerun["signed"]
        for v in (SEED_VARIABLE, TOKEN_VARIABLE):
            os.environ.pop(v, None)
        deploy_new_commits("the Colab notebook's rerun")

        say("\n== Repeats: each is refused before any write")
        for kind in ("first", "rerun"):
            fake.log.clear()
            landed = len(fake.landed)
            try:
                run_colab(site / "notebooks/colab-example.ipynb", kind, content, held)
                fail(f"a repeated RUN = {kind!r} was not refused")
            except ts.PublishRefusedError as error:
                say(f"  RUN = {kind!r} again: PublishRefusedError: {error}")
            finally:
                for v in (SEED_VARIABLE, TOKEN_VARIABLE):
                    os.environ.pop(v, None)
            writes = [line for line in fake.log if line.startswith(("POST", "PATCH"))]
            say("  API: " + "; ".join(fake.log))
            if writes or len(fake.landed) != landed:
                fail(f"a repeated RUN = {kind!r} wrote {writes}")

    say("\n== The checks")
    if len(steps) != 4:
        fail(f"{len(steps)} commits landed, not 4")
    say(f"commits on main after setup: {len(steps)}")
    for n, (label, commit) in enumerate(steps, 1):
        say(f"  {n}. {fake.commits[commit]['message']}")

    index = json.loads((work / f"site-{len(steps)}" / "records.json").read_text("utf-8"))
    for record in index["records"]:
        say(f"records.json: {record['name']}: {record['status']}" + (f", withdrawn {json.dumps(record['withdrawn'])}" if "withdrawn" in record else ""))
    statuses = {r["name"]: r for r in index["records"]}
    want = {"colab-example": "withdrawn", "marimo-example": "active", "colab-example-rerun": "active"}
    if {k: v["status"] for k, v in statuses.items()} != want:
        fail(f"records.json's statuses are not {want}")
    if not statuses["colab-example"]["withdrawn"].get("reason"):
        fail("records.json's withdrawal carries no reason")

    manifest = json.loads((site / "host.json").read_text("utf-8"))
    say("host.json records: " + json.dumps(
        [{k: e[k] for k in ("name", "signed", "attestations")} for e in manifest["records"]]))

    committed_colab = json.loads((ROOT / "notebooks/colab-example.ipynb").read_text("utf-8"))
    committed_badge = badge_link("".join(committed_colab["cells"][0]["source"]))
    committed_app_badge = badge_link((ROOT / "notebooks/marimo_example.py").read_text("utf-8"))
    checks = [
        ("the committed notebook's cell 0 links to colab-example's verify_url",
         committed_badge == receipts["colab-example"]["verify_url"]),
        ("the committed Marimo app's badge links to marimo-example's verify_url",
         committed_app_badge == receipts["marimo-example"]["verify_url"]),
    ]
    for name, signed in (("colab-example", first_signed), ("colab-example-rerun", rerun_signed)):
        inner = json.loads(signed["package"]["output"])
        checks.append((f"{name}: the signed notebook's cell 0 links to its receipt's verify_url",
                       badge_link("".join(inner["cells"][0]["source"])) == receipts[name]["verify_url"]))
        text = signed["package"]["output"]
        checks.append((f"{name}: the signed notebook holds none of Colab's per-account metadata",
                       STAND_IN_USER not in text and "STAND-IN-AUTHORSHIP-TAG" not in text and "executionInfo" not in text))
        analysis = next(c for c in inner["cells"] if "".join(c["source"]).startswith("# The analysis."))
        checks.append((f"{name}: the signed notebook carries the analysis's outputs", bool(analysis["outputs"])))
    checks.append(("the rerun's signed notebook sets RUN = \"rerun\"", 'RUN = \\"rerun\\"' in rerun_signed["package"]["output"]))
    checks.append(("the receipt's verify_url for colab-example-rerun differs from colab-example's",
                   receipts["colab-example-rerun"]["verify_url"] != receipts["colab-example"]["verify_url"]))
    revises = [a for a in manifest["records"][0]["attestations"] if ".revises-" in a]
    withdraws = [a for a in manifest["records"][0]["attestations"] if ".withdraws-" in a]
    checks.append(("colab-example's entry carries one revises node and one withdrawal", len(revises) == 1 and len(withdraws) == 1))
    for label, ok in checks:
        say(f"{'ok ' if ok else 'BAD'} {label}")
    if not all(ok for _, ok in checks):
        fail("a check above")

    say("")
    scan = run([sys.executable, str(site / "scripts/scan_outputs.py"), "--root", str(site)], site, expect=None)
    if scan.returncode != 0:
        fail("the output scanner found a hit")

    leaks = []
    for path in sorted(work.rglob("*")):
        if path.is_file() and "node_modules" not in path.parts:
            data = path.read_bytes()
            leaks += [f"{path.relative_to(work)} holds the {what}" for what, v in (("seed", seed), ("token", token)) if v.encode() in data]
    for name, ns in (("first", first), ("rerun", rerun)):
        outputs = json.dumps([c.get("outputs", []) for c in ns["__frontend__"]["cells"]])
        leaks += [f"the {name} run's outputs hold the {what}" for what, v in (("seed", seed), ("token", token)) if v in outputs]
    leaks += [f"this script's own output holds the {what}" for what, v in (("seed", seed), ("token", token)) if v in printed.getvalue()]
    say(f"{'ok ' if not leaks else 'BAD'} neither the seed nor the token is in any file under {work} (node_modules aside), "
        "in any cell output, or in what this script printed" + ("" if not leaks else ": " + "; ".join(leaks)))
    if leaks:
        fail("a leak")
    say(f"\nREHEARSAL PASSED: {len(steps)} commits, each built, verified and displayed by the publish job's steps. Scratch: {work}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
