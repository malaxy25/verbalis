# Maintenance

What keeps Verbalis healthy, and how often. Effort: about 15 minutes a month,
plus a release now and then.

## Monthly (after Dependabot has opened its pull requests)

Dependabot checks once a month and opens **grouped** pull requests:

| PR | What it updates | Risk |
|---|---|---|
| `python-dependencies` | `pyproject.toml` (ranges, rarely anything) and the exact versions of the installer in `packaging/requirements-build.txt` | medium |
| `github-actions` | versions of the building blocks in `.github/workflows/` | low |

For each PR:

1. **Tests green?** The «Tests» workflow runs on every PR (Windows and Ubuntu). Its job
   **build versions** installs exactly the pinned versions of the installer – if a new pin
   doesn't fit the others (e.g. one package requires an older version of another), it is red.
   Red → don't merge; see «When a dependency PR can't be merged» below.
2. **Major version jump** (e.g. `4 → 7`)? Skim the release notes in the PR for
   «breaking». Usually it only concerns features Verbalis doesn't use.
3. **Merge on GitHub** («Merge pull request»), then «Delete branch».
4. For `build-dependencies`: **start the Release workflow manually**
   (Actions → Release → Run workflow). It builds and self-tests the installer
   without publishing. Green → the next tag will build fine.
5. **Locally:** `git pull` – otherwise your local `main` is behind GitHub.

## When a dependency PR can't be merged

Dependabot updates single packages; sometimes another package doesn't allow the new
version yet. Example (October 2026): huggingface-hub 2 – tokenizers, which faster-whisper
needs, requires huggingface-hub < 2.

1. Close the PR («Close pull request») – don't merge it.
2. Add an `ignore` entry with a comment to `.github/dependabot.yml`, so Dependabot doesn't
   propose it again every month (see the huggingface-hub entry there).
3. Remove the entry once the blocking package has a compatible version – Dependabot
   proposes updates of the blocking package as usual.

## Immediately: security alerts

GitHub shows known vulnerabilities under **Security → Dependabot alerts** and
sends an email. Don't wait for the monthly round for those: merge the security
PR (or ask for an update) as soon as the tests are green.

## When the dictionary issue appears

The «Dictionary check» workflow runs on the 2nd of every month and opens an issue
«Newer Swiss German spelling dictionary available» when LibreOffice changed it.
The issue contains the new revision; set it as `DICTIONARY_REVISION` in
`src/verbalis/spelling.py`, release, and every installation downloads the new
dictionary once. No hurry – spelling dictionaries change rarely and slowly.

## Models

- **Updates of a downloaded model** are offered to the user at start («Modell-Update
  verfügbar») and only taken on confirmation, unless «Modell-Updates automatisch
  übernehmen» is switched on. Models load from the approved revision on disk
  (`~/.verbalis/models.json`); the previous revision stays for «Zurück auf vorherigen
  Stand». For company use: compare a new revision with `verbalis compare` before
  rolling it out.
- **Flix** is served from our own repo `malaxy/flix-swissgerman-ct2`. The «Model check»
  workflow (3rd of every month) opens an issue «Newer version of a converted model
  available» when Flix-AI publishes new model files. Then:
  1. `pip install -e ".[convert]"`, `verbalis convert-model Flix-AI/flix-swissgerman-full --force`
  2. compare old and new with `verbalis compare` (read-aloud text and a real Teams call);
     only continue if the new one is at least as good
  3. upload as in `tools/flix-model/README.md` (the old version stays in the repo history,
     so you can go back)
  4. set the new revision in `UPSTREAM_REVISIONS` (`transcription/models.py`) and in the
     model card, add a line to `CHANGELOG.md`, release
  Installations download the new Flix the next time they transcribe.
- **Only the model card changed?** Upload it with
  `hf upload malaxy/flix-swissgerman-ct2 tools/flix-model/README.md README.md` – installations
  don't download anything because the model files are unchanged.
- **New, better models** usually appear as new repos: compare them (`verbalis compare`)
  and add the good ones to `RECOMMENDED` in `transcription/models.py`.

## Every time you apply a new version from a ZIP

The ZIP workflow overwrites files with the state Claude had – it does not know
about changes made on GitHub in the meantime (e.g. merged Dependabot PRs).

1. Before extracting: `git pull`.
2. Mention merged Dependabot PRs when asking for the next version, so they are
   included.
3. After extracting: `git status` / `git diff --stat` – if a file you didn't
   expect shows up (e.g. in `.github/`), check it before committing.
4. Files that were renamed or deleted in a version are **not** removed by
   extracting a ZIP; the release notes then say which files to delete.

## Releasing

1. Version in `pyproject.toml` and `src/verbalis/__init__.py`, section in `CHANGELOG.md`.
2. `pytest -q`, commit, `git tag -a vX.Y.Z -m "Version X.Y.Z"`, push commit and tag.
3. The Release workflow builds `Verbalis-X.Y.Z-setup.exe` and the experimental
   `Verbalis-X.Y.Z-macos-arm64.zip` and publishes them under **Releases** with the changelog
   section. It refuses to run if tag and version differ. If only the Mac build fails, the
   release is published with the Windows installer alone – check the macOS job's log.

## Occasionally

- **Dependencies changed in `pyproject.toml`** (new package): regenerate the exact versions
  ```bash
  pip install uv
  uv pip compile pyproject.toml --extra build --universal --python-version 3.12 \
      --no-header --annotation-style line -o packaging/requirements-build.txt
  ```
- **Python versions** (yearly, after a new Python release in October): tests run on
  3.11 and 3.13, the installer is built with 3.12. Move them up once the libraries
  support the new version.
- **Models:** check for better Swiss German models now and then and compare them
  with `verbalis compare` and the read-aloud text in `testdata/`.
- **Windows runner image:** if Inno Setup or the WebView2 parts suddenly fail in the
  Release workflow without a change on our side, GitHub has updated `windows-latest`.

## What is deliberately not automated

- **Auto-merge of Dependabot PRs:** Verbalis handles personal data and ships an
  installer; a human look at a red/green test and a major version jump is worth
  the minute.
- **Weekly checks:** monthly is enough for a project of this size; security alerts
  bypass the schedule anyway.
