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
| **1 · Tests**, job *tests* | every push and pull request: Windows + Ubuntu (Python 3.11, 3.13, 3.14), macOS (3.12); lint (pyflakes), all tests, catalogue check – with the newest compatible library versions |
| **1 · Tests**, job *build versions* | same tests with exactly the pinned versions of the installer (`packaging/requirements-build.txt`); catches Dependabot pins that don't fit together |
| **2 · Build & Release** | starts only after the Tests workflow is green for a push to main with a new version; then `verbalis-cli selftest` inside the bundled app on Windows and macOS: audio compression, silence filter (VAD), model runtime, UI files, window and audio libraries, spelling library, changelog, speaker diarization with the real models after the silence filter (both ONNX runtimes in one process) |
| **3 · / 4 · Monthly check** | not tests, but watch external data: LibreOffice dictionary and the Flix original |

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
- **Tests must not depend on the machine they run on.** Two lessons from CI (0.7.10):
  - shell scripts (the macOS update swap) can't run on Windows → `skipif(sys.platform == "win32")`
  - on GitHub's Mac the real system audio helper is present, which changes the device list →
    device tests fix `mac_tap.available` explicitly (`use(..., system_audio=...)` in `test_devices.py`)
- **Fault injection** for robustness (`test_robustness.py`): a recorder that doesn't stop
  (`FakeRecorder.hangs`), device errors, a WAV left open by a crash (header sizes zeroed),
  a cut-off `meta.json`, faked free disk space (`shutil.disk_usage` patched), a lost track.

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
(scenarios via `#transcript`, `#recording`, `#paused`, `#news`, `#notice`, `#empty`, `#dev`, `#nomic`, `#linux`).
During development every UI change was clicked through this way with Playwright.

## Catalogue

<!-- catalog:start -->
306 tests in 31 files.

### `test_acceleration.py` (10)

Experimental tests in the diagnosis: speed test, MLX wheels, notification and call-detection checks.

- **Mac wheel picks the binary for this macos**
- **Speed test uses the newest recording with audio**
- **Speed test compares cpu and graphics chip**
- **Speed test says when the gpu fell back to the cpu**
- **Speed test in the service reports numbers only**
- **Speed test refused while transcribing**
- **Failed install is shown**
- **Test notification and its click**
- **Call check lists program names only**
- **Speed test prefers a recording of at least a minute** – The first test on Windows took the newest recording: 31 s of silence, 0 words – nothing to compare.

### `test_app.py` (9)

Window size and position, log output without console, file dialog filter.

- **Default size without screen**
- **Adapts to scaled screen**
- **Remembered size is limited**
- **Window centered in free area**
- **Log replacement handles progress bars**
- **Zip filter is valid for pywebview** – Regression 0.7.3: «ZIP-Datei (*.zip)» was rejected by the save dialog.
- **Taskbar identity only for development version on windows** – Regression: the development version showed the Python logo in the taskbar.
- **App ends without python clean up only while audio is open on mac** – Regression 0.7.33: on the Mac the app sometimes crashed on quitting (after waking up) – a CoreAudio
- **Linux without gtk bindings starts qt directly** – pipx on Ubuntu: no `gi` → pywebview logged «GTK cannot be loaded» with a traceback twice before Qt.

### `test_audio.py` (10)

Compressing and retaining the audio files.

- **Compress wav to flac**
- **Delete audio keeps transcript**
- **Retention in days**
- **Zero days and unlimited**
- **Size limit deletes oldest first**
- **No retranscription without audio**
- **Settings validate input**
- **Size query while compressing** – Regression: GitHub Action on Windows – FileNotFoundError for gegenueber.wav.
- **Kept audio survives retention days and size limit** – 0.7.17 bug: a test recording was deleted by the size limit – «Audio behalten» protects it.
- **Track without any audio does not block the transcription** – 0.7.24 on macOS: recorded with the microphone only – the silent system audio track became a 0-byte

### `test_calls.py` (7)

Recognising calls: a call app uses the microphone → suggest recording (never record by itself).

- **Only call apps count and verbalis is ignored**
- **Call is suggested once and forgotten when it ends**
- **No notification when the window is in front and never a recording**
- **Suggestion offers a planned recording that is due**
- **Switched off or recording means no suggestion**
- **Asks to stop the recording when the call is over** – 0.7.26: the recognised Teams call ended – ask whether to stop the recording (never stop by itself).
- **No question without a call at the start**

### `test_cli.py` (9)

Run transcribe/compare with a simulated model.

- **Transcribe**
- **Compare**
- **Compare with reference**
- **Load audio resampling**
- **Selftest passes**
- **Compare with corrected transcript per track**
- **Compare warns about uncorrected reference**
- **Compare overall wer ignores order of overlapping speech** – 0.7.17 bug: the overall WER compared the merged conversation, so overlapping speech in a
- **Audio test reports a device without data** – verbalis audio-test: which device delivers audio – for the first tests on a Mac.

### `test_corrections.py` (7)

Correction list: unique targets, variants, applying rules, suggestions from edits.

- **Target is unique variants are collected**
- **Newer correction replaces older**
- **Apply whole words and multi word variants**
- **Save and load**
- **Ignores identical words**
- **Suggestions from edit**
- **No suggestions for rephrasing and insertions**

### `test_cuda.py` (9)

Nvidia GPU (experimental): choosing the device, CPU fallback, downloading cuBLAS/cuDNN from PyPI.

- **The wheel for this system**
- **Libraries in loading order and what is missing**
- **Device choice**
- **Gpu used when ready**
- **Too little graphics memory falls back to the cpu** – A GPU that can't hold the model (e.g. T500 with 2 GB) must not stop the transcription.
- **Gpu error while transcribing repeats on the cpu**
- **Device cuda asked explicitly does not fall back**
- **Install keeps only the libraries**
- **Install with a wrong checksum installs nothing**

### `test_details.py` (5)

Recording details (name, project, participants, notes) and planned recordings.

- **Details are saved and shown in the transcript**
- **Details survive the end of the recording** – meta.json is rewritten when a recording ends – what was entered meanwhile must stay.
- **Planned recording is recorded into with its details**
- **Planned recording can be deleted**
- **Details are saved while meta json is being read** – Windows: replacing meta.json failed while another thread had it open for a moment (WinError 5/32).

### `test_devices.py` (7)

Device selection, including macOS where the others' voices come from a virtual input device.

- **Windows uses loopback of speakers**
- **Mac uses virtual input device**
- **Mac without virtual device explains what to do**
- **Missing default device does not break the list** – Regression 0.7.11: on a PC without a default microphone both device lists stayed empty.
- **No microphone at all explains what to do**
- **Soundcard without the windows warning class** – 0.7.19 bug on macOS: «module 'soundcard' has no attribute 'SoundcardRuntimeWarning'» –
- **Microphone only choice has no second device**

### `test_diarization.py` (24)

Speaker diarization: assigning speakers, model download, transcript, naming, merging, samples.

- **Speakers numbered in order of appearance**
- **One speaker keeps the track name**
- **Segment goes to the speaker who talks most or the nearest**
- **Several voices on the microphone are persons** – 0.7.30 (Andrea): on site the others speak into the same microphone – «Andrea 1, Andrea 2» was wrong.
- **Models are downloaded once and checked**
- **Transcript has speakers of the others**
- **Switched off means no speakers**
- **Failing diarization keeps the transcript**
- **Settings switch diarization per track**
- **Speaker split setting sets the threshold** – «Sprechertrennung: Eher weniger Personen» clusters with the higher threshold – Teams calls split one
- **Asides setting is kept and checked**
- **Rename merge and reassign**
- **Track without diarization gets a speaker to name** – 0.7.38: without speaker diarization (switched off, «1 Person») the paragraphs had no speaker id – the
- **Single participant names the speaker** – Option agreed with Andrea (0.7.39): with exactly one participant entered for a track, its only speaker gets
- **Speaker sample is playable wav**
- **Reference and compare use the track not the name**
- **Merging never loses a given name** – 0.7.17: merging «Hans Muster» into the unnamed «Gegenüber 1» kept «Gegenüber 1» – the name was lost.
- **Speaker with only short turns goes to the most similar voice** – 0.7.18: a 40-min call with 4 people gave 60+ speakers – short turns created speakers of their own.
- **Small speaker merged only when the voice is close**
- **Known number of people joins the similar voices not the outliers** – 0.7.26: on site with 2 people, the clustering told «2» put nearly everything into one speaker and a few
- **Known number of people leaves fewer speakers alone**
- **Reassign with known number of people keeps given names**
- **Speakers test prints only numbers**
- **Diarization runs in its own process and reports errors** – 0.7.18 bug: sherpa-onnx blocks Python while it computes – the app froze during «Neu zuordnen».

### `test_evaluation.py` (6)

Word error rate (WER) and loading references for model comparisons.

- **Normalize numbers and punctuation**
- **Identical**
- **Error kinds**
- **Empty hypothesis**
- **Reference from corrected transcript**
- **Reference from text file**

### `test_feedback.py` (10)

«Problem melden»: building, sending and the e-mail fallback – without network.

- **Config from environment or bundled file**
- **Report needs a text and leaves out device names**
- **Too large log is not sent**
- **Send posts json with token and checks the answer**
- **Refused report does not blame the internet** – Bug (0.7.29 test): an HTTP 403 from Google (web app not open to «Anyone») was shown as
- **Contact must look like an email address** – Bug (0.7.29 test): «mail mail» was accepted as the e-mail for questions.
- **Diagnosis does not show the user name in paths** – Bug (0.7.29 test): the diagnosis sent the data folder with the account name in its path.
- **Mail link goes to the developer**
- **Service sends log and diagnosis without names**
- **Service without address offers mail only**

### `test_hardware.py` (4)

Processor, memory and graphics card in the diagnosis – with fake system commands.

- **Mac shows chip memory and graphics in the chip**
- **Failing commands give unknown instead of an error**
- **Windows reads processor memory and graphics**
- **Linux graphics card from lspci** – Ubuntu showed «Grafikkarte: unbekannt» on a ThinkPad with an Nvidia T500.

### `test_linux.py` (6)

Linux (experimental): call detection via pactl, notifications via notify-send, one app at a time.

- **Pactl lists programs using the microphone**
- **No pactl means no call**
- **Click on linux notification opens the window**
- **Hide closes the open notification**
- **Without notify send there are no notifications**
- **Second app on linux is refused**

### `test_logs.py` (5)

Reading, filtering and exporting the log without personal data.

- **Entries newest first with details**
- **Errors only**
- **No log yet**
- **Export is anonymised and without personal settings**
- **Export removes device and person names**

### `test_mac_tap.py` (7)

macOS system audio: the recorder side of the Swift helper, with a fake helper speaking its protocol.

- **Tap device delivers blocks at the target rate**
- **Tap device reports helper errors in german**
- **Tap device notices when helper stops**
- **Mac prefers system audio when available**
- **Old mac falls back to virtual device**
- **Macos version check**
- **Silent helper neither hangs nor aborts** – 0.7.23 on macOS: the system audio delivers nothing while macOS asks for the permission or nothing

### `test_migration.py` (5)

Migration from «Mitschrift» (≤ 0.6) to Verbalis.

- **Full migration**
- **Custom recordings folder migrated in place**
- **Nothing to do without old folder**
- **Existing new files are not overwritten**
- **Missing custom folder falls back to default**

### `test_mlx.py` (6)

MLX on Apple M chips (experimental): model conversion names, times after the silence filter, missing package.

- **Transformers names become mlx names**
- **Dimensions from transformers config**
- **Without mlx whisper a clear message**
- **Only speech is transcribed and times point into the recording**
- **Silence only sends nothing**
- **Model converted by 0 7 36 is renamed not converted again** – First Mac test (0.7.36): «[load_npz] Input must be a zip file» – the conversion saved

### `test_models.py` (21)

Model names, download sources and subfolders, cache detection, updates, conversion checks.

- **Downloaded models load from disk without asking hugging face** – Regression 0.7.11: faster-whisper fetched the newest model revision on every load.
- **Model not on disk is downloaded first**
- **Update keeps previous revision for rollback**
- **Rollback without previous revision explains**
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
- **New model search reports only unknown speech models**
- **Check update ignores documentation only changes**
- **Gcoli comes from our mirror** – 0.7.29: the default model is downloaded from our unchanged copy (files at the root), pinned and
- **Subfolder model** – gcoli kept the CTranslate2 version in ct2/ (until 0.7.28) – Verbalis must load that, not the repo root.
- **Default model is gcoli for new installations only** – 0.7.17: gcoli is the default for new installations; an existing settings.json keeps its model.

### `test_recorder.py` (17)

Two-track recorder: padding dropouts with silence, pausing without padding.

- **No gap for small jitter**
- **Gap is detected**
- **Track pads dropout**
- **Pause writes nothing and pads no silence**
- **Device with unreadable format records with fixed channels** – Regression 0.7.12: «AssertionError» from soundcard stopped the recording at once.
- **Device that cannot record explains why**
- **Level monitor measures without writing** – 0.7.17: levels before recording – the meter tracks read the devices but create no file.
- **Macos records without a block size** – 0.7.20 bug on macOS: «blocksize must be between 15.0 and 512» – every recording failed at once.
- **Reader gives exact blocks and never waits forever** – 0.7.22 on macOS: devices that delivered nothing made the recording hang («stop_timeout»).
- **Device without audio neither hangs nor aborts** – 0.7.23 on macOS: a recording ended after 3 s without system audio – while macOS still asked for
- **Audio that starts late is padded in sync** – The permission is granted after a moment: the silence before is filled in, the track stays in sync.
- **Measure tells a working from a silent device** – Diagnosis: which device delivers, how loud, and whether it can be closed.
- **Recorder and meters with the microphone only**
- **Lost device reconnects and keeps recording** – 0.7.34: a headset leaving hands-free mode after a Teams call ended the recording
- **Lost device without replacement gives a readable error** – The closing error (0x100000001) hid the real one (0x88890004 = device disconnected).
- **Device that never opens is not retried**
- **User is told once that a device is gone**

### `test_release_workflow.py` (7)

The release workflow: only after green tests, only for a new version, exactly the tested commit.

- **Release waits for exactly the tests workflow** – The release workflow finds the tests by name – renaming only one of them would silently stop
- **Tests run once per push to main and for pull requests**
- **Release starts after tests not on tags**
- **Every job builds the tested commit**
- **Tag only after a successful windows build**
- **Fixed download names are never taken for an update** – frehner.tech links to fixed names (releases/latest/download/…) because the GitHub API it used for the
- **Decision step**

### `test_robustness.py` (13)

Robustness of recordings: honest end states, no overwriting, crash recovery, disk space, shutdown.

- **Meta is written atomically and damage is detected**
- **Wav left open by a crash is repaired** – Regression guard: after a crash the WAV header still says 0 bytes of audio.
- **New recording never reuses a folder**
- **Recorder refuses to overwrite a wav**
- **Complete recording is marked complete**
- **Stop timeout is not treated as success**
- **Device error keeps audio and marks incomplete**
- **Single rescued track is transcribed and flagged** – Flaky on a slow macOS runner (0.7.28): transcript.json existed while the job was still finishing
- **Interrupted recording is recovered at start**
- **No recording without disk space**
- **Low disk space warns and finally stops the recording**
- **Shutdown during pause ends the worker**
- **Recovery runs before the clean up compresses audio** – Order at start matters: repair the WAV first, then the clean-up may compress it.

### `test_service.py` (42)

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
- **Model updates wait for approval by default**
- **Model update on request and state**
- **Introduction downloads a missing model ahead** – Introduction: the model download starts at the welcome step, not only after the test recording.
- **Introduction skips the download when the model is here**
- **Model rollback from settings**
- **Recordings in a synced folder are flagged**
- **Levels before recording open and close the devices** – 0.7.17: level meters while choosing devices – without recording, closed again when not needed.
- **Shutdown closes the level meters right away** – Regression 0.7.33: quitting with the level meters open left the devices to the watchdog thread;
- **Level preview with broken device does not flood the log**
- **Transcription waits for the user by default** – 0.7.18: after a meeting the number of people is entered first – transcribing starts by hand.
- **Audio clip mixes both tracks**
- **Delete waits for a file that is open for a moment** – 0.7.21 CI failure on Windows: deleting failed with «being used by another process» when the
- **Track without any audio is reported while recording** – 0.7.21 on macOS: the recording ran without sound and nothing said which device delivered nothing.
- **Diagnosis runs the steps of a recording start** – Diagnose tab: each device alone, both together, closing and reopening at once – with a report to copy.
- **Copy on macos goes through pbcopy** – 0.7.23.dev1 on macOS: «Diagnose kopieren» did nothing – WebKit refuses the clipboard after an await.
- **Microphone only recording for a meeting in a room** – 0.7.26: «Keiner – nur Mikrofon» – no second track, no warning about it, nothing reported missing.
- **Maximum recording time warns extends and ends cleanly** – 0.7.26: a forgotten recording ends after the maximum time (2 h by default) – as a complete recording.
- **Model tiles say whether the model is up to date** – 0.7.26: «Stand 540fb2e, 8.10.2026» didn't say whether it is the newest – now the tile says so.
- **Split paragraph where another person takes over** – 0.7.32: a paragraph that started with one person and went on with another (seen in a Teams call)
- **Remaining time during speaker diarization** – 0.7.32: after transcribing, the progress was near 100 % while diarization of a long call still ran

### `test_spelling.py` (5)

Spell checking with a tiny test dictionary (no download).

- **Check finds misspelled words**
- **Extra and personal words count as correct**
- **Suggestions**
- **Missing dictionary without download**
- **Outdated revision triggers new download**

### `test_stepwise.py` (5)

Step-by-step transcription: pieces cut in speech pauses, both tracks alternately, resume after a crash.

- **Cuts land in speech pauses**
- **Both tracks alternate and progress is saved**
- **Cut off transcription continues where it stopped** – 0.7.18: a crash or closing the app used to lose the whole transcription – now only the current piece.
- **Finished transcript removes the partial file**
- **Service resumes cut off transcriptions at start**

### `test_transcript.py` (12)

Merging both tracks into paragraphs and the Markdown output.

- **Tracks are interleaved by time and paragraphs formed**
- **Long pause starts new paragraph**
- **Markdown format**
- **Question appears where it was asked** – 0.7.18 reading flow: a long answer used to swallow a question asked in the middle – it came afterwards.
- **Interjection while someone speaks is an aside**
- **Asides switched off are paragraphs** – «Kurze Einwürfe am Rand zeigen» off: an interjection is a normal paragraph where it was said.
- **Short answer after a question stays a paragraph**
- **Aside in markdown and json**
- **Paragraphs keep their word timestamps** – 0.7.32: the words are saved, so a paragraph split by hand gets the time of its second part.
- **Split time comes from the words also after a correction**
- **Split time without words is estimated from the text**
- **Line breaks are kept**

### `test_ui_list.py` (1)

The recording list in the UI: groups open and close. Runs the list functions of index.html in Node.js.

- **List groups open and close again** – 0.7.27: «Diese Woche» could be closed but not opened again (only a click on «Heute» did it),

### `test_ui_speakers.py` (3)

The speaker box in the UI. Runs functions of index.html in Node.js.

- **Speaker count names the track** – 0.7.32: «Anzahl Personen auf dieser Spur ()» – the label used a variable that no longer existed.
- **Number of people offered without speakers** – Ubuntu, 0.7.36: the test recording of the introduction is transcribed with «1 Person» per track, so no
- **Generated names are recognised** – A name Verbalis gave is cleared on focus so the field lists all participants; a typed name is kept.

### `test_ui_tour.py` (1)

The introduction in the UI: its last step. Runs the tour functions of index.html in Node.js.

- **Test recording is deleted once and the step stays** – 0.7.30 draft: after «Probeaufnahme löschen» the button stayed (the step count shrank and the card was

### `test_updates.py` (28)

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
- **Download checks sha256 and size**
- **Check reads the github digest and name**
- **Mac app finds certificates** – 0.7.19 bug on macOS: the update check failed with «CERTIFICATE_VERIFY_FAILED» – the Python
- **Windows checks certificates itself** – 0.7.31 bug on a colleague's Windows PC: the update check failed with «CERTIFICATE_VERIFY_FAILED
- **Certificate path inherited from the moved app is replaced** – 0.7.28 on a new Mac: after Verbalis moved itself from the translocated copy into «Programme», the
- **App started from downloads is recognised** – 0.7.21 on macOS: «Verbalis darf /private/var/folders/… nicht ändern» – the app had been started
- **Mac app in a locked folder offers the download** – 0.7.22 on a Mac without admin rights: «Verbalis darf /Applications nicht ändern» – and no way on.
- **Test build gets the real release as update** – A test build «0.7.23.dev1» (manual build, not released) must see the release 0.7.23 as newer.
- **Where verbalis lies and where it goes** – 0.7.26: started from «Downloads», «Schreibtisch» or the disk image, Verbalis offers to move itself.
- **Move into the personal programme folder** – Andrea's case: no administrator account, Verbalis on the desktop – it ends up in ~/Applications,
- **Translocated copy moves its original from downloads**
- **Relaunch script starts the moved app**
- **Update without checksum is not downloaded** – 0.7.28: without a SHA-256 from GitHub the size alone was enough to run a downloaded installer.
- **Mac update must be signed like the running app** – 0.7.28: a downloaded Mac update was installed without checking who signed it – a compromised GitHub
- **Mac update refused when the running app is not signed**

### `test_wasapi_fix.py` (5)

Windows workaround for devices soundcard can't open (e.g. Jabra Link 380) – with a fake WASAPI.

- **Float format is packed like windows expects**
- **Devices that work are left to soundcard**
- **Unsupported device is opened with own format** – Regression 0.7.13: «Mikrofon (Jabra Link 380)» failed soundcard's format assertion.
- **Loopback flag and stereo for system audio**
- **Install only once**
<!-- catalog:end -->
