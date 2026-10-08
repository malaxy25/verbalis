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
  that all participants consent, start and stop with the red button.
- **Transcript:** created automatically in the background after stopping, with
  progress and remaining time. The model stays loaded, so the next
  transcription starts faster.
- **Correct:** click a paragraph, edit, save. Verbalis suggests the changed
  words for the correction list; ticked suggestions apply from then on.
- **Settings:** your name, label for the others, model, speed (accurate/fast),
  keywords, correction list, audio retention and recordings folder.

## Data

Everything lives in `~/.verbalis` (override with the `VERBALIS_HOME` environment
variable):

| Path | Content |
|---|---|
| `settings.json` | settings |
| `corrections.json` | correction list |
| `stats.json` | speed per model, for the remaining-time estimate |
| `models/` | converted models |
| `recordings/YYYY-MM-DD_HHMMSS/` | `me.flac`, `others.flac`, `meta.json`, `transcript.md/.json` |
| `verbalis.log` | log file |

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

Any Hugging Face Whisper model can be converted this way and used with
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

## Development

```bash
pytest
```

The GitHub Action runs the tests on Windows and Ubuntu with Python 3.11 and 3.13.
Open work is tracked in [`BACKLOG.md`](BACKLOG.md), changes in
[`CHANGELOG.md`](CHANGELOG.md).

## License

MIT
