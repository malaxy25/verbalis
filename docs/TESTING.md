# Testing

How Verbalis is tested, what the tests cover – and what they deliberately don't.
The catalogue at the end is generated from the tests (`python tools/test_catalog.py`);
CI fails if it is out of date, so it always matches the code.

## Running the tests

```bash
pip install -e ".[dev]"
pytest -q
python tools/test_catalog.py   # after adding or renaming tests
```

The tests need no audio device, no model, no network and no window. They run in
seconds on Windows, Linux and macOS.

## Where tests run automatically

| Where | What |
|---|---|
| **Tests** workflow, job *tests* | every push and pull request: Windows + Ubuntu (Python 3.11, 3.13), macOS (3.12); lint (pyflakes), all tests, catalogue check – with the newest compatible library versions |
| **Tests** workflow, job *build versions* | same tests with exactly the pinned versions of the installer (`packaging/requirements-build.txt`); catches Dependabot pins that don't fit together |
| **Release** workflow | `verbalis-cli selftest` inside the bundled app on Windows and macOS: audio compression, silence filter (VAD), model runtime, UI files, window and audio libraries, spelling library, changelog |
| **Dictionary check** / **Model check** (monthly) | not tests, but watch external data: LibreOffice dictionary and the Flix original |

## How the tests are built

- **Isolated data folder:** `tests/conftest.py` points `VERBALIS_HOME` (and the old
  `MITSCHRIFT_HOME`) to a temporary folder for every test – tests never touch real
  settings, recordings or models.
- **Background threads are stopped:** every `Service` created in a test is shut down
  afterwards (`conftest.py`), otherwise its worker thread could act on the next test's files.
- **Fakes instead of hardware and downloads:**
  - recording: `FakeRecorder` writes short WAV files and reports levels (`test_service.py`);
    `FakeDevice` simulates dropouts and pauses for the real `Track` (`test_recorder.py`)
  - transcription: small fake transcribers return fixed segments, some slowly to test
    pausing and progress
  - Hugging Face: a temporary cache folder and patched `snapshot_download` / `HfApi`
  - audio devices: a fake `soundcard` module, also simulating macOS (`test_devices.py`)
  - GitHub releases: a fake URL opener (`test_updates.py`)
- **Real where cheap:** FLAC compression, resampling, WER computation, the correction
  list, Markdown/JSON output and the macOS update swap script (with fake app folders)
  run for real.
- **Regression tests** name the bug they guard against in their docstring.

## Not covered by automated tests

These need real hardware or a real system and are checked by hand (see the test plans
in the README and in `BACKLOG.md`):

- recording from real devices (microphone, WASAPI loopback, BlackHole on macOS)
- real transcription with a real model and the quality of the result
  (use `verbalis compare` with a corrected transcript)
- the window itself (pywebview / WebView2 / WebKit)
- installer and update on a clean Windows machine or Mac

**User interface:** the HTML/JavaScript UI can be opened in any browser with a fake
backend: `python tools/ui_preview.py` writes `tools/ui-preview/preview.html`
(scenarios via `#transcript`, `#recording`, `#paused`, `#news`, `#notice`, `#empty`, `#dev`).
During development every UI change was clicked through this way with Playwright.

## Catalogue

<!-- catalog:start -->
115 tests in 15 files.

### `test_app.py` (7)

Window size and position, log output without console, file dialog filter.

- **Default size without screen**
- **Adapts to scaled screen**
- **Remembered size is limited**
- **Window centered in free area**
- **Log replacement handles progress bars**
- **Zip filter is valid for pywebview** – Regression 0.7.3: «ZIP-Datei (*.zip)» was rejected by the save dialog.
- **Taskbar identity only for development version on windows** – Regression: the development version showed the Python logo in the taskbar.

### `test_audio.py` (8)

Compressing and retaining the audio files.

- **Compress wav to flac**
- **Delete audio keeps transcript**
- **Retention in days**
- **Zero days and unlimited**
- **Size limit deletes oldest first**
- **No retranscription without audio**
- **Settings validate input**
- **Size query while compressing** – Regression: GitHub Action on Windows – FileNotFoundError for gegenueber.wav.

### `test_cli.py` (7)

Run transcribe/compare with a simulated model.

- **Transcribe**
- **Compare**
- **Compare with reference**
- **Load audio resampling**
- **Selftest passes**
- **Compare with corrected transcript per track**
- **Compare warns about uncorrected reference**

### `test_corrections.py` (7)

Correction list: unique targets, variants, applying rules, suggestions from edits.

- **Target is unique variants are collected**
- **Newer correction replaces older**
- **Apply whole words and multi word variants**
- **Save and load**
- **Ignores identical words**
- **Suggestions from edit**
- **No suggestions for rephrasing and insertions**

### `test_devices.py` (3)

Device selection, including macOS where the others' voices come from a virtual input device.

- **Windows uses loopback of speakers**
- **Mac uses virtual input device**
- **Mac without virtual device explains what to do**

### `test_evaluation.py` (6)

Word error rate (WER) and loading references for model comparisons.

- **Normalize numbers and punctuation**
- **Identical**
- **Error kinds**
- **Empty hypothesis**
- **Reference from corrected transcript**
- **Reference from text file**

### `test_logs.py` (4)

Reading, filtering and exporting the log without personal data.

- **Entries newest first with details**
- **Errors only**
- **No log yet**
- **Export is anonymised and without personal settings**

### `test_mac_tap.py` (6)

macOS system audio: the recorder side of the Swift helper, with a fake helper speaking its protocol.

- **Tap device delivers blocks at the target rate**
- **Tap device reports helper errors in german**
- **Tap device notices when helper stops**
- **Mac prefers system audio when available**
- **Old mac falls back to virtual device**
- **Macos version check**

### `test_migration.py` (5)

Migration from «Mitschrift» (≤ 0.6) to Verbalis.

- **Full migration**
- **Custom recordings folder migrated in place**
- **Nothing to do without old folder**
- **Existing new files are not overwritten**
- **Missing custom folder falls back to default**

### `test_models.py` (15)

Model names, download sources and subfolders, cache detection, updates, conversion checks.

- **Builtin names and hf ids pass through**
- **Converted model is preferred**
- **Local folder without model bin**
- **Unknown name**
- **Mel bins pick base model**
- **Repo check**
- **Download sources**
- **Converted model is local and needs no download**
- **Cached model is local**
- **Download reports progress and errors**
- **Local revision from cache**
- **Page urls**
- **Upstream check script reads pins**
- **Check update ignores documentation only changes**
- **Subfolder model** – gcoli keeps the CTranslate2 version in ct2/ – Verbalis must load that, not the repo root.

### `test_recorder.py` (4)

Two-track recorder: padding dropouts with silence, pausing without padding.

- **No gap for small jitter**
- **Gap is detected**
- **Track pads dropout**
- **Pause writes nothing and pads no silence**

### `test_service.py` (22)

App flow without a window: recording → queue → transcript.

- **No recording without consent**
- **Recording to transcript**
- **Error is shown and retryable**
- **Model is reused**
- **Invalid id is rejected**
- **Save and load settings**
- **Pause and resume**
- **Automatic pause while recording**
- **Remaining time from stats and progress**
- **Edit suggest remember apply**
- **Edit validates input**
- **Keywords without duplicates**
- **Delete recording completely**
- **Cannot delete running recording**
- **Silent others track is reported**
- **Pause and resume recording**
- **Add correction by hand**
- **Spelling knows keywords and correction targets**
- **Model update is downloaded and announced**
- **No download when current or offline**
- **Model updates are listed and cached**
- **Models have readable names**

### `test_spelling.py` (5)

Spell checking with a tiny test dictionary (no download).

- **Check finds misspelled words**
- **Extra and personal words count as correct**
- **Suggestions**
- **Missing dictionary without download**
- **Outdated revision triggers new download**

### `test_transcript.py` (3)

Merging both tracks into paragraphs and the Markdown output.

- **Tracks are interleaved by time and paragraphs formed**
- **Long pause starts new paragraph**
- **Markdown format**

### `test_updates.py` (13)

Update check, installer download, macOS bundle swap, what's new from the changelog.

- **Versions**
- **Check finds newer release and installer**
- **Check same version is not available**
- **Download installer**
- **Changes between versions**
- **Bundled changelog has current version**
- **Whats new first start and after update**
- **Install update guards**
- **Update check setting is validated**
- **App bundle found from executable**
- **Mac update swaps bundle after app closed**
- **Mac update rolls back if new app missing**
- **Check picks the asset for this platform**
<!-- catalog:end -->
