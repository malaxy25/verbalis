# Changelog

## 0.7.32 – 2026-10-20
- **Split a paragraph:** while correcting, Enter splits the paragraph at the cursor – e.g. where another
  person takes over – and the choice of person for the second part opens right away. Shift+Enter is a line
  break within a paragraph (kept in the Markdown file too); Ctrl+Enter saves as before.
- **Word timestamps are kept** in new transcripts, so the second part of a split paragraph starts at its
  first word, also after corrections. Older transcripts get an estimate from the text length.
- **Time left during speaker diarization:** after transcribing, the app said «noch weniger als eine Minute»
  while the speakers of a long call were still recognised for minutes; the estimate now comes from the
  speaker recognition itself.
- **Participants in the speaker box:** the names entered for a track can be picked from «Teilnehmende ▾».
- **Participants and notes:** the fields can be pulled wider, not only taller; with notes, «Teilnehmende und
  Notizen» is open in the transcript.
- **New Swiss German models:** a monthly check on Hugging Face opens an issue for speech recognition models
  we haven't looked at yet (`tools/find_new_models.py`, `tools/known-models.txt`).

## 0.7.31 – 2026-10-19
- **Setting «Sprechertrennung»** (Einstellungen → Sprecher): «Standard» or «Eher weniger Personen». Measured on
  two Teams calls and two on-site meetings: Teams splits one person into 7–19 speakers but hardly ever mixes
  two people; «Eher weniger Personen» gives fewer duplicates, but similar voices in the same room are mixed
  a little more often. Also used by «Neu zuordnen».
- **The number of people is the reliable way:** with it, Teams calls were 99–100 % right. Before
  transcribing, a track whose voices are not told apart in the settings now shows «1»; the number entered
  there overrides the setting for that recording – explained in the settings and in the introduction
  («Wer spricht?»).
- **Setting «Kurze Einwürfe am Rand zeigen»** (on by default): switched off, «ja», «genau», «mhm» become
  paragraphs of their own where they were said. Applies to new transcripts.

## 0.7.30 – 2026-10-17
- **Introduction for new users:** on the first start without recordings a short guided tour in 11 steps –
  your name, microphone and Systemton checked with the real level meters (test tone), a test recording that
  is transcribed while the settings, the model, the speakers and «Problem melden» are explained. The model
  download starts right at the welcome step. The test recording is deleted afterwards (with a confirmation).
  Shown again via Einstellungen → Allgemein → «Einführung zeigen».
- **Clearer track and speaker names:** the two tracks are called «Mikrofon» and «Systemton» everywhere
  (level meters, settings, «Personen am …»). A single voice stays «Ich» (or the name from the settings) /
  «Gegenüber»; several voices on the microphone – e.g. on site – become «Person 1, 2, …» instead of
  «Ich 1, 2, …», on the Systemton «Gegenüber 1, 2, …». Existing transcripts keep their names.
- **The Mac version is no longer experimental.** README and release notes explain the first start
  («Dennoch öffnen»).

## 0.7.29 – 2026-10-15
- **«Problem melden»** in Einstellungen → Log and Diagnose: a short text, optionally an e-mail address for
  questions, the log and the diagnosis – sent directly to the developer with one click (names, device names
  and paths removed; never recordings or transcripts). Without internet: «Per E-Mail …». The dialog confirms
  in green when the report has arrived, and checks the e-mail address.
- **The diagnosis shows processor, memory and graphics card** – transcription speed depends on them. The
  user name in folder paths is replaced by `~` when a report is sent.
- **Mac: the first model download failed after Verbalis had moved itself into «Programme»** («[Errno 2] No such
  file or directory»): the restarted app had inherited a certificate path into the vanished temporary copy.
- **The default model now comes from our own unchanged copy on Hugging Face**
  (`malaxy/whisper-large-v3-turbo-swiss-german-ct2`), pinned to the tested version and compared monthly with
  the original – it can't disappear or change unnoticed. Installations that already have it download it
  once more (1.6 GB).
- Licence of the default model checked (MIT including the training data); FHNW/i4ds credited in the README.

## 0.7.28 – 2026-10-15
- **Updates are checked more strictly.** Without a SHA-256 from GitHub an update is no longer downloaded
  (until now the size alone was enough). On the Mac the downloaded app must be signed with the same
  certificate as the installed one – so a compromised GitHub account alone cannot ship an update. The
  release build checks this with the real `codesign`.
- **The groups in the list open and close reliably:** «Diese Woche» could be closed but not opened again,
  and «Heute» could not be closed while its recording was selected.
- **Release notes on GitHub completely in English** (the install hints were German).

## 0.7.27 – 2026-10-14
- **A known number of people now helps instead of hurting.** Until now «2 Personen» was handed straight
  to the speaker clustering – in an on-site meeting it put nearly everything into one speaker and a few
  coughs into the other (56 % right). Now the speakers are found as without a number and the most similar
  voices are joined until the number is reached; small groups such as coughs never count as a person.
  Measured on two on-site recordings (2 and 4 people): 75 % and 90 % right instead of 56 % and 76 %.

## 0.7.26 – 2026-10-14
- **«Keiner – nur Mikrofon»** under «Ton der anderen kommt über», for a meeting in a room: only the
  microphone track is recorded – no warning about the system audio, nothing reported as missing.
- **Maximum recording time** (Einstellungen → Allgemein, 2 hours by default) in case the stop is forgotten:
  5 minutes before, a notice with «+30 Min.»; then the recording ends cleanly and complete.
- **When the recognised call is over** (Windows): «Der Teams-Call ist zu Ende – Aufnahme beenden?» with
  «Beenden» / «Weiter aufnehmen». Verbalis never stops by itself.
- **Model tiles say whether the model is up to date:** «✓ Neuester Stand vom … – geprüft heute 14:05»,
  «Update verfügbar» or «Nicht geprüft – keine Verbindung»; «Jetzt auf Updates prüfen».
- **Mac: Verbalis puts itself into «Programme».** Started from «Downloads», the desktop, «Dokumente» or the
  disk image, it offers once to move itself – into /Applications with administrator rights, otherwise into
  the personal «Programme» folder – and starts again from there. No more «Verbalis 2», no read-only copy,
  updates work without an administrator account. New: a **DMG** for the first download; the ZIP stays for
  the automatic updates.

## 0.7.25 – 2026-10-14
- **A track without any audio no longer blocks the transcription** (on all systems): recorded with the
  microphone only, the silent system audio track became an empty file and transcribing failed with «Format
  not recognised». Such a track is now left out; the transcript notes it is missing. Recordings already made
  with 0.7.24 can be transcribed after the update.

## 0.7.24 – 2026-10-14
- **macOS: recordings no longer stop when a track is quiet for a moment.** 0.7.23 ended a recording after
  3 seconds without audio – but macOS delivers nothing while it still asks for the permission, and the
  system audio apparently nothing while nothing plays. Now Verbalis keeps recording, fills such gaps with
  silence once audio comes again (both tracks stay in sync) and can still be stopped at once. If a track
  delivers nothing at all for 5 seconds, a notice says so – the recording goes on.

## 0.7.23 – 2026-10-14
Recording works on the Mac (tested on a MacBook Air with macOS 14.6, without an administrator account):
- **macOS keeps its permissions across updates:** every Mac build is now signed with the same Verbalis
  certificate. Until now each update counted as a new app, and macOS silently gave it no access to the
  microphone and the system audio (recordings without sound). Updating to 0.7.23 asks once more; after that
  the permissions stay. The first start still shows the Gatekeeper warning (that needs a paid Apple account).
- **A device that delivers nothing no longer hangs the recording:** after 3 seconds without any audio
  Verbalis stops with a clear message instead of waiting forever (it could not be stopped then).
- **New settings tab «Diagnose»:** system and device information, an audio test in steps (microphone alone,
  system audio alone, both, closing and reopening as when a recording starts), an internet check and
  «Diagnose kopieren» for an e-mail – device names, no conversation content.
- **«Kopieren» works on the Mac** (diagnosis and transcript): the Mac's window refused the clipboard.
- macOS: when Verbalis can't replace itself (no administrator account or started from «Downloads»), the
  update dialog says why and offers «Download öffnen». Without an administrator account, put Verbalis into
  the personal «Programme» folder in the home folder – there it updates itself.
- Test builds (e.g. 0.7.23.dev1, built by hand on GitHub without a release) get the next release as update.

## 0.7.22 – 2026-10-13
Help for finding out why a Mac recording stays silent:
- **Warning while recording** when a track delivers no audio data at all after a few seconds – with the
  device name (silence still arrives as data, so this means the device or the system blocks it). The log
  also says which track did not end when a recording can't be stopped cleanly.
- New command `verbalis audio-test`: opens the microphone and the others' audio one after the other and
  shows whether audio arrives, how loud, and whether the device hangs – nothing is recorded or saved. On a
  Mac: `/Applications/Verbalis.app/Contents/MacOS/verbalis-cli audio-test` in the Terminal.
- macOS: a clear message when Verbalis was started straight from «Downloads» and can't update itself –
  move it to «Programme».

## 0.7.21 – 2026-10-13
- **macOS: recording failed at once** («blocksize must be between 15.0 and 512»). On the Mac the block size
  sets the hardware buffer, which may be at most 512 frames; Verbalis asked for 0.1 s. It is now only given
  on Windows; the recording still works in 0.1-second blocks on both. Windows is unchanged.
- Windows: deleting a recording or saving its details could fail with «being used by another process»
  when the background clean-up was reading the same file at that moment; Verbalis now tries again
  shortly instead of showing an error.

## 0.7.20 – 2026-10-13
First test on a real Mac – two fixes:
- **macOS: audio devices were not found** («module 'soundcard' has no attribute 'SoundcardRuntimeWarning'»),
  so nothing could be recorded. The warning class only exists in soundcard's Windows part.
- **macOS: downloads failed** («CERTIFICATE_VERIFY_FAILED»): the update check, the speaker-diarization models
  and the spelling dictionary. The Mac app now uses the certificate list of certifi.
- The release self-test now checks both on the Mac build.
- README: badges for Build & Release, Dependabot and the latest version

## 0.7.19 – 2026-10-13
- **Details per recording:** name (editable, shown in the list, the transcript and the Markdown file),
  project (free text with suggestions from earlier recordings), date and start time, participants per track
  («Am Mikrofon», «Im Call») and notes. Participants preset the number of people and can be chosen as
  names in the speaker box. Details entered during a recording are kept.
- **Plan a recording:** «+» in the list creates a planned recording with all details. At the meeting select
  it, confirm consent and record – the audio goes into that entry.
- **List grouped by time:** «Geplant», «Heute», «Diese Woche», «Letzte Woche», then by month; groups can be
  collapsed.
- **Calls are recognised (Windows):** when Teams, Zoom, Webex, Slack, Skype, Discord or a browser uses the
  microphone, Verbalis suggests recording – in the window, or as a Windows notification when it is in the
  background (a click brings Verbalis to the front). A planned recording due within 30 minutes is offered.
  Verbalis never records by itself; consent is still confirmed with the checkbox. Dictation tools and audio
  mixers are ignored. Setting «Calls erkennen» (on by default).

## 0.7.18 – 2026-10-13
- **Step-by-step transcription:** long calls are transcribed in pieces of about two minutes, cut in speech
  pauses, both tracks alternately. What is finished shows below the progress bar while it runs (read-only,
  only the time range done on both tracks). After each piece the progress is saved: if Verbalis crashes or
  is closed, the transcription continues at the next start where it stopped instead of from the beginning.
  The end of the previous piece is given to the model as context, so names stay consistent across the cuts.
- **Reading flow:** paragraphs are split at sentence ends (word timestamps), so a question appears where it
  was asked, not after the whole answer. Short interjections («ja», «genau», «mhm») said while someone else
  is talking are shown small in a grey column next to that paragraph (below it in narrow windows); a short
  «Ja.» as a real answer stays a normal paragraph. In the Markdown file they are written in italics.
- **Fewer wrong speakers:** a speaker who only ever says something short (under 1.5 s) is given to the most
  similar voice, and speakers with little talk time are merged into a similar voice. A real call with 4
  people had shown more than 60 speakers.
- **«Anzahl Personen auf dieser Spur» + «Neu zuordnen»** in the speaker box: tells the speakers of a track
  apart again with a known number of people – without transcribing again; corrections stay and given
  names go to the matching new speaker.
- New command `verbalis speakers-test <folder> [--thresholds …]`: how many speakers each threshold finds and
  their talk time – only numbers, no content – to tune the threshold on real calls
- **Transcribing starts by hand** after a recording (new setting «Sofort automatisch transkribieren», off
  by default): first enter how many people spoke on each track («Personen am Mikrofon», «Personen über
  Gegenüber»; empty = find out, 1 = nobody to tell apart), then «Transkribieren». The numbers are kept for
  «Neu transkribieren».
- **The app no longer freezes** while speakers are told apart: sherpa-onnx blocked all of Verbalis while it
  computed, so the diarization now runs in a separate process. «Neu zuordnen» runs in the background with
  a progress bar and waits while a recording runs.
- **▶ next to every paragraph** plays that passage (both tracks together), as long as the audio exists

## 0.7.17 – 2026-10-13
- **Default model gcoli** (`gcoli/whisper-large-v3-turbo-swiss-german-mit`) for new installations: on a
  corrected real Teams call it made the fewest errors (me 14.1 %, others 10.4 %) and was twice as fast as
  Flix (0.82× real time). Existing installations keep the model chosen in their settings.
- **Settings with tabs:** «Allgemein», «Transkription», «Sprecher», «Aufbewahrung», «Updates», «Log»; uses
  the width of the screen (two columns where it fits). Closes with Escape or a click outside – if something
  was changed, it first asks «Änderungen speichern?»
- «Protokoll» is now called **«Log»** (tab, «Log exportieren», export file `verbalis-log-….zip`)
- **Level meters before recording:** both levels show while choosing devices, without recording. The
  devices are only open while the window is in front and was used during the last minute.
- **«Audio behalten»** per recording, in the new «⋯» menu (with «Ordner öffnen», «Audio löschen»,
  «Aufnahme löschen»): protects its audio from deletion by retention days and the size limit; kept audio
  doesn't count towards the limit. The audio line then says «wird behalten».
- **Speaker box:** names save themselves when the field is left (no more «Namen speichern» button);
  «Gleiche Person wie …» instead of «Zusammenlegen mit …», listing the names as typed; merging never loses a
  given name (if both have one, the chosen person's name stays); list sorted by talk time and scrollable;
  play buttons disabled with an explanation once the audio is deleted
- The red message bar can be closed and disappears after 15 seconds (an «Audio … gelöscht» message stayed
  forever)
- Model comparison: the overall error rate is computed from the two tracks – the merged order of
  overlapping speech made it higher than both tracks

## 0.7.16 – 2026-10-09
- **Speakers on the Teams track:** Verbalis tells the other participants apart and labels them
  «Gegenüber 1», «Gegenüber 2», … Above the transcript a «Sprecher» box lets you play a short sample of each
  person, give names (written into the transcript and the Markdown file) and merge two speakers that are the
  same person. Clicking a name in the text moves a paragraph to another speaker of the same track.
- Settings: «Sprechererkennung» for the others (on by default) and for the own microphone (off; for meetings
  in a room where everybody speaks into the same microphone)
- Uses sherpa-onnx (Apache 2.0) with pyannote segmentation 3.0 (MIT) and 3D-Speaker ERes2Net (Apache 2.0);
  the two models (about 46 MB) are downloaded on first use with fixed SHA-256. No torch, no account needed.
  In a test with three synthetic voices all turns were assigned correctly.
- Voice prints are only used within one recording and never stored
- If diarization fails, the transcript is kept without speakers and says why
- Model comparison (`compare`) counts the error rate per track by the track, not the speaker name
- Release self-test runs the real diarization models after the silence filter on Windows and macOS (two
  ONNX runtimes in one process)

## 0.7.15 – 2026-10-09
- **Releases happen automatically after green tests:** raise the version, add a CHANGELOG section and
  push – no more manual tags. The Release workflow starts when the Tests workflow has finished; it only
  continues if all tests passed for a push to main and the version has no tag yet. It builds exactly the
  tested commit, creates the tag only after the Windows build succeeded, and stops with a clear message
  if the CHANGELOG section is missing. Pushes without a new version release nothing.
- Tests for the release workflow itself (`test_release_workflow.py`), including its decision step
  against a local git repository
- Clearer GitHub Actions list: numbered workflows («1 · Tests», «2 · Build & Release», «3 · / 4 · Monthly
  check …») and run titles that start with the type («Tests: …», «Build & Release: …»). Tests run once per
  push to main (no second run for the tag) and for pull requests. A test makes sure the release workflow
  refers to the tests by their exact name.

## 0.7.14 – 2026-10-09
- Fix: devices that report a plain audio format, such as the **Jabra Link 380** in hands-free mode, still
  couldn't be recorded. The audio library only accepts one specific format (and describes it with wrong
  memory offsets). When it fails, Verbalis now opens the device with a correctly packed 32-bit float format
  of its own and lets Windows convert (`audio/wasapi_fix.py`). Devices that already worked are untouched.

## 0.7.13 – 2026-10-09
- Fix: on some devices a recording stopped at once with «Gerätefehler: AssertionError()». The audio
  library can't read the format some devices report (e.g. Bluetooth headsets in hands-free mode, some
  USB devices) and fails a check. Verbalis now retries with a fixed channel count (microphone mono,
  system audio stereo – Windows converts the format); if that fails too, it says in plain words which
  device can't be recorded and what to do. Found on a second PC.
- Device errors are shown as readable text instead of e.g. «AssertionError()», and the log contains
  the full traceback of every track error (so the next unknown device problem can be diagnosed)
- Tests also run on Python 3.14

## 0.7.12 – 2026-10-09
- Fix: on a PC without a default microphone (or speakers) both device lists stayed empty with
  «Error 0x80070490» (Windows: element not found). Verbalis now takes the first device when no default
  is set, lists the other kind of device anyway, and explains in plain words what to do when there is
  no microphone at all (connect one, allow microphone access for desktop apps in Windows privacy settings).
  Found by installing the release on a second PC.

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
