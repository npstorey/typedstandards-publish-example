# typedstandards-host-template

A GitHub template repository for serving signed [Typed Standards](https://typedstandards.org)
records from GitHub Pages under your own `did:key`. Copy it with "Use this template",
and replace the example record with your own. A copy runs in one of two modes:

- **Branch mode**, the default, and this template's own. You sign in your terminal,
  run `build`, and commit what Pages serves, under `docs/`. On every push, `check.yml`
  checks that the committed `docs/` is what
  [`@typedstandards/host-core`](https://www.npmjs.com/package/@typedstandards/host-core)
  builds, and that every record verifies.
- **Publish mode.** You commit only the signed record and its entry in `host.json`,
  for example from a notebook. On every push to `main`, `publish.yml` builds the site
  in the job, verifies every record, and deploys Pages from the job. See
  [Publishing from a notebook](#publishing-from-a-notebook).

[![Verify this record with Typed Standards](https://typedstandards.org/badge/typed-standards-verify.svg)](<https://typedstandards.org/verify?url=https%3A%2F%2Fhost-template.typedstandards.org%2Fbundles%2Ffirst-note.bundle.json>)

- **What it pins.** `@typedstandards/host-core` 0.1.1, exactly, and
  [`@typedstandards/cli`](https://www.npmjs.com/package/@typedstandards/cli) 0.2.0,
  exactly, for signing. `package-lock.json` resolves both from the npm registry.
- **What it serves.** One example record: `records/first-note.md`, a short Markdown
  note signed under `raw-bytes/v1`.
- **What it holds.** No key. Signing runs in your own terminal or notebook. Neither
  workflow signs: each builds, checks and verifies, and reads no repository secret.

## Layout

| Path | What |
|---|---|
| `host.json` | The host manifest: the origin, the visibility, the registry and the records. host-core reads it. |
| `records/` | What you sign and what signing printed: the note, the input to `sign`, and `sign`'s output. Kept out of `docs/`. |
| `host-policy.json` | The display policy: which records a page shows, and as what. |
| `docs/` | Branch mode: what Pages serves. `bundles/`, `.well-known/typed-publisher.json` and `records.json` are `typedstandards-host build`'s output. `.nojekyll`, `CNAME` and `index.html` are written by hand; `CNAME` names this template's domain. Publish mode keeps only `index.html` and `.nojekyll`, which the job copies into the site it builds. |
| `verify-output.txt` | Branch mode's golden: `typedstandards-host verify`'s output on `docs/`. Publish mode has none; each run's summary carries `verify`'s output. |
| `display.mjs` | Reads every record an index lists (`docs/records.json`, or the path given as its argument) through `host-policy.json` with host-core's `displayOf`, and exits 1 when one is refused. |
| `.github/workflows/check.yml` | Branch mode's workflow. |
| `.github/workflows/publish.yml` | Publish mode's workflow. |
| `.gitleaks.toml` | Tells [gitleaks](https://github.com/gitleaks/gitleaks) that an Ed25519 `did:key` identifier is a public key, not a secret. Without it, gitleaks reads every `did:key` in the signed and served files as an API key. |

## What the workflows check

A repository variable, `TYPEDSTANDARDS_HOST_MODE`, picks which workflow's jobs run:
`publish.yml`'s when it is `publish`, `check.yml`'s otherwise, unset included
([why a variable](#the-mode-switch-a-repository-variable)).

### Branch mode: `check.yml`

On every push and pull request, on Node 24:

1. `npm ci` installs the exact versions `package-lock.json` pins.
2. `npx typedstandards-host check` rebuilds `docs/` in memory from `host.json` and
   `records/`, and compares it with the committed `docs/` byte for byte.
3. `npx typedstandards-host verify` verifies every served record offline, with the
   network blocked, and its output must equal `verify-output.txt`.
4. `node display.mjs` reads every record through `host-policy.json`, and none may be
   refused.

### Publish mode: `publish.yml`

On every push to `main`, and on demand, on Node 24:

1. `npm ci` installs the exact versions `package-lock.json` pins.
2. `npx typedstandards-host build --out "$RUNNER_TEMP/site"` builds the served tree
   from `host.json` and `records/`, beside copies of `docs/index.html` and
   `docs/.nojekyll`.
3. `npx typedstandards-host verify` verifies every record in that tree offline, with the
   network blocked. Its output goes to the run summary, and a failure stops the job.
4. `node display.mjs "$RUNNER_TEMP/site/records.json"` reads every record in the built
   index through `host-policy.json`, and none may be refused.
5. `actions/upload-pages-artifact` uploads the tree with `include-hidden-files: true`.
   With its default, `false`, the action's `tar` adds `--exclude=.[^/]*`, and
   `.well-known/typed-publisher.json` is left out.
6. `actions/deploy-pages` deploys it. Only this job holds `pages: write` and
   `id-token: write`; the workflow's default is `contents: read`.

A failed step deploys nothing, and the site stays as it was.

**Why Node 24, and not an exact version.** The workflow pins the major version, 24.
The first line of `verify`'s output names no Node version and no core version:

```
typedstandards-host verify: records.json lists 1 record, each verified offline by @typedstandards/verify-core with the network blocked
```

so the golden stays equal across Node 24 patches. `verify-output.txt` was written on
Node 24.21.0. A change of Node major, or of host-core version, is a reason to
[regenerate the golden](#regenerate-the-golden) and review its diff.

## What the records prove

This describes what `typedstandards-host verify` checks offline, over the served
bundles (`verify-output.txt`).

- **Attested:** checkable by anyone from the served bundle. The row names the check.
- **Asserted:** stated inside the signed bytes, resting on the signer's word. No check establishes it.
- **Host's statement:** served by the host, unsigned. A verifier reads it, and it shows
  what the host says, not who holds the key.
- **Not covered:** nothing in this repository addresses it.

| Property | Status | Why |
|---|---|---|
| The bytes of the signed file | Attested (#3, #4, #1) | The record carries the file's exact UTF-8 bytes inline, under `raw-bytes/v1` (#3). #4 recomputes `contentHash.sha256` from those bytes, and #1 recomputes the envelope hash. The digest is the file's ordinary SHA-256, so `shasum -a 256 records/first-note.md` checks it without any Typed Standards code. |
| The signature over the record | Attested (#2) | Ed25519ph over the envelope-hash hex string. |
| The identifier is the key's | Attested (#14, #6) | #14 reads `key_derived_match`: the `did:key` identifier is derived from the public key that signed. #6 reads `ok`: the signature's `kid` equals `metadata.signingKeyId`. |
| Whether a record is withdrawn | Attested (#10), for what the bundle carries | A withdrawal is a signed attestation carried in the unsigned bundle. `verify` checks each one's signature and signer, and that the status they give equals the one `records.json` states. A host could leave a withdrawal out, and the record's own signature cannot show that it was not withdrawn. |
| The served files are what host-core builds | Checked by `check`, not by a verifier | `check` rebuilds `docs/` from `host.json` and `records/` and compares byte for byte. The bundle's view fields that are not copied from the package (the title, the visibility, `trustRegistryUrl` and the registry copy) are the host's. `verify` checks that every copied field equals the package's. |
| The key is active | Host's statement | `.well-known/typed-publisher.json` lists the key as active from the first record's `createdAt`. `verify` reads it as the file a verifier fetches from `trustRegistryUrl`, and #5 reads `active`. That shows which host publishes the statement, not who holds the key. The registry is this template's own statement about its example key. It is not a Typed Standards record, and not an endorsement by the Typed Standards specification or by typedstandards.org, although this host is a subdomain of it. |
| Who holds the key | Not covered | The signer is a pseudonymous `did:key`. Its `displayName` names this template, not a person. The example record's key was generated for its one signature and deleted after it. |
| Revocation of the key | Not covered | A `did:key` has no rotation. host-core 0.1.1 serves the key as active, and `host.json` has no field to mark it revoked. Anyone who holds a leaked seed can sign as the identifier. |
| Capture method and producer profile | Asserted (#15) | #15 reads `ok`: `script-run` is a value the `scripted-recomputation` profile allows. The label is signed, so changing it breaks #1, but no check establishes it. |
| The display policy | Host's statement | `host-policy.json` is this host's rule for what a page shows. It is not signed, and no verifier reads it. |
| When the record existed | Not covered | #7 does not apply: no RFC 3161 token was requested. `createdAt` is the signer's own claim. |
| Inclusion in a transparency log | Not covered | #8 does not apply: no transparency-log entry was submitted. |
| That any statement in the file is correct | Not covered | A signature shows the bytes are unchanged since signing, not that they are true. |

A bundle carries no `lifecycle` summary in host-core 0.1.1. A record's status is in
`records.json`, in the display policy's reading, and in the verifier's own reading of
the carried attestations.

## The served URLs

Pages serves `docs/` from `main`, at the custom domain `docs/CNAME` names, over
HTTPS. With `origin` set as in `host.json`:

| URL | What |
|---|---|
| `https://host-template.typedstandards.org/` | `docs/index.html` |
| `https://host-template.typedstandards.org/bundles/first-note.bundle.json` | The example record's bundle |
| `https://host-template.typedstandards.org/records.json` | The index, version 1 |
| `https://host-template.typedstandards.org/.well-known/typed-publisher.json` | The key registry, the bundle's `trustRegistryUrl` |

The verifier link for the example record:

```
https://typedstandards.org/verify?url=https%3A%2F%2Fhost-template.typedstandards.org%2Fbundles%2Ffirst-note.bundle.json
```

### Serve it over HTTPS

The browser verifier runs on an HTTPS page, so it can fetch the bundle and the
registry only over HTTPS: a browser blocks an `http` fetch, or a redirect to `http`,
from an HTTPS page. In the repository's Pages settings, set the custom domain and
turn on **Enforce HTTPS**. Once Pages has deployed, check that `origin` answers over
HTTPS without a redirect:

```sh
curl -sI "https://host-template.typedstandards.org/records.json"   # expect HTTP 200, and no location header
```

### A site with a path prefix

This template's site has its own domain, so `origin` has no path. A copy served as
a project site with no custom domain is served under a path,
`https://<owner>.github.io/<repository>/`. `origin` then carries that path, with no
trailing `/`, and host-core puts every served URL under it, the registry included:
`<origin>/.well-known/typed-publisher.json`. A verifier finds the registry by the
URL each bundle names in `trustRegistryUrl`, not at the host's root.

If the account's user site (`<owner>.github.io`) has a custom domain, GitHub serves
the account's project sites under that domain instead, and the `github.io` URL
redirects there, possibly over `http`. Set `origin` to the URL Pages actually serves
over HTTPS, and check it with the `curl` above.

### Cross-origin reads

The browser verifier at typedstandards.org fetches the bundle and the registry from
another origin, so it needs the host to send `Access-Control-Allow-Origin`. On
2026-09-29, with `Origin: https://typedstandards.org`, this template's site answered
`HTTP/2 200` with `access-control-allow-origin: *` for four paths: the bundle, the
registry, `records.json` and `/`. The same day, the verifier at typedstandards.org,
given the bundle's URL, read "Verified", with the key active in the registry it
fetched. That is what was checked; a copy checks its own site once Pages has
deployed it:

```sh
curl -sI -H 'Origin: https://typedstandards.org' \
  "<origin>/bundles/<name>.bundle.json" \
  | grep -i '^access-control-allow-origin'
```

`docs/.nojekyll` stops Pages running Jekyll, which would leave `.well-known/` out of
the site.

## The badge snippet

`npx typedstandards-host links` prints each record's verifier link and badge
snippets, in the site's own percent-encoded form. The example record's HTML:

```html
<a href="https://typedstandards.org/verify?url=https%3A%2F%2Fhost-template.typedstandards.org%2Fbundles%2Ffirst-note.bundle.json">
  <img src="https://typedstandards.org/badge/typed-standards-verify.svg" alt="Verify this record with Typed Standards" width="248" height="30" />
</a>
```

and its Markdown:

```md
[![Verify this record with Typed Standards](https://typedstandards.org/badge/typed-standards-verify.svg)](<https://typedstandards.org/verify?url=https%3A%2F%2Fhost-template.typedstandards.org%2Fbundles%2Ffirst-note.bundle.json>)
```

The badge is a call to verify, not a verdict. `docs/index.html` links to the
verifier with text and shows no badge image, because the image is served by another
host and the page loads nothing from any other host.

## What a copy changes

These are branch mode's steps. Publish mode's are in
[Publishing from a notebook](#publishing-from-a-notebook).

1. **`docs/CNAME`, before you enable Pages.** Delete it, or replace its one line with
   your own domain. It names this template's domain, and GitHub Pages reads it as
   the site's custom domain, so a copy that keeps it would try to claim this
   template's domain instead of serving yours.
2. **`origin`** in `host.json`: the URL your Pages site is served at over HTTPS (see
   [a site with a path prefix](#a-site-with-a-path-prefix)). The registry's and the
   index's `$comment` strings are yours too: the registry's says whose statement it
   is.
3. **The record.** Remove the example record and sign your own (below). `build`
   deletes nothing, so the example's bundle is removed by hand; `check` reports a
   served bundle that `host.json` no longer lists.
4. **The policy.** `signer` in `host-policy.json` becomes your `did:key`, and the
   rules name your records' statuses and roles.
5. **`docs/index.html`**, by hand, and the URLs and badge in this README.
6. **The golden**, `verify-output.txt`, [regenerated](#regenerate-the-golden).
7. **Pages**, in the repository's settings: deploy from a branch, `main`, `/docs`;
   your custom domain, if any; and Enforce HTTPS.

## Sign your first record

In a copy of this template in branch mode, on Node 24. The commands run from the repository's root.

```sh
npm ci
```

### 1. Make a key, and keep it out of the repository

The CLI reads the signing seed from one environment variable,
`TYPEDSTANDARDS_SIGNING_SEED_B64`: the base64 of 32 random bytes. It never prints the
seed and never writes it. Keep the seed in a secret store, as the
[CLI's README](https://www.npmjs.com/package/@typedstandards/cli) shows with
`op run`. At the least, keep it in a file only you can read, outside every
repository:

```sh
export KEY_FILE="$HOME/.typedstandards/signing-seed.b64"
mkdir -p "$(dirname "$KEY_FILE")"
test -e "$KEY_FILE" || ( umask 077 && openssl rand -base64 32 > "$KEY_FILE" )
```

Never commit the seed, print it, or add it to this repository's secrets: the
workflow signs nothing. The seed is the only way to sign, or withdraw, under your
`did:key`, so keep a backup. A `did:key` cannot be rotated.

### 2. Replace the example record

```sh
git rm -q docs/CNAME   # or write your own domain into it
git rm -q records/first-note.md records/first-note.signed.json docs/bundles/first-note.bundle.json
git mv records/first-note.input.json records/my-record.input.json
printf '# My record\n\nThe text I am signing.\n' > records/my-record.md
```

Edit `records/my-record.input.json`: set `signer.displayName` to the name you sign
under, and `prompt` to what the record is. The input is produce-core's envelope
input, which the [CLI's README](https://www.npmjs.com/package/@typedstandards/cli)
describes under `sign`.

### 3. Sign

```sh
TYPEDSTANDARDS_SIGNING_SEED_B64="$(cat "$KEY_FILE")" npx typedstandards sign \
  --input records/my-record.input.json --output-file records/my-record.md \
  > records/my-record.signed.json
```

`sign` verifies its own result offline before it prints. The file's bytes are signed
inline under `raw-bytes/v1`, so the file must be UTF-8.

### 4. Point `host.json` and the policy at your record

In `host.json`, set `origin`, and replace the example's entry in `records`:

```json
{ "name": "my-record", "signed": "records/my-record.signed.json", "attestations": [], "title": "My record", "extensions": { "role": "note" } }
```

In `host-policy.json`, set `signer` to your `did:key`, which this prints:

```sh
node -p 'require("./records/my-record.signed.json").package.signer.identifier'
```

### 5. Build, check, verify, and print the links

```sh
npx typedstandards-host build
npx typedstandards-host check
npx typedstandards-host verify > verify-output.txt
node display.mjs
npx typedstandards-host links
```

`build` writes `docs/`. `check` compares it with a fresh build. `verify` writes the
new golden; review it with `git diff verify-output.txt`. `links` prints the verifier
link and badge snippets for this README and `docs/index.html`. Commit, push, and the
workflow runs the same checks.

### 6. Withdraw a record

A signed record cannot be changed. A correction is a withdrawal plus a new record.
The withdrawal is signed with the same key:

```sh
node -e '
const s = require("./records/my-record.signed.json");
const input = { targetNodeId: s.envelopeHash, reason: "Replaced by a corrected record.", signer: { bindingTier: s.package.signer.bindingTier, displayName: s.package.signer.displayName } };
require("node:fs").writeFileSync("records/my-record.withdraw-input.json", JSON.stringify(input, null, 2) + "\n");
'
TYPEDSTANDARDS_SIGNING_SEED_B64="$(cat "$KEY_FILE")" npx typedstandards withdraw \
  --input records/my-record.withdraw-input.json > records/my-record.withdrawal.json
```

Add it to the record's `attestations` in `host.json`:

```json
"attestations": ["records/my-record.withdrawal.json"]
```

and run step 5 again. The record still verifies, `records.json` lists it as
`withdrawn` with the reason, and the policy's `withdrawn` rule displays it.

## Publishing from a notebook

In publish mode the repository holds only inputs: the signed records under `records/`,
their entries in `host.json`, the policy, and `docs/index.html`. A notebook publishes a
record by committing its signed file and its `host.json` entry to `main` in one
commit, with the Python package [`typedstandards`](https://pypi.org/project/typedstandards/);
its README describes the call. Each push to `main` then runs `publish.yml`, which
builds, verifies and deploys the whole site
([what it runs](#publish-mode-publishyml)). The measurements behind these steps were
made on a public repository.

### The mode switch: a repository variable

| Mode | `TYPEDSTANDARDS_HOST_MODE` | The job that runs | Pages source | What is served |
|---|---|---|---|---|
| Branch mode | unset, or anything but `publish` | `check.yml`'s | Deploy from a branch: `main`, `/docs` | The committed `docs/` |
| Publish mode | `publish` | `publish.yml`'s | GitHub Actions | `build` over the pushed commit, made in the job |

Each job reads the variable in its own `if:` line:

```yaml
# .github/workflows/check.yml, job check
    if: vars.TYPEDSTANDARDS_HOST_MODE != 'publish'
# .github/workflows/publish.yml, jobs build and deploy
    if: vars.TYPEDSTANDARDS_HOST_MODE == 'publish'
```

Why a variable, and not deleting the other mode's workflow: both workflows start on
a push to `main`. This template is itself a branch-mode site, so it has to carry
`publish.yml` without running it: its own site is served from `main`, `/docs`, not
deployed from a job. Deleting a file cannot do that, and a variable can.
A copy made from the template gets both files and no variable, so it starts in
branch mode, as copies made before publish mode do. One setting switches a copy
either way, with no commit. In each mode the other workflow still starts on a push,
and its job is skipped.

### Steps

1. **Make the repository.** "Use this template", public.
2. **Turn on Pages from Actions, and set the mode.** In the repository's settings:
   Pages, Build and deployment, Source: **GitHub Actions**. Then Secrets and
   variables, Actions, Variables: a repository variable `TYPEDSTANDARDS_HOST_MODE`
   with the value `publish`. With the GitHub CLI:

   ```sh
   gh variable set TYPEDSTANDARDS_HOST_MODE --body publish --repo <account>/<repository>
   ```

   From here `check.yml`'s job is skipped and `publish.yml`'s jobs run.
3. **Pick the address, with one `curl`** on the account address, once step 2 is
   done, reading the first hop only:

   ```sh
   curl -sS -o /dev/null -w 'first-hop: %{http_code} location=%{redirect_url}\n' \
     "https://<account>.github.io/<repository>/"
   ```

   - **A `200`:** use the account address as it is (step 4a).
   - **A redirect** (a `301` with a `location`): use a custom subdomain (step 4b).
     An account whose own user site has a custom domain gets this: GitHub redirects
     the account address to that domain, over `http`, on a response with no
     `access-control-allow-origin`, as `first-hop: 301 location=http://<other-host>/<repository>/`.
     A page on HTTPS cannot follow that.

   A `404` with no `location` is not a redirect: read it as the first case, and run
   the `curl` again once the first deploy is served. `origin` can change later,
   because each run rebuilds every bundle from it. The `200` case rests on GitHub's
   documentation; the account these steps were measured on got the redirect.
4. **Set up the address.**
   - **a. The account address.** `origin` in `host.json` is
     `https://<account>.github.io/<repository>`, with no trailing `/`
     ([a site with a path prefix](#a-site-with-a-path-prefix)).
   - **b. A custom subdomain.** The general pattern is a subdomain of a domain you
     own, for example `typedstandards.<your-site>`. At your DNS provider, add a
     `CNAME` record from that name to `<account>.github.io.`. In the Pages settings,
     set the custom domain to the same name, and turn on **Enforce HTTPS** once its
     certificate is approved. `origin` is `https://<subdomain>`. A site deployed from
     Actions ignores `docs/CNAME` (GitHub's documentation), so the domain lives in the
     Pages settings only.

     **When a certificate does not arrive.** On one site deployed from Actions, the
     certificate stayed absent for about 34.5 hours. Changing the custom domain to
     another name, one with no DNS record, and back again got it approved in under a
     minute. Then read its state:

     ```sh
     gh api repos/<account>/<repository>/pages --jq .https_certificate.state   # expect approved
     ```

   GitHub Pages is the documented host, not the only one. Any static host will do
   that serves `/records.json`, `/.well-known/typed-publisher.json` and each
   `/bundles/<name>.bundle.json` under `origin`, over HTTPS with no redirect, with a
   JSON content type and `access-control-allow-origin: *`. `publish.yml`'s upload and
   deploy jobs are Pages-specific.
5. **Change the copy for publish mode**, in one commit:

   ```sh
   git rm -q -r docs/bundles docs/.well-known docs/records.json docs/CNAME verify-output.txt
   git rm -q records/first-note.md records/first-note.input.json records/first-note.signed.json
   ```

   - `docs/bundles/`, `docs/.well-known/` and `docs/records.json` are build output.
     Publish mode builds them in the job, so committed copies would go stale and no
     workflow would check them.
   - `docs/CNAME` names this template's domain, and Actions ignores it.
   - `verify-output.txt` is branch mode's golden. In publish mode it would change on
     every publish, and each run's summary carries `verify`'s output instead.
   - Keep `docs/index.html` and `docs/.nojekyll`: the job copies both into the site it
     builds, and its `cp` fails without either. Edit `index.html` by hand: it names
     this template's example record, and no build adds the records a notebook
     publishes to it; `records.json` lists them. `.nojekyll` matters only in branch
     mode, and keeping it lets the copy switch back.
   - In `host.json`: set `origin` (step 4), and remove the example's entry from
     `records`, leaving `"records": []`. Edit the registry's and the index's `$comment`
     strings, which are yours.
   - In `host-policy.json`: set `signer` to your `did:key`, the
     `package.signer.identifier` of any record signed with your seed. The active rule
     admits the roles `note` and `notebook`; name any other role your records carry.

   host-core refuses a manifest with no records, so this commit's run fails at
   `build` with `records must be a non-empty array`, and deploys nothing. The first
   publish makes the first deploy.
6. **Make the token.** A fine-grained personal access token: this one repository
   only; repository permission **Contents: Read and write**, and nothing else
   (GitHub adds Metadata: Read-only on its own). On a public repository the workflow
   runs are readable with no token at all. A private repository was not measured:
   what its token needs, and who can read its runs, are unknown. Keep the token in a
   secret store, never in the repository or a notebook's saved output. With
   1Password's CLI, run `op signin` in that terminal before `op run`, which otherwise
   answers `You are not currently signed in`.
7. **Add the ruleset.** On the default branch: block deletion and force pushes, with
   no bypass actors, and nothing more:

   ```sh
   echo '{"name":"main","target":"branch","enforcement":"active","conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"],"exclude":[]}},"rules":[{"type":"non_fast_forward"},{"type":"deletion"}]}' | gh api -X POST repos/<account>/<repository>/rulesets --input -
   ```

   No signed-commits rule: a commit made through the API with a fine-grained token is
   unsigned, and the rule would refuse it. No pull-request rule: the notebook commits
   to `main` directly. This ruleset lets the token's commit through.
8. **Publish from the notebook**, as the
   [`typedstandards` package's README](https://pypi.org/project/typedstandards/)
   shows. The commit starts `publish.yml` within seconds; on the measured copy a new
   record was served about 42 seconds after its commit.
9. **See each run.** The repository's Actions tab lists `publish` runs; a run's
   summary carries `verify`'s output, and a failed step's log says why. From a
   terminal:

   ```sh
   gh run list --workflow publish.yml --repo <account>/<repository> --limit 5
   curl -sS "https://api.github.com/repos/<account>/<repository>/actions/runs?head_sha=<commit>" \
     | jq -r '.workflow_runs[] | "\(.name) \(.status) \(.conclusion) \(.html_url)"'
   ```

### When a deploy is stuck

Every run builds the whole of `main`. A commit whose record fails `build` or
`verify` (its row in the summary reads `FAIL`), or that `display.mjs` refuses, deploys
nothing, and nor does any later commit while that record is on `main`: each later run
fails at the same record. The site keeps serving the last good deploy.

The remedy is a commit that removes the failing record: its file under `records/`
and its entry in `host.json`, for example by reverting the commit that added it:

```sh
git revert <commit>
git push
```

That record was never served, so removing it withdraws nothing. The next run deploys
everything else on `main`.

## The display policy, and a policy kept as YAML

`host-policy.json` is JSON with `$comment` strings. host-core reads JSON only. A
policy kept as YAML is converted first, with any YAML-to-JSON tool. With the
[`yaml`](https://www.npmjs.com/package/yaml) package's command:

```sh
npx --yes yaml@2.9.1 --json --single --strict --indent 2 < host-policy.yaml > host-policy.json
```

This YAML converts, byte for byte, to the committed `host-policy.json`:

```yaml
$comment: >-
  The display policy: which records a page shows, and as what. It is this host's
  own rule, not signed and not verified. Every rule names its statuses, so a status
  no rule names is refused. A copy of the template changes signer to its own did:key.
signer: did:key:z6Mks7BK2kyVhoPY3ayt6ALKeZY5eCbu64XyQuje9gTUxiUB
type: content/analysis/v1
display:
  - $comment: An active note, or a record published from a notebook, is shown as current.
    status: active
    extensions:
      role: [note, notebook]
    as: current
  - $comment: A withdrawn record stays listed, marked withdrawn.
    status: withdrawn
    as: withdrawn
unmatched: refuse
```

A record's roles are host-specific, so they go under the record's `extensions` in
`host.json`, and a rule names the values it admits. A record is displayed by the
first rule it matches, and refused when its status is not `active`, `withdrawn` or
`superseded`, when `signer` or `type` does not name it, or when no rule matches.
`superseded` is displayed only when a rule names it.

## Visibility is host-wide

`visibility` in `host.json` is every record's disclosure state: host-core 0.1.1 has
no per-record visibility. It is never defaulted. Records that need different
visibilities need separate hosts.

## Regenerate the golden

`verify-output.txt` is `typedstandards-host verify`'s output on `docs/`. After any
change that alters it (a record added or withdrawn, a host-core upgrade, a new Node
major), regenerate it and review the diff:

```sh
npx typedstandards-host build
npx typedstandards-host check
npx typedstandards-host verify > verify-output.txt
git diff verify-output.txt
```

To upgrade host-core, pin the new version exactly, then regenerate:

```sh
npm install --save-exact @typedstandards/host-core@<version>
```

## License

MIT
