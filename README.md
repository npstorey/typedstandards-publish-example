# typedstandards-publish-example

A worked example of publishing signed [Typed Standards](https://typedstandards.org) records
from a notebook. A hosted Google Colab notebook and a local Marimo app each sign their own
file, and publish it with one call to the Python package
[`typedstandards`](https://pypi.org/project/typedstandards/0.2.0/) 0.2.0. The records are
served at `https://publish-example.typedstandards.org`.

This repository was made from
[`typedstandards-host-template`](https://github.com/npstorey/typedstandards-host-template)
and set up in its publish mode, by the template README's
[Publishing from a notebook](https://github.com/npstorey/typedstandards-host-template#publishing-from-a-notebook),
steps 1 to 9. Each publish is one commit to `main`. The template's `publish.yml` then builds
the site from `host.json` and `records/`, verifies every record, and deploys it to GitHub
Pages. The wrapper's README, at its 0.2.0 release,
[Publishing to a GitHub Pages host](https://github.com/npstorey/typedstandards-python/blob/bdcf377040c462d9648554879f1ee976e4be6524/README.md#publishing-to-a-github-pages-host),
describes `publish`, its names, its refusals and its receipt.

## Layout

| Path | What |
|---|---|
| `notebooks/colab-example.ipynb` | The Colab notebook. Committed with no outputs. Cell 0 is the verifier badge for `colab-example`. |
| `notebooks/marimo_example.py` | The Marimo app. Its second cell is the badge for `marimo-example`. |
| `scripts/scan_outputs.py` | The output scanner. |
| `scripts/rehearse.py` | The offline rehearsal of the four publishes. |
| `host.json`, `host-policy.json`, `records/` | The host's inputs. Each publish adds a record. |
| `docs/index.html`, `docs/.nojekyll` | Copied into the site by `publish.yml`. |
| `display.mjs`, `.github/workflows/` | The template's, unchanged. |

## The four records

| # | What | Made by | Name |
|---|---|---|---|
| 1 | A record of the notebook | `colab-example.ipynb`, `RUN = "first"` | `colab-example` |
| 2 | A record of the app's source | `marimo_example.py` | `marimo-example` |
| 3 | A record of the notebook's rerun, with a `revises` node from 1 to 3 | `colab-example.ipynb`, `RUN = "rerun"` | `colab-example-rerun` |
| 4 | A withdrawal of 1, with its reason | the same rerun, after 3 | on `colab-example` |

Each name was chosen before signing. The badge is part of the signed bytes and links to the
record's bundle URL, so the name has to be known before signing. `badge_cell` refuses a URL
that holds a date, a time or a 64-hex string, so the wrapper's default name
(`<stem>/<date>-<eight hex>`) cannot be badged. A rerun published under its first run's
name would be listed as `colab-example-<eight hex of its own hash>`, which its badge cannot
name either. So the rerun has a name of its own, and `publish` puts the `revises` node on the
entry of the record the node targets.

The rerun reads the first record's `envelopeHash` from the served `records.json` (its
`packageHash`). `publish` checks that hash against the repository's `main` before writing.

## What the records prove

`publish.yml` runs `typedstandards-host verify` over every record. For what that verifies
(the bytes, the signature, the key, the carried withdrawal, and what is only the host's
statement), see the template README's
[What the records prove](https://github.com/npstorey/typedstandards-host-template#what-the-records-prove).
For each record here:

- **`colab-example`.**
  - *Proves:* the signed `.ipynb` has not changed since this example's key signed it: every
    cell's source, and the outputs of the cells above the signing cell.
  - *Does not prove:*
    - that those outputs came from running that source. The outputs are what Colab's frontend
      returned, and a signer can change them before signing;
    - that it ran on Colab, or when. `createdAt` is the signer's own claim;
    - that the analysis is correct;
    - who holds the key. The signer is a pseudonymous `did:key`.
  - The signed file is the notebook in the form the signing cell writes (below). It is not
    byte-equal to any `.ipynb` that Colab saves.
- **`marimo-example`.**
  - *Proves:* the app's source file has not changed since it was signed. The record carries
    its bytes, and `shasum -a 256 notebooks/marimo_example.py` gives the record's
    `contentHash` while the file is unchanged.
  - *Does not prove:* any output, because a Marimo file holds none; that the app ran; or
    which commit of this repository held the file.
- **`colab-example-rerun`.**
  - *Proves and does not prove:* as `colab-example`.
  - The `revises` node, carried on `colab-example`'s entry, is a signed statement by the same
    key that the rerun revises the first run. It never changes `colab-example`'s status. It
    does not prove that the rerun corrects anything.
- **The withdrawal of `colab-example`.**
  - *Proves:* the key's holder signed a withdrawal of `colab-example` with this reason:
    "Replaced by a rerun of the same notebook, published as colab-example-rerun."
    `records.json` lists the record as `withdrawn` with the reason, and the record still
    verifies.
  - *Does not prove:* that the reason is true. A host could also leave a withdrawal out, and
    the record's own signature cannot show that it was not withdrawn (the template README).

## How the notebook signs its own bytes

Colab's kernel holds no file of the notebook. Cell 3 (counting the badge as cell 0; it starts
`# This notebook's own bytes`) asks Colab's frontend for it with
`google.colab._message.blocking_request("get_ipynb", ...)`. This request is internal and
undocumented. In colabtools' source
([`_message.py`](https://github.com/googlecolab/colabtools/blob/f4b1d17310779e2f312fd7c06e5084ec80deb9f1/google/colab/_message.py),
at `f4b1d17`), `blocking_request` sends a request of any type to the frontend. It returns the
reply's `data`, returns `None` on a timeout, and raises `MessageError` on an error reply.
Nothing in colabtools names `get_ipynb`: Colab's frontend answers it, and the frontend's
source is not public.

The notebook takes the reply's `ipynb` value as the notebook. Cell 3 makes the request before
any secret is read. It stops the run if the reply is not an nbformat 4 notebook with the
parameters, analysis and signing cells. The signing cell asks again. It stops if the reply
does not set this run's `RUN`, or holds no output for the analysis.

What is signed is the notebook rebuilt from the reply:

- every cell keeps its type and its source;
- code cells above the signing cell keep their outputs and execution counts, and the signing
  cell and every later cell keep neither;
- every cell's metadata is dropped. Of the notebook's metadata, only `kernelspec` and
  `language_info` are kept. Colab's cell metadata can name the account that ran each cell;
- the badge in cell 0 is replaced by this run's, written by `badge_cell` before signing;
- the file is written as nbformat 4.4 JSON with one-space indentation and sorted keys.

**The fallback**, if cell 3 stops:

1. Run the cells down to the analysis.
2. Use File, Download, Download `.ipynb`.
3. Upload that file in the Files pane, which puts it under `/content/`.
4. Set `NOTEBOOK_FILE = "/content/<its name>.ipynb"` in the parameters cell, and run from
   the parameters cell on.

The signed notebook is then the downloaded file, rebuilt as above, and its parameters cell
reads `NOTEBOOK_FILE = None`. Set `RUN` before you download.

## The seed and the token

The seed is the base64 of 32 random bytes: this example's signing key. It was made once,
outside any notebook, and is kept in 1Password. The token is a fine-grained personal access
token for this repository alone, with Contents read and write
([the template README, step 6](https://github.com/npstorey/typedstandards-host-template#steps)).

**Do not:**

- paste the seed into a cell, print it (with `print`, `%env`, or a cell whose last expression
  is its value), or save it in the `.ipynb` in any other way. The notebook is the file that
  is signed and published;
- make the seed a GitHub Actions variable or secret. Nothing in this repository's workflows
  signs, and a workflow that could read the seed could sign as this key;
- generate a seed in a notebook and keep it nowhere else. A record signed by a lost key can
  never be withdrawn or revised.

The token follows the same rules. It is read from `TYPEDSTANDARDS_GITHUB_TOKEN`, and never
written as a literal in a cell.

### Custody in Colab

The notebook reads both values from Colab's Secrets panel (the key icon in the left bar), in
one cell that prints nothing. That cell runs after the analysis and just before the signing
cell:

```python
os.environ["TYPEDSTANDARDS_SIGNING_SEED_B64"] = userdata.get("TYPEDSTANDARDS_SIGNING_SEED_B64")
os.environ["TYPEDSTANDARDS_GITHUB_TOKEN"] = userdata.get("TYPEDSTANDARDS_GITHUB_TOKEN")
```

- **What colabtools' source establishes.** In
  [`userdata.py`](https://github.com/googlecolab/colabtools/blob/f4b1d17310779e2f312fd7c06e5084ec80deb9f1/google/colab/userdata.py),
  at `f4b1d17`, `userdata.get` asks Colab's frontend for the value through
  `_message.blocking_request("GetSecret", ...)`, and returns the reply's `payload`. The reply
  says whether the secret exists (`SecretNotFoundError` if not), and whether this notebook
  has access to it (`NotebookAccessError` if not). With no Colab UI to answer, as when the
  notebook runs outside it, the request times out (`TimeoutException`: "Secrets can only be
  fetched when running from the Colab UI"). So the kernel gets a value only by asking the
  frontend while the notebook runs, and only for a notebook with access. The value is not in
  the notebook file.
- **What the source does not establish.** Where Google stores the value, and for how long.
- **The panel.** It shows the same list of secrets in every notebook of the Google account.
  Each notebook has its own access toggle for each secret, and reads a value only with that
  toggle on.
- **The choice.** Choosing Colab is choosing that Google holds the seed and the token for as
  long as the secrets exist in the panel, not only while the kernel runs. While the runtime
  runs, the values are also in its environment, which every later cell and every process it
  starts can read. After a run, use Runtime, Disconnect and delete runtime. When the example
  is done, delete both secrets from the panel. The seed stays in 1Password.

Locally, the Marimo app gets both values from `op run`. Its env file maps each variable to a
1Password reference, and no value is in the file. Each mapping is one unquoted line; a
quoted reference reaches the process with its quotes, and `publish` refuses a token that holds
a quote:

```sh
TYPEDSTANDARDS_SIGNING_SEED_B64=op://<vault>/<item>/<field>
TYPEDSTANDARDS_GITHUB_TOKEN=op://<vault>/<item>/<field>
```

## Running each step

The setup (template README, steps 1 to 9) is done. This repository's step 5 is the commit
"Set up this copy for publish mode". Its own `publish` run fails at `build` with
`records must be a non-empty array`, as step 5 says, until the first publish. Run the
publishes in this order. After each one, watch its run with
`gh run list --workflow publish.yml --repo npstorey/typedstandards-publish-example --limit 5`,
then open the printed `verify_url`.

1. **The notebook's first run: `colab-example`.**
   1. Open
      `https://colab.research.google.com/github/npstorey/typedstandards-publish-example/blob/main/notebooks/colab-example.ipynb`.
   2. In the Secrets panel, add `TYPEDSTANDARDS_SIGNING_SEED_B64` and
      `TYPEDSTANDARDS_GITHUB_TOKEN`, with values copied from 1Password. Turn on this
      notebook's access to both.
   3. Leave `RUN = "first"`, and use Runtime, Run all. Colab asks before running a notebook
      it did not write; run it anyway.

   The publish cell prints the receipt's `name`, `commit`, `bundle_url`, `verify_url`,
   `registry_url` and `written`, and whether the badge in cell 0 links to `verify_url`.
2. **The Marimo app: `marimo-example`.** From this repository's root, with Node 20.19 or
   later on `PATH`, run `op signin` first, then:

   ```sh
   op run --env-file="$HOME/.typedstandards/publish-example.env" -- \
     uv run --no-project --with typedstandards==0.2.0 --with marimo==0.25.1 \
     python notebooks/marimo_example.py --publish
   ```

   This signs the file as committed. Without `--publish`, the app signs nothing. Under
   `marimo run notebooks/marimo_example.py`, it has a button that does the same; the
   rehearsal below runs the script form only.
3. **The rerun and the withdrawal: `colab-example-rerun`, then `colab-example` withdrawn.**
   Wait until the first run's `publish` run has deployed: the rerun reads the served
   `records.json`. In the notebook, set `RUN = "rerun"`, and use Runtime, Run all. The
   publish cell signs a `revises` node and publishes the rerun. The withdrawal cell then
   withdraws `colab-example`.
4. **Check.** Run
   `curl -sS https://publish-example.typedstandards.org/records.json | jq '.records[] | {name, status, withdrawn}'`.
   It lists `colab-example` as `withdrawn` with its reason, and the other two as `active`.
   Open each record's `verify_url`.

**Running a step again.** A repeat of step 1 or 3 signs a new record under a name already
listed. `publish` refuses it before any write (`PublishRefusedError`), and nothing changes.
If step 3's withdrawal cell fails after the rerun was published, run only the secrets cell
and the withdrawal cell. Run the withdrawal cell once: each run adds a withdrawal. To
publish a further record, give it a new name in the parameters cell.

**A failed deploy.** See the template README's
[When a deploy is stuck](https://github.com/npstorey/typedstandards-host-template#when-a-deploy-is-stuck).

## The scanner and the rehearsal

```sh
python3 scripts/scan_outputs.py [PATH ...]
```

The scanner searches every output of every cell. It reads every `.ipynb` git lists, every
notebook signed inline in `records/*.signed.json`, and each path given. It looks for
`TYPEDSTANDARDS_SIGNING_SEED_B64`, `TYPEDSTANDARDS_GITHUB_TOKEN` and the token prefix
`github_pat_`. On a hit it exits 1 and names the file, the cell and the output, never the
text. It exits 2 when an input cannot be read.

```sh
fnm exec --using=24 -- uv run --no-project --with typedstandards==0.2.0 --with marimo==0.25.1 \
  python scripts/rehearse.py
```

The rehearsal runs the four publishes in the order above, offline, in a scratch copy of the
committed tree:

- It uses a throwaway seed made in its own process, and the scratch copy's policy names that
  key.
- A fake GitHub API answers the reads and Git Data API writes that `publish` makes.
- Colab is stood in for: `userdata.get`, and the `get_ipynb` reply with Colab-style metadata.
  The Marimo app runs as a script.
- After each commit, it runs `publish.yml`'s steps on Node 24 with the pinned host-core:
  `build`, `verify` and `display.mjs`.

It fails unless:

- every step exits 0;
- `records.json` shows the withdrawal with its reason;
- each badge links to its receipt's `verify_url`;
- a repeat of either notebook run is refused before any write;
- the scanner finds nothing;
- neither the seed nor the token appears in any file, output or line it printed.

It needs `npm` and the npm registry for `npm ci`, and nothing else from the network.

## License

MIT
