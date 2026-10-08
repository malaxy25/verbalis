# Changelog

## 0.7.0 – 2026-10-07
- **Renamed to Verbalis** (formerly «Mitschrift»): package, commands (`verbalis`, `verbalis-app.exe`),
  data folder `~/.verbalis`, window title, icon, shortcut
- **English codebase:** identifiers, file and folder names, CLI commands and options, data fields,
  comments, docstrings, README, CHANGELOG, BACKLOG. UI and user-facing messages stay German.
- CLI commands: `app`, `devices`, `record`, `transcribe`, `compare`, `models`, `convert-model`
- Data: tracks `me`/`others`, `transcript.*`, `comparison*`, `settings.json`, `corrections.json`,
  `stats.json`, `models/`, `recordings/`, `verbalis.log`
- **Automatic migration** from `~/.mitschrift`: settings, correction list, stats, converted models and
  recordings (including custom recordings folders), files and JSON fields renamed
- `tools/create-shortcut.ps1` removes the old «Mitschrift» shortcut
- Optional dependency group renamed: `.[convert]` (was `.[konvertieren]`)
- GitHub Action also runs pyflakes

## 0.6.1 – 2026-10-07
- Fix (GitHub Action on Windows): `FileNotFoundError` for `gegenueber.wav` when the list was queried
  while the background thread deleted the WAV after compressing. Affected the app as well.
  Regression test added.
- Tests shut down their background threads so they can't run into the next test
- Window opens centred in the free screen area (without taskbar)
- `BACKLOG.md` with all open items

## 0.6.0 – 2026-10-07
- Audio is compressed to 16 kHz FLAC after recording (lossless, about 85 % smaller,
  one hour ≈ 100 MB instead of ≈ 700 MB); old WAV recordings are converted afterwards
- Retention in the settings: delete audio after N days (default 3) and/or at most N MB in total
  (oldest first). Transcripts always stay, recordings without a transcript are protected.
- Cleanup on start, after every transcription and hourly
- Transcript view shows size and deletion date of the audio, button «Audio löschen»
- No «Neu transkribieren» without audio

## 0.5.1 – 2026-10-07
- Window never opens taller than the screen (considers scaling, taskbar and title bar)
- Last window size is remembered

## 0.5.0 – 2026-10-07
- Correct the transcript in the app (click a paragraph); the unedited version is kept
- Correction list: edits yield suggestions (e.g. «Toko» → «tocco») that are remembered deliberately.
  Unique target, variants collected. Applied after every transcription; targets also feed the model
  as keywords. Managed in the settings.
- «Neu transkribieren» on corrected transcripts only after confirmation
- Start by double-click: GUI launcher without console window, shortcut script, own icon
- Log file; on Windows the app can only be opened once

## 0.4.0 – 2026-10-07
- Pause and resume transcription (stops after the next text segment)
- Automatic pause while a recording runs – keeps the CPU free for the call
- Remaining time: estimated from earlier transcriptions at first, then from progress
- Paused time no longer counts as compute time
- Settings: proper model selection list, custom model via «Anderes Modell …»

## 0.3.0 – 2026-10-07
- User interface: recording with level lanes, consent per recording, automatic transcription in
  the background, history, transcript view, settings
- Settings file; default model Flix-AI/flix-swissgerman-full
- Recordings stored in the data folder by default (also for the command line)
- Speed selectable (beam size)
- Withdrawn model removed from the recommendations
- Conversion checks beforehand whether the repo contains weights
- Hugging Face notices hidden

## 0.2.1 – 2026-10-07
- Zurich German read-aloud text and Standard German reference in the test data
- Word error rate (WER) per model in the comparison
- Changelog introduced

## 0.2.0 – 2026-10-07
- Transcription with faster-whisper, silence filter against hallucinations
- Merge tracks into one conversation (Markdown + JSON)
- Model comparison, model overview, conversion of Hugging Face models
- Load audio directly with soundfile (PyAV 19 is incompatible with faster-whisper)
- GitHub Action (Windows/Ubuntu), MIT licence, `.gitattributes`

## 0.1.0 – 2026-10-07
- Two-track recording: microphone and system audio (loopback), in sync
- Command line to list devices and record, with level display and consent prompt
