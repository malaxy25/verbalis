# Verbalis – context for a new AI (or you, in six months)

Gets you up to speed without reconstructing everything from the code. Keep it short;
update it with larger changes. Details live in README, MAINTENANCE, TESTING, BACKLOG.

## What Verbalis is

A desktop app that records conversations – the own microphone **and** the system audio
(everyone else in a Teams call) as two separate tracks – and transcribes them locally into
Standard German text, also from Swiss German. Built for Andrea Frehner, possibly for use
at tocco AG later. Everything runs on the user's computer; nothing is uploaded.

- Repo: https://github.com/malaxy25/verbalis (public, MIT)
- Releases: Windows installer + macOS app (Apple Silicon, DMG + ZIP for updates), built by GitHub Actions
- Flix model copy: https://huggingface.co/malaxy/flix-swissgerman-ct2

## Language rule

Code, identifiers, file names, CLI commands, comments and docs are **English** – also CHANGELOG.md and
the GitHub release notes (with the install hints the release workflow adds), as agreed with Andrea.
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
  Default model gcoli (Swiss German fine-tune of large-v3-turbo, MIT) since 0.7.17 – best on a corrected
  real Teams call and twice as fast as Flix; Flix stays available.
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
- **Linux (experimental, since 0.7.34):** runs from the repository only, no installer/update. Loopback is
  the PipeWire/PulseAudio monitor source (soundcard). Call detection parses `pactl list source-outputs`
  (with `LC_ALL=C`), notifications use `notify-send --wait --action`, a lock file (`~/.verbalis/app.lock`,
  `fcntl.flock`) stops a second app. The device hint in the UI says «experimentell». Never run on real
  hardware by me (Claude) – Linux changes need Andrea's tests.
- **Nvidia GPU (experimental):** `transcription/cuda.py`. CTranslate2's wheels support CUDA but need
  cuBLAS 12 + cuDNN 9, too big for the installer: `verbalis gpu --install` downloads NVIDIA's wheels from
  PyPI (pinned, SHA-256 from PyPI) and keeps only the DLLs/.so files in `~/.verbalis/cuda` (pip-installed
  `nvidia-*` packages are found too). `prepare()` preloads them (ctypes, retry rounds for dependencies) so
  CTranslate2's lookup by name finds them. Device "auto" is the default everywhere; compute type
  int8_float16 (small GPUs); load or run errors fall back to the CPU (`--device cuda` doesn't). No UI yet.
- **Experimental tests in the diagnosis (0.7.36):** `acceleration.py` (status, install, speed test) and
  Service.acceleration_info/start_acceleration_install/start_speed_test/test_notification/check_calls. Add-ons
  come from PyPI via `transcription/wheels.py` (pinned version, PyPI SHA-256). MLX for the Mac app: wheels
  for its Python 3.12 unpacked into `~/.verbalis/mlx/site-cp312` and appended to sys.path – works because
  the app is not signed with the hardened runtime (library validation would block it). The speed test
  reports numbers and word agreement (1 − WER CPU vs. GPU), never text.
- **Apple GPU (experimental, measuring only):** `transcription/mlx.py` runs Whisper with mlx-whisper on
  the M-chip GPU, selected in `verbalis compare` by the prefix `mlx:`. It converts the Transformers weights
  itself (safetensors, no torch; follows mlx-examples convert.py) and uses Silero VAD from faster-whisper
  like faster-whisper does (speech only, times mapped back). No beam search, no hotwords. Not in the app
  until Andrea's measurement shows it is worth it. More CPU threads were measured and don't help.
- **soundcard on Windows** only opens devices whose mix format is float32 WAVEFORMATEXTENSIBLE (and
  its struct has wrong offsets). `audio/wasapi_fix.py` wraps its `_AudioClient.__init__`: on its assertion
  the stream is opened with an own packed float32 format and AUTOCONVERTPCM. Check this file when
  updating soundcard.
- **Speaker diarization** (`diarization.py`): sherpa-onnx with pyannote segmentation 3.0 (MIT) and
  3D-Speaker ERes2Net (Apache) – chosen because it needs no torch and no Hugging Face token. Models
  downloaded once with fixed SHA-256. Segments carry `track` and `speaker_id`; `transcript.json` has a
  `speakers` map; names are changed there. Threshold 0.7 grouped three synthetic voices correctly, but
  real calls gave 60+ speakers; since 0.7.18 `refine` gives short-only speakers to the most similar voice
  and merges small ones; «Neu zuordnen» re-runs it with a fixed number of people. Tune with
  `verbalis speakers-test` (prints numbers only). sherpa-onnx holds the GIL while computing, so the app
  runs it in a separate process (`diarization.turns_for_file`, spawn; `freeze_support()` in the packaged
  entry scripts; tests set `SEPARATE_PROCESS = False` because they fake `find_turns`).
- **Transcription starts by hand** by default since 0.7.18 (`auto_transcribe` setting): the number of
  people per track is entered first and stored in `meta.json` (`people`), used as `num_speakers`.
- **Step-by-step transcription** (0.7.18, `pipeline.transcribe`): ~2-min pieces cut in speech pauses,
  tracks alternately, progress in `transcript.partial.json` after each piece; the service resumes it at
  start. Diarization and corrections run at the end. Finished parts are read-only while it runs.
- **Reading flow** (`transcript.merge`): sentences from word timestamps form the paragraphs; short
  interjections during someone else's speech get `aside: true` (shown next to the paragraph). Since
  0.7.32 the word timestamps are kept in `transcript.json` (`words` per paragraph, about 3–4× the size) so a
  paragraph split by hand (Enter while correcting) gets the time of its second part, also after corrections
  (`transcript.split_times` compares the text with the words); old transcripts fall back to an estimate from
  the text length. The window never gets the words (`Service.transcript` drops them). Shift+Enter keeps a
  line break in a paragraph (`clean_text`; Markdown gets a hard line break).
  sherpa-onnx bundles its own onnxruntime next to faster-whisper's – the release self-test runs both
  in one process with the real models on Windows and macOS.
- **Recording details** (0.7.19) live in `meta.json` (`title`, `project`, `participants`, `notes`); they
  survive the rewrite at the end of a recording (`pipeline.DETAIL_FIELDS`). A planned recording is a folder
  with only `meta.json` and `state: planned`; recording into it keeps the id.
- **Call detection** (`audio/call_detect.py`, Windows; Linux via `pactl`): reads the microphone consent store in the registry
  (which app uses the microphone now). Only known call apps count – dictation tools and Voicemeeter use the
  microphone constantly. It only suggests; recording always needs the consent checkbox. The notification
  (`notify.py`) is a notification-area balloon via ctypes – no extra package, works without an AppUserModelID.
- **macOS signing:** every Mac build is signed with the same self-made certificate «Verbalis Code Signing»
  (GitHub secrets MACOS_SIGNING_CERT / MACOS_SIGNING_PASSWORD; Andrea keeps the .p12 in his password
  manager). macOS ties microphone/audio permissions to the signature: with ad-hoc signatures every update
  silently lost them (recordings without sound). Not notarized – Gatekeeper still warns on first start.
- **Test builds:** Actions → «2 · Build & Release» → Run workflow on a branch with version `X.Y.Z.devN`
  builds Windows and Mac without releasing (files at the run, login needed). Never push a dev version to
  main – that would release it. `updates.is_newer` sorts dev builds before the release.
- **Mac pitfalls found on real hardware (0.7.20–0.7.23):** soundcard's Windows-only warning class; no CA
  certificates in the bundled Python (certifi via SSL_CERT_FILE); blocksize is the hardware buffer (≤ 512);
  coreaudio waits forever for audio (`recorder._Reader`); App Translocation from «Downloads»; /Applications
  not writable without admin (use ~/Applications); WebKit refuses the clipboard after an await (pbcopy).
- **Mac install place** (0.7.26): outside /Applications or ~/Applications the app offers to move itself
  (`updates.move_to_applications`, relaunch script); /Applications only when writable (admin). The DMG is
  for the first download, the ZIP for self-updates.
- **«Problem melden»** (`feedback.py`, 0.7.29): POST to a Google Apps Script web app; URL and token from GitHub
  secrets → `packaging/feedback.json` (gitignored, bundled by the spec) or env `VERBALIS_FEEDBACK_URL/TOKEN`.
  Never recordings or transcripts; names and device names are removed. Script: `tools/feedback/apps-script.js`.
- **Not notarized / Windows not signed** yet (SmartScreen and Gatekeeper warn on first install).

## How work is delivered (important pitfalls)

Up to 0.7.16 new versions came as a ZIP from Claude (chat) and were extracted over the local
repo. From 0.7.17 on, Andrea works with **Claude Code in VS Code** directly in the repo
(`$HOME\dev\verbalis`); see `CLAUDE.md` for the rules. The ZIP pitfalls below still matter
whenever files are copied in from outside.

- **Always `git pull` first**, and build new versions on the current GitHub state –
  a ZIP doesn't know about merged Dependabot PRs and would revert them.
- **Extracting a ZIP never deletes files.** Renames/removals need explicit `git rm`.
- **Never delete with wildcard commands in scripts.** A script once deleted sibling repos
  because a failed `Rename-Item`/`cd` left it in the parent folder. Scripts must stop on
  errors (`$ErrorActionPreference = "Stop"`, check `$LASTEXITCODE` after every git call)
  and only touch explicit paths.
- **Releases are automatic:** raise the version (`pyproject.toml`, `src/verbalis/__init__.py`),
  add a `CHANGELOG.md` section, push. The Release workflow runs only after green Tests, only
  for a version without tag, builds the tested commit and creates the tag. Never tag by hand.
- **Published tags are never reused or moved** (protected by a ruleset); a fix gets a new
  version number.
- `main` is protected against force-push and deletion; direct pushes are fine.

## Testing

`pytest -q` (no hardware, no network). What's covered and what isn't: `docs/TESTING.md`
(catalogue generated by `tools/test_catalog.py`, checked in CI). The UI can be opened in a
browser with fake data: `python tools/ui_preview.py`.

## Where things stand

See the top of `CHANGELOG.md` for the current version and `BACKLOG.md` for what's next
(speaker diarization with naming, meeting context for notes, Mac system audio without
BlackHole, signing).
