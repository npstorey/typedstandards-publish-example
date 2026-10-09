import marimo

__generated_with = "0.25.1"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(
        """[![Verify this record with Typed Standards](https://typedstandards.org/badge/typed-standards-verify.svg)](<https://typedstandards.org/verify?url=https%3A%2F%2Fpublish-example.typedstandards.org%2Fbundles%2Fmarimo-example.bundle.json>)

    | Typed Standards record | |
    |---|---|
    | Host | `publish-example.typedstandards.org` |
    | Capture method | `script-run` |

    This cell is a reader affordance and is not authoritative: verification reads the signed record, not this cell, and the verifier shows the record's signer, hash and time.
    """
    )
    return


@app.cell
def _(mo):
    mo.md("""
    # A local Marimo app that publishes a record of its own source

    The record is this file, `marimo_example.py`, signed inline with this example's key and
    published to `https://publish-example.typedstandards.org` as `marimo-example`, with one call
    to the [`typedstandards`](https://pypi.org/project/typedstandards/) package. The cell above is
    the verifier badge for that record, written before signing.

    Start it under `op run`, which sets `TYPEDSTANDARDS_SIGNING_SEED_B64` and
    `TYPEDSTANDARDS_GITHUB_TOKEN` from 1Password for this process. The CLI reads the seed, and
    `publish` the token, from that environment; no cell prints or stores either. The repository's
    README gives the command.
    """)
    return


@app.cell
def _(mo):
    import statistics

    values = [40 + (17 * k) % 23 for k in range(1, 13)]
    mean = statistics.mean(values)
    above = [v for v in values if v > mean]
    mo.md(
        f"""
    Twelve values made by a fixed formula: `{values}`. Their mean is `{round(mean, 4)}`, and
    `{len(above)}` of them lie above it. The analysis reads no file, no network and no credential.
    """
    )
    return


@app.cell
def _(mo):
    publish_button = mo.ui.run_button(label="Sign this file and publish it")
    publish_button
    return (publish_button,)


@app.cell
def _(mo, publish_button):
    # Sign this file and publish it: on the button, or when the app was started with --publish.
    from pathlib import Path

    import typedstandards as ts

    mo.stop(
        not (publish_button.value or "publish" in mo.cli_args()),
        mo.md("Not published: press the button, or start the app with `--publish`."),
    )
    _source = Path(mo.notebook_dir()) / "marimo_example.py"
    _signed = ts.sign(
        {
            "type": "content/analysis/v1",
            "producerProfile": "scripted-recomputation/publish-example",
            "captureMethod": "script-run",
            "prompt": "Twelve values made by a fixed formula, and how many lie above their mean, computed in a local Marimo app.",
            "promptVisibility": "full_text",
            "queries": [],
            "dataSources": [],
            "cost": {"model": "none"},
            "skillMetadata": {},
            "trace": {},
            "signer": {"bindingTier": "pseudonymous", "displayName": "typedstandards-publish-example"},
        },
        output_file=_source,
    )
    receipt = ts.publish(
        _signed,
        host=ts.GitHubPagesHost("npstorey/typedstandards-publish-example"),
        name="marimo-example",
        title="A local Marimo app's record of its own source",
    )
    for _key in ("name", "commit", "bundle_url", "verify_url", "registry_url", "written"):
        print(f"{_key}: {receipt[_key]}")
    print("the badge cell links to verify_url:", f"](<{receipt['verify_url']}>)" in _signed["package"]["output"])
    return


if __name__ == "__main__":
    app.run()
