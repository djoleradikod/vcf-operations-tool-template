# Using this template

This page is deleted by `repokit.py init`. It walks through turning the template into a new
"&lt;Tool&gt; for VCF Operations" repository.

## 1. Name the tool

- Display name: **&lt;Tool&gt; for VCF Operations**, for example *Capacity Lens for VCF Operations*.
  Never *VCF Capacity Lens*. CI rejects it.
- Repository: `<slug>-for-vcf-operations`, for example `capacity-lens-for-vcf-operations`.
- Project page: `https://djonko.dev/projects/<slug>`.

## 2. Create the repository

On GitHub, open the template repository and choose **Use this template → Create a new repository**.
Name it as above and make it public (attestations and private vulnerability reporting are free on
public repositories).

## 3. Initialise

```sh
git clone https://github.com/<owner>/<slug>-for-vcf-operations && cd <slug>-for-vcf-operations
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/repokit.py init --name "Capacity Lens" --kind script --summary "One sentence."
# kind: script | agent | management-pack (add --mp-approach mp-builder|integration-sdk)
```

`init` renames the package and CLI, sets the slug and links, resets the changelog, removes this guide
and the template notice, and regenerates everything.

## 4. Fill in tool.yaml

- `summary` (one sentence, also the GitHub description) and `description`.
- `boundary`, if the tool reads anything other than VCF Operations. The README header states what
  the tool talks to; say exactly which systems it reads and that it never writes to them.
- `architecture`, if the default diagram for your `kind` does not match what the tool does.
- `compatibility.matrix`: what you have actually tested.
- `permissions`: the real minimum role. Rows stay `example: true` until confirmed on a real deployment.

Then:

```sh
python scripts/repokit.py render
python scripts/repokit.py check && pytest
pre-commit install
```

## 5. Replace the example command

`src/<package>/inventory.py` and the `inventory` command are a working example of the pattern every
command follows: a module that takes the client and returns rows, a short `cmd_*` function in
`cli.py`, and `output.emit_rows` for text, JSON and CSV. Keep it if your tool lists objects; otherwise
replace it with your own module and delete its tests in `tests/test_cli.py`. Keep `check`,
`profiles` and `about`: operators expect them in every tool of the family.

## 6. Write the parts only you can write

Search the repository for `TODO`. The README sections *Background*, *Design* and *Usage*,
the call table in `docs/architecture.md`, and a real, redacted screenshot in `docs/assets/`.

## 7. Push and configure

```sh
git add -A && git commit -m "feat: initial scaffold" && git push
scripts/configure-repo.sh
```

Then, once per repository, in the GitHub UI:

- Convert `docs/assets/social-preview.svg` to PNG (for example `rsvg-convert -w 1280 docs/assets/social-preview.svg > social-preview.png`) and upload it under
  *Settings → General → Social preview*.
- Add the `PRIVACY_TERMS` secret under *Settings → Secrets and variables → Actions*.
- Turn on *Releases → Immutable releases* if your account offers it.

## 8. First release

```sh
python scripts/repokit.py bump 0.1.0
git commit -am "chore(release): v0.1.0" && git tag -a v0.1.0 -m "v0.1.0" && git push --follow-tags
```

## 9. Link the project page

The djonko.dev project page reads `releases/latest/download/project.json` from the repository, so the
version, compatibility table and permissions on the site always match the latest release.
