# Verbalis – instructions for Claude Code

Read first: `docs/AI-CONTEXT.md` (purpose, architecture, decisions and why), `docs/TESTING.md`
(how tests work), and `BACKLOG.md` (open items; a section «X.Y.Z – planned and decided with Andrea» at the top
holds the agreed plan for the next version, if there is one).

## Working with Andrea

- Answer Andrea in **German** (Swiss spelling: «ss», never «ß»). He programs in Python, not in other
  languages; explain changes in plain words, not only in code.
- Before larger UI changes: show a screenshot or describe the layout and wait for his OK.
- **Push only when Andrea asks for it.** Commit with messages like `v0.7.29: …`.

## Environment (Windows, PowerShell)

- Repo: `$HOME\dev\verbalis`; virtual environment `.venv` (Python 3.14 on the new PC).
  `.\.venv\Scripts\Activate.ps1` – if scripts are blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- Install: `pip install -e ".[dev]"`. Start the app from the repo: `verbalis app`.
- Before every commit: `pytest -q`, `pyflakes src tests tools`, `python tools/test_catalog.py`
  (updates the test catalogue in `docs/TESTING.md`; CI fails if it is out of date).
- UI in a normal browser with fake data: `python tools/ui_preview.py`, then open
  `tools/ui-preview/preview.html#transcript` (other scenarios listed in `docs/TESTING.md`).
  Keep `tools/ui-preview/mock.js` in step when the Python API changes.

## Rules

- **Language:** code, identifiers, comments, docs, tests, CHANGELOG and release notes in English; everything a user reads (UI,
  messages, CLI output, transcripts) in German.
- **Releases are automatic.** A release = raise the version in `pyproject.toml` *and*
  `src/verbalis/__init__.py` + a section `## X.Y.Z – date` at the top of `CHANGELOG.md` + push to main.
  GitHub runs «1 · Tests»; only if all are green, «2 · Build & Release» builds and tags. **Never create
  or push git tags yourself** – a manual tag stops the automatic release. Published tags are protected.
- **Tests:** every bug fix gets a regression test whose docstring names the bug. Tests use no network,
  no audio hardware, no real models (see `tests/conftest.py`; diarization is faked there). Keep CI green on
  Windows, Ubuntu and macOS.
- **Privacy:** never open, read or summarise anything under `~\.verbalis\recordings` (real conversations)
  unless Andrea explicitly asks for a specific file. Logs and settings are fine.
- **Safety:** no destructive commands without asking – no `git reset --hard`, no force push, no
  recursive deletes with wildcards, no deleting files outside the repo. Scripts stop on errors.
- **macOS** can't be tested on Windows: the Swift helper is compiled in CI; ask Andrea to test on his Mac.
- **Dependencies:** new packages go into `pyproject.toml`; then regenerate the exact build versions as
  described in `MAINTENANCE.md` (`uv pip compile … -o packaging/requirements-build.txt`), keeping the
  existing pins. huggingface-hub stays below 2 for now (tokenizers).

## Useful facts

- Recordings: `~\.verbalis\recordings\<id>\` (`me.flac`, `others.flac`, `meta.json`, `transcript.json/.md`).
- Model comparison: `verbalis compare <folder> --reference transcript --until 600 --name Andrea --models …`
- Speaker diarization: `src/verbalis/diarization.py` (sherpa-onnx). Real calls give far too many speakers
  with `THRESHOLD = 0.7`; since 0.7.18 they are refined – tune with `verbalis speakers-test`.
