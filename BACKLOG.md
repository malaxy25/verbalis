# Backlog

Open items, roughly in priority order. Done items move to `CHANGELOG.md`.
Tags: **[quality]** transcript quality · **[ux]** usability · **[ops]** build/deploy ·
**[privacy]** data protection · **[tocco]** needed before use at tocco

## Now

- [ ] **Teams call tests** – record real calls: quality of the compressed remote track, several remote speakers, Swiss German vs. Standard German speakers. **[quality]**

## Next

- [ ] **Speaker diarization** – separate remote speakers on the "other side" track (pyannote). Requires a Hugging Face token for the gated models; explain setup in the app. **[quality]**
- [ ] **Name speakers** – per transcript, play a short snippet per detected speaker and assign a name; transcript updates everywhere. **[ux]**
- [ ] **Audio playback** – click a timestamp/paragraph to hear that part; makes correcting much easier. **[ux]**
- [ ] **Standard German reference text** – second read-aloud text with reference, check that the Swiss German model does not get worse on Standard German. **[quality]**
- [ ] **WER per track** in `compare`, so microphone and Teams tests are evaluated separately. **[quality]**
- [ ] **Decide default model** after Teams tests (currently Flix-AI/flix-swissgerman-full). **[quality]**
- [ ] **Remove the migration from «Mitschrift»** once no old installations remain (≥ 1.0). **[ops]**

## Later

- [ ] **Recognize speakers across calls** – voice fingerprints. Biometric data under the Swiss revDSG: opt-in only, consent of the people concerned, deletable. **[privacy]** **[tocco]**
- [ ] **Summary and action items** via LLM – optional and off by default; local model or a provider approved by tocco. **[tocco]**
- [ ] **Resume transcription after app restart** – save progress per segment instead of starting over. **[ux]**
- [ ] **Convert models from the UI** instead of the terminal. **[ux]**
- [ ] **Search across transcripts.** **[ux]**
- [ ] **Export** to Word/PDF (copy as Markdown exists). **[ux]**
- [ ] **Import/export the correction list**, e.g. to share company terms within a team. **[tocco]**
- [ ] **i18n** – UI in English as an option. **[ux]**
- [ ] **GPU support** (CUDA) when an Nvidia GPU is available. **[quality]**
- [ ] **Echo without headset** – reduce remote voices on the microphone track. **[quality]**
- [ ] **Taskbar icon on Windows** – may still show the Python icon; set an AppUserModelID / window icon. **[ux]**
- [ ] **Ubuntu test** – PipeWire monitor source, pywebview with GTK or Qt. **[ops]**
- [ ] **macOS support** – system audio via ScreenCaptureKit or BlackHole. **[ops]**

## Before using it at tocco **[tocco]**

Devices at tocco are not centrally managed, so Verbalis is distributed as an
installer via GitHub Releases with an update notice in the app.

- [ ] **First installer test** – install the latest release in Windows Sandbox, on a second machine or in a fresh user account (without Python); check recording, transcription, shortcut, update over an existing installation and uninstall. **[ops]**
- [ ] **Offline use** – the spelling dictionary is downloaded on first use like the models; for machines without internet provide both on an internal share. **[ops]**
- [ ] **Upload the converted Flix model** to `malaxy25/flix-swissgerman-ct2` on Hugging Face (one-time; model card in `tools/flix-model/README.md`). Until then installed copies can't download Flix. **[ops]**
- [ ] **German release notes for users** – «Was ist neu» and the update dialog show the English changelog; consider a short German summary per release. **[ux]**
- [ ] **Code signing** – without a signature Windows SmartScreen warns about an unknown publisher on first install. Decide whether to buy a certificate or document the warning. **[ops]**

- [ ] Talk to IT and data protection: local processing, consent per recording, retention (audio deleted after N days).
- [ ] Check the licence situation of the default model (Flix: Apache 2.0, trained under the Swiss TDM research exception).
- [ ] Standard consent text for customer calls (German and English).
- [ ] Decide on defaults for colleagues: retention, model, storage location (not in a OneDrive-synced folder).
