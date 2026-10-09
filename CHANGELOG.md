# Changelog

## 0.7.11 – 2026-10-09
Hardening after an external review (ChatGPT, checked against the code).

**Recordings**
- Stop is checked: if a track doesn't end in time, the recording is marked «nicht sauber beendet» and not
  transcribed automatically, instead of being processed as if it were finished
- `meta.json` is written at the start (consent and start survive a crash) and atomically (never half a
  file); a damaged one is shown as such instead of looking empty. It states how the recording ended:
  complete, incomplete (device error, full disk), stop timeout or interrupted.
- **Crash recovery:** at start, recordings still marked as running are repaired (WAV headers fixed so the
  audio up to the crash is readable) and shown as «unterbrochen»
- A recording never reuses a folder (two starts in the same second) and a WAV is never overwritten
- A single rescued track can be transcribed; the transcript says which track is missing
- **Disk space:** no start below 500 MB free; below 2 GB the remaining minutes are shown; below 150 MB
  the recording is stopped and saved
- Closing Verbalis during a paused transcription ends cleanly
- The consent stored per recording includes the wording and its version

**Models and updates**
- **Model updates only after confirmation:** models are loaded from a fixed, approved revision on disk –
  faster-whisper no longer fetches newer versions on its own. At start Verbalis checks for model updates
  together with app updates and shows «Modell-Update verfügbar»; the tiles offer «Update laden» and
  «Zurück auf vorherigen Stand» (the previous revision is kept).
- Setting «Modell-Updates automatisch übernehmen» (off by default)
- App updates are checked against the size and SHA-256 that GitHub publishes for every release file, and
  against the expected file name; a mismatch deletes the download and nothing is run

**Privacy**
- Warning when the recordings folder lies in a folder synchronised by OneDrive, Dropbox, iCloud & co.
- Log export also removes audio device names and the names of the user and the others
- README: what Verbalis does with data, and what the organisation has to arrange

**Fixes**
- Release notes for the Mac no longer say BlackHole is required
- CLI: never writes into an existing folder; records how the recording ended

## 0.7.10 – 2026-10-08
- **macOS version (experimental, Apple Silicon):** the release workflow also builds `Verbalis.app`,
  self-tests it on a GitHub Mac and attaches `Verbalis-X.Y.Z-macos-arm64.zip` to the release
- **System audio on the Mac without extra software:** a small Swift helper (`tools/macos/audiotap.swift`)
  records what all programs play through a Core Audio tap (macOS 14.2+) – the counterpart of loopback
  on Windows; you keep hearing the call. It is preselected as «Systemton (alle Programme)». macOS asks
  once for permission to record audio. Older Macs can still use a virtual device such as BlackHole.
  The helper is compiled on every push on a GitHub Mac, so errors show up before a release.
- **Updates on the Mac install themselves**, like on Windows: the update notice downloads the Mac
  version, a small script waits until Verbalis has closed, swaps the app bundle (rolling back if
  anything fails) and starts the new version
- Fix: the development version (started from Python) showed the Python logo in the Windows taskbar;
  it now has its own taskbar identity. The installed version was not affected.
- Release workflow restructured: version check, Windows and macOS builds in parallel, one publish
  step; a failing Mac build doesn't block the Windows release. Tests also run on macOS.
- **`docs/TESTING.md`:** how the code is tested, what isn't covered, and a catalogue of all tests –
  generated from the tests by `tools/test_catalog.py`; CI fails if it is out of date
- **`docs/AI-CONTEXT.md`:** quick start for a new developer or AI – purpose, architecture, decisions
  and pitfalls of the ZIP workflow
- **UI preview** in the repo: `python tools/ui_preview.py` opens the interface in a browser with a
  fake backend (`tools/ui-preview/mock.js`)

## 0.7.9 – 2026-10-08
- **New test job «build versions»:** installs exactly the pinned versions of the installer
  (`packaging/requirements-build.txt`) and runs the tests. Dependabot PRs whose pin doesn't fit the
  others now turn red instead of breaking the next release. Found with PRs #2/#3: huggingface-hub 2
  is not compatible with tokenizers (requires < 2), but the tests were green because they resolve
  their own versions.
- Dependabot: one PR for Python packages instead of two identical ones; huggingface-hub ≥ 2 ignored
  until tokenizers supports it (with explanation in `.github/dependabot.yml`)
- Lint also checks `tools/`
- `MAINTENANCE.md`: what to do when a dependency PR can't be merged

## 0.7.8 – 2026-10-08
- **New recommended model «Schweizerdeutsch turbo (gcoli)»**
  (`gcoli/whisper-large-v3-turbo-swiss-german-mit`): Swiss German fine-tune of large-v3-turbo,
  on its 17-dialect test set about as accurate as large-v3 at roughly three times the speed; MIT licence
  for model and training data. Downloads ready-converted (1.6 GB).
- Models whose repo keeps the CTranslate2 version in a subfolder (`ct2/`) are supported for loading,
  download, «on this computer» and update checks
- **`compare` against your own corrected transcript:** `--reference transcript` uses the recording's
  transcript corrected in the app (also any `transcript.json`); only paragraphs within `--until` count.
  Warns if the reference was never corrected.
- **Word error rate per track** (own voice vs. Teams) when the reference is a transcript

## 0.7.7 – 2026-10-08
- **Model tiles instead of a dropdown** in the settings: one tile per model with a readable name
  («Flix Schweizerdeutsch», «Whisper large-v3 turbo»), the technical id, description, whether it is
  on this computer or the download size, revision and download date, an available update and a link
  to the model page. Click a tile (or use the arrow keys) and save to make it the default. The last
  tile is «Anderes Modell …» with the input field as before.

## 0.7.6 – 2026-10-08
- **Model updates become visible:** before transcribing, Verbalis checks whether the model files on
  Hugging Face are newer than the ones on this computer. If so, it downloads them with progress
  («Modell-Update wird heruntergeladen») and shows a notice afterwards. Changes that only touch the
  model card don't count. Applies to all downloaded models (Flix, large-v3, large-v3-turbo).
- **Settings show the model's version:** revision and download date on this computer, an available
  update, and a link to the model page on Hugging Face; the model list marks «Update verfügbar»
- **Monthly check of the Flix original** (`model-check.yml`, `tools/check_upstream_models.py`): opens
  an issue when Flix-AI publishes new model files. Our copy stays as it is until we convert, compare
  and upload a new one. Converted from revision `a9c347a` (noted in the model card).

## 0.7.5 – 2026-10-08
- Flix is downloaded from `malaxy/flix-swissgerman-ct2` – the Hugging Face account is `malaxy`
  (0.7.4 pointed to `malaxy25`, which doesn't exist on Hugging Face)

## 0.7.4 – 2026-10-08
- Fix: exporting the log failed with «ZIP-Datei (*.zip) is not a valid file filter» – pywebview
  allows no hyphen in the filter description. Regression test uses pywebview's own check.
- **Reproducible installer build:** exact versions of all build dependencies in
  `packaging/requirements-build.txt` (all platforms, generated with uv); Dependabot proposes
  updates for them monthly
- GitHub Actions updated (checkout 7, setup-python 7, upload-artifact 6, action-gh-release 3) –
  same as Dependabot PR #1
- `MAINTENANCE.md`: monthly routine, security alerts, ZIP workflow, releasing
- **Update notice:** at start Verbalis asks GitHub for the latest release (can be switched off in the
  settings, «Jetzt prüfen» checks by hand). If newer, a notice appears bottom left; the dialog shows the
  release notes and downloads and starts the installer, Verbalis closes itself. In a development
  checkout it links to the release page instead.
- **What's new:** after an update the changelog sections since the previously used version are shown
  once. `CHANGELOG.md` is bundled with the installer.
- **Models download on demand, with progress:** the model list shows which models are already on this
  computer and the download size of the others. Flix is downloaded ready-converted from
  `malaxy25/flix-swissgerman-ct2` (model card in `tools/flix-model/`) – no local conversion needed.
  Downloaded models update themselves: faster-whisper fetches a newer version when it loads them.
- **Spelling dictionary pinned** to a LibreOffice commit; a newer pin makes every installation download
  it once. A monthly GitHub Action (`dictionary.yml`) opens an issue when LibreOffice has a newer one.
- Self-test also checks the bundled changelog

## 0.7.3 – 2026-10-08
- **Own spell checking** while correcting a transcript: misspelled words are underlined, a right-click
  shows suggestions and «Als richtig merken». Swiss German dictionary (LibreOffice de_CH, «ss»
  instead of «ß»), downloaded on first use to `~/.verbalis/dictionaries` (GPL, therefore not part of
  the repo). Keywords and correction targets count as correct; own words in `~/.verbalis/words.txt`.
  Replaces the WebView2 context menu from 0.7.1, which no longer worked.
- **Pause and resume a recording:** paused time is neither recorded nor padded with silence;
  the silent-track warning ignores pauses
- **Edit the correction list in the settings:** add entries by hand, click a word to add another
  variant to it
- Version in the sidebar links to the release notes on GitHub
- Dependabot: monthly grouped update PRs for Python packages and GitHub Actions
- Self-test also checks the spelling library
- Fix: the suggestion box of an earlier edit was not removed when editing again

## 0.7.2 – 2026-10-08
- Log moved into the settings as its own tab («Allgemein» / «Protokoll»); title and tabs stay
  visible while the content scrolls
- **Release build:** on every version tag a GitHub Action bundles Verbalis with PyInstaller,
  runs a self-test of the bundle and builds a Windows installer (Inno Setup) that is published
  as a GitHub Release with the matching changelog section. Per-user install without admin rights;
  updates keep settings, corrections, models and recordings. Can also be started manually
  without publishing.
- Hidden command `verbalis selftest` checks the bundled parts (audio, silence filter, model
  runtime, UI, window and audio libraries)
- Optional dependency group `.[build]` for PyInstaller

## 0.7.1 – 2026-10-08
- **Log viewer** («Protokoll»): newest entries first, filter for warnings and errors,
  tracebacks expandable. **Export** as ZIP for bug reports – log files, version, system info and
  non-personal settings; home path replaced by `~`, no names, keywords or conversation content.
- **Spelling suggestions** when correcting a transcript: right-click a red-underlined word.
  The WebView2 context menu is enabled on Windows but suppressed outside editable fields and
  selected text.
- **Reload devices** button, e.g. after plugging in a headset
- **Warning when the others track stays silent** for a minute during a recording – usually the
  wrong output device
- **Delete a recording completely** (audio and transcript), with confirmation
- CSS grid area names in English (missed in 0.7.0)

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
