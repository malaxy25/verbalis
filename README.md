# Verbalis

[![Tests](https://github.com/malaxy25/verbalis/actions/workflows/tests.yml/badge.svg)](https://github.com/malaxy25/verbalis/actions/workflows/tests.yml)

Verbalis records conversations – your own microphone **and** the system audio,
i.e. everyone in a Teams call – and turns them into a transcript. It understands
Standard German and Swiss German. Everything runs locally; nothing leaves the
computer.

The user interface and all user-facing messages are German, the code and the
documentation English.

## Features

- **Two-track recording:** microphone (`me`) and system audio (`others`) in sync,
  so "me vs. the others" is clear without speaker recognition.
- **Transcription in the background** with faster-whisper; Swiss German
  fine-tunes supported. Pause/resume, remaining time, automatic pause while
  recording.
- **Correcting in the transcript:** click a paragraph, fix it; Verbalis suggests
  rules for a correction list (e.g. «Toko» → «tocco») that apply to all future
  transcripts.
- **Audio retention:** compressed to 16 kHz FLAC after recording (one hour ≈
  100 MB), deleted after N days and/or above a size limit. Transcripts stay.
- **Consent** is confirmed before every recording and stored with it.

## Architecture

```
UI (HTML/JS in a pywebview window)        app.py, ui/index.html
        │  JavaScript calls Python directly
Service: recording, queue, history        service.py
Pipeline: audio files, metadata           pipeline.py
 ├─ audio/          two-track recording (microphone + loopback)
 ├─ transcription/  exchangeable backends (faster-whisper), model management
 ├─ transcript.py   merge tracks, Markdown/JSON
 ├─ corrections.py  correction list
 └─ evaluation.py   word error rate for model comparisons
```

## Setup

Python 3.11 or newer.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Ubuntu:   source .venv/bin/activate
pip install -e ".[dev]"
```

Ubuntu additionally needs PipeWire with `pipewire-pulse` (default on Ubuntu) and
GTK or Qt for the window, e.g. `sudo apt install python3-gi gir1.2-webkit2-4.1`
or `pip install pywebview[qt]`.

## Start by double-click (Windows)

Once, inside the repo with the `.venv` activated:

```powershell
pip install -e ".[dev]"
.\tools\create-shortcut.ps1
```

This creates «Verbalis» on the desktop and in the Start menu. The shortcut
starts `.venv\Scripts\verbalis-app.exe` without a console window and points to
the repo, so updates take effect immediately. Errors are logged to
`~/.verbalis/verbalis.log`. The app can only be opened once at a time.

## Using the app

- **Record:** pick the microphone and the device Teams plays sound on, confirm
  that all participants consent, start and stop with the red button. The small
  button below pauses and resumes; paused time is not recorded.
- **Transcript:** created automatically in the background after stopping, with
  progress and remaining time. The model stays loaded, so the next
  transcription starts faster.
- **Correct:** click a paragraph, edit, save. Verbalis suggests the changed
  words for the correction list; ticked suggestions apply from then on.
- **Spelling:** while correcting, misspelled words are underlined; right-click
  for suggestions or «Als richtig merken». Uses the Swiss German dictionary of
  LibreOffice (GPL), downloaded on first use.
- **Settings:** your name, label for the others, model, speed (accurate/fast),
  keywords, correction list (add entries by hand, click a word to add another
  variant), audio retention and recordings folder.
- **Updates:** Verbalis checks GitHub for a newer version at start (can be
  switched off). A notice bottom left opens the release notes and installs the
  update. After an update, «Neu in Verbalis» shows what changed.
- **Log:** the «Protokoll» tab in the settings shows the log with a filter for warnings and errors.
  «Exportieren …» saves a ZIP for bug reports – without names, paths or
  conversation content.

## Data

Everything lives in `~/.verbalis` (override with the `VERBALIS_HOME` environment
variable):

| Path | Content |
|---|---|
| `settings.json` | settings |
| `corrections.json` | correction list |
| `dictionaries/` | spelling dictionary (downloaded on first use) |
| `words.txt` | words marked as correct |
| `stats.json` | speed per model, for the remaining-time estimate |
| `models/` | converted models |
| `recordings/YYYY-MM-DD_HHMMSS/` | `me.flac`, `others.flac`, `meta.json`, `transcript.md/.json` |
| `verbalis.log` | log file, rotates at 1 MB (one backup `verbalis.log.1`) |

During a recording audio is written as WAV (crash-safe) and compressed afterwards.

**Upgrading from «Mitschrift» (≤ 0.6):** on first start Verbalis moves settings,
correction list, models and recordings from `~/.mitschrift` to `~/.verbalis` and
renames files and fields. A note file is left in the old folder, which can then
be deleted.

## Command line

Commands and options are English, output is German.

```bash
verbalis app                                   # open the UI
verbalis devices                               # list microphones and speakers
verbalis record --speakers jabra --duration 30 # record (asks for consent)
verbalis transcribe ~/.verbalis/recordings/2026-10-07_143000 --name Andrea
verbalis transcribe … --model large-v3 --keywords "tocco, Höngg" --beam 1
```

`--beam 1` is about twice as fast but slightly less accurate.

## Models and comparison

```bash
verbalis models                                # overview with status
pip install -e ".[convert]"                    # once, large (torch)
verbalis convert-model Flix-AI/flix-swissgerman-full
verbalis compare <folder> --reference testdata/reference_standard_german.txt
```

`compare` runs all recommended models on the first 3 minutes (`--until 0` for the
whole recording) and writes `comparison.md` with load time, compute time,
real-time factor and word error rate (WER), plus one transcript per model.

Models are downloaded on first use, with progress in the app; the model list in
the settings shows which ones are already on this computer. Flix only exists in
Transformers format upstream, so a ready-converted copy is provided in
`malaxy/flix-swissgerman-ct2` (model card in `tools/flix-model/`).

Model updates: before transcribing, Verbalis compares the model files on this
computer with the latest ones on Hugging Face (documentation changes don't count)
and downloads newer ones with progress and a notice. The settings show each model's
revision, download date, available updates and a link to its page on its own
tile; the chosen tile is the default model. For Flix, a
monthly GitHub Action watches the original and opens an issue when it has new model
files – our copy only changes when we convert, compare and upload a new version.

Any Hugging Face Whisper model can be converted with `convert-model` and used with
`--model <hf-id>`. The read-aloud text for tests is in
`testdata/read_aloud_zurich.md`.

All models write Swiss German as **Standard German**. That is usually what you
want for minutes, but it is a translation, not a verbatim record – correct
translations worded differently also count as errors in the WER, so compare
models relative to each other.

## Privacy and law

Recording a conversation without the consent of all participants is a criminal
offence in Switzerland (StGB Art. 179ter). Verbalis asks for consent before
every recording and stores it in `meta.json`. Recordings contain personal data;
they are excluded from the repo via `.gitignore` and deleted after the retention
period. See `BACKLOG.md` for what is still open before use at tocco.

## Releases and installer

Pushing a version tag (`git tag -a v0.7.2 …`, `git push origin v0.7.2`) starts the
**Release** GitHub Action:

1. bundles Verbalis with PyInstaller (`packaging/verbalis.spec`) into `Verbalis.exe`
   (app, no console) and `verbalis-cli.exe` (command line),
2. runs `verbalis-cli selftest` on the bundle,
3. builds `Verbalis-<version>-setup.exe` with Inno Setup (`packaging/verbalis.iss`),
4. publishes it as a GitHub Release with the matching CHANGELOG section.

The tag must match `verbalis.__version__`. The installer installs per user into
`%LOCALAPPDATA%\Programs\Verbalis` without admin rights; installing a newer
version updates in place and keeps `~/.verbalis`. Without a code signature Windows
SmartScreen warns on first install («Weitere Informationen» → «Trotzdem ausführen»).

The workflow can also be started manually (Actions → Release → Run workflow): it then
only builds and attaches the installer to the run, without publishing.

The build uses the exact versions in `packaging/requirements-build.txt`.

Local build: `pip install -c packaging/requirements-build.txt -e ".[build]"`, then
`pyinstaller packaging/verbalis.spec --noconfirm`.

## Development

```bash
pytest
```

The GitHub Action runs the tests on Windows and Ubuntu with Python 3.11 and 3.13.
Dependabot proposes grouped dependency updates once a month as pull requests;
merge them when the tests are green.
Open work is tracked in [`BACKLOG.md`](BACKLOG.md), changes in
[`CHANGELOG.md`](CHANGELOG.md), the maintenance routine in
[`MAINTENANCE.md`](MAINTENANCE.md).

## License

MIT
