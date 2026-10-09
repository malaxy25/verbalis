# Verbalis – context for a new AI (or you, in six months)

Gets you up to speed without reconstructing everything from the code. Keep it short;
update it with larger changes. Details live in README, MAINTENANCE, TESTING, BACKLOG.

## What Verbalis is

A desktop app that records conversations – the own microphone **and** the system audio
(everyone else in a Teams call) as two separate tracks – and transcribes them locally into
Standard German text, also from Swiss German. Built for Andrea Frehner, possibly for use
at tocco AG later. Everything runs on the user's computer; nothing is uploaded.

- Repo: https://github.com/malaxy25/verbalis (public, MIT)
- Releases: Windows installer + experimental macOS app, built by GitHub Actions
- Flix model copy: https://huggingface.co/malaxy/flix-swissgerman-ct2

## Language rule

Code, identifiers, file names, CLI commands, comments and docs are **English**.
Everything a user reads – UI, error messages, CLI output, transcripts – is **German**
(Swiss spelling: «ss», no «ß»). Keep both when changing anything.

## Architecture

```
src/verbalis/
  app.py           pywebview window; Api class = methods JavaScript may call
  ui/index.html    the whole UI (HTML/CSS/JS, no build step, no framework)
  service.py       logic behind the UI: recording, transcription queue (one worker
                   thread), pause, audio retention, corrections, updates, model updates
  pipeline.py      shared steps for CLI and app: audio files, meta.json, transcribing
  cli.py           command line (`verbalis …`), also used for model comparisons
  audio/           devices.py (device choice, loopback, macOS virtual device), recorder.py
  transcription/   faster.py (faster-whisper backend), models.py (sources, cache, updates)
  transcript.py    merge both tracks into paragraphs, Markdown/JSON
  corrections.py   learning correction list   spelling.py  own spell checker (Hunspell)
  evaluation.py    WER for `compare`          updates.py   GitHub releases, what's new
  logs.py          log view/export            migration.py from «Mitschrift» ≤ 0.6
  settings.py      ~/.verbalis/settings.json
packaging/         PyInstaller recipe, Inno Setup script, pinned build versions
tools/             shortcut script, upstream model check, test catalogue, UI preview
```

Data lives in `~/.verbalis/` (`VERBALIS_HOME`): settings, corrections, stats, models,
dictionaries, recordings (`me.flac`, `others.flac`, `meta.json`, `transcript.md/.json`), log.

## Decisions and why (don't undo them by accident)

- **Two tracks** instead of one mix: "me vs. others" is clear without diarization.
- **faster-whisper (CTranslate2)** on CPU; models are downloaded, never bundled.
  Default model Flix (Swiss German fine-tune); gcoli is the fast MIT-licensed alternative.
  Model choice should be based on `verbalis compare` against corrected real calls.
- **Audio** is recorded as WAV (crash-safe), then compressed to 16 kHz FLAC and deleted
  after a retention period; recordings without transcript are never deleted automatically.
- **Consent** must be confirmed before every recording (Swiss law, StGB 179ter).
- **Own spell checker** (spylls + LibreOffice de_CH dictionary, downloaded – GPL, so not
  in the repo) instead of the WebView2 context menu, which was unreliable.
- **Model updates** count only when the model files change, not the model card. Models load
  from an approved revision on disk (`models.json`), never «latest»; updates need confirmation
  (setting for automatic), the previous revision is kept for rollback.
- **Recording end states** are explicit in `meta.json` (`recording`, `complete`, `incomplete`,
  `stop_timeout`, `interrupted`); meta is written at the start and atomically; WAVs open in
  exclusive mode; interrupted recordings are repaired at start. Never present a partial
  recording as complete.
- **Review 0.7.11:** an external review (ChatGPT) was checked finding by finding; the open
  organisational items (encryption, backups, consent process, signing) are in BACKLOG.
- **Pinned build versions** (`packaging/requirements-build.txt`, generated with uv) make the
  installer reproducible; huggingface-hub ≥ 2 is ignored until tokenizers supports it.
- **macOS:** no loopback; a small Swift helper (`tools/macos/audiotap.swift`, compiled in CI,
  bundled into the app) records the system audio through a Core Audio tap (macOS 14.2+) and
  streams it to Python (`audio/mac_tap.py`). BlackHole only for older Macs. Updates swap the
  app bundle via a script. I (Claude) can't run Swift or macOS: Mac changes need Andrea's tests.
- **Not signed** yet (Windows SmartScreen / macOS Gatekeeper warn on first install).

## How work is delivered (important pitfalls)

New versions come as a ZIP from Claude and are extracted over the local repo
(`C:\Users\AndreaFrehner\dev\verbalis`), then committed, tagged and pushed.

- **Always `git pull` first**, and build new versions on the current GitHub state –
  a ZIP doesn't know about merged Dependabot PRs and would revert them.
- **Extracting a ZIP never deletes files.** Renames/removals need explicit `git rm`.
- **Never delete with wildcard commands in scripts.** A script once deleted sibling repos
  because a failed `Rename-Item`/`cd` left it in the parent folder. Scripts must stop on
  errors (`$ErrorActionPreference = "Stop"`, check `$LASTEXITCODE` after every git call)
  and only touch explicit paths.
- **Published tags are never reused or moved** (protected by a ruleset); a fix gets a new
  version number. Version lives in `pyproject.toml` and `src/verbalis/__init__.py` and must
  match the tag, plus a section in `CHANGELOG.md`.
- `main` is protected against force-push and deletion; direct pushes are fine.

## Testing

`pytest -q` (no hardware, no network). What's covered and what isn't: `docs/TESTING.md`
(catalogue generated by `tools/test_catalog.py`, checked in CI). The UI can be opened in a
browser with fake data: `python tools/ui_preview.py`.

## Where things stand

See the top of `CHANGELOG.md` for the current version and `BACKLOG.md` for what's next
(speaker diarization with naming, meeting context for notes, Mac system audio without
BlackHole, signing).
