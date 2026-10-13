# Backlog

Open items, roughly in priority order. Done items move to `CHANGELOG.md`.
Tags: **[quality]** transcript quality · **[ux]** usability · **[ops]** build/deploy ·
**[privacy]** data protection · **[tocco]** needed before use at tocco

## 0.7.18 – planned and decided with Andrea

Left over from the 0.7.17 plan (gcoli default, speaker box, settings tabs, levels, messages, «Audio behalten»
and model comparison were released in 0.7.17). Findings from the first real Teams calls (October 2026) and
Andrea's decisions. UI texts German, code and docs English. Show Andrea screenshots of the reading flow
before finishing.

1. **Too many speakers.** A 40-min call with 4 people on the others track gave 60+ speakers
   (threshold 0.7 was tuned on synthetic voices). Do all of:
   - field «Anzahl Personen auf dieser Spur» in the speaker box + button «Neu zuordnen»: re-runs only
     diarization with `num_clusters` = that number (no re-transcription), keeps given names where possible
   - turns shorter than ~1.5 s don't create a speaker: assign them to the most similar existing speaker
   - second pass: speakers with little talk time merged into the most similar one if close enough
   - CLI `verbalis speakers-test <folder> [--thresholds …]`: prints only numbers (speakers per threshold,
     talk time per speaker) – no content – to tune `THRESHOLD` on real calls
2. **Reading flow** (screenshot approved): split long paragraphs at sentence boundaries where another
   speaker talks in between (needs sentence timestamps – use word timestamps of faster-whisper), so a
   question appears where it was asked. Short interjections («ja», «genau», «mhm»: ≤ ~3 words or ~1 s,
   *while someone else is speaking*) get `aside: true` and are shown in a narrow grey column on the right
   of the paragraph they were said during: «Andrea: ja 00:06». On narrow windows below the paragraph.
   A short «Ja.» as a real answer stays a normal paragraph.
3. **Step-by-step transcription**: save after every finished segment (partial file next to the
   transcript), show finished parts while it runs, resume after a crash/close at the last saved point.
   Work in ~2-minute pieces cut in a speech pause (VAD), alternating both tracks so the partial view reads
   like a conversation (show only the time range done on *both* tracks). Pass the last sentences as
   prompt across cuts. Diarization and the correction list run at the end over everything.
   **Safe way decided:** finished parts are read-only while it runs; editing once it is done.

## Now

- [ ] **Teams call tests** – record real calls: quality of the compressed remote track, several remote speakers, Swiss German vs. Standard German speakers. **[quality]**
- [ ] **Correct while transcribing** – edit finished parts while a long transcription still runs; edits must survive the final diarization and correction pass. Decided against for 0.7.17 (safe way first). **[ux]**

## Next

- [ ] **Speaker diarization: test with real calls** – 0.7.16 tells speakers apart (sherpa-onnx, no token needed). Check quality with 2–4 people on Teams and with similar voices; adjust `THRESHOLD` in `diarization.py` if people are split or merged too often; measure the extra time per hour in the log. **[quality]**
- [ ] **Number of speakers from the meeting** – with meeting details (attendees) the expected number of speakers could guide the clustering. **[quality]**
- [ ] **Name speakers** – per transcript, play a short snippet per detected speaker and assign a name; transcript updates everywhere. **[ux]**
- [ ] **Audio playback** – click a timestamp/paragraph to hear that part; makes correcting much easier. **[ux]**
- [ ] **Standard German reference text** – second read-aloud text with reference, check that the Swiss German model does not get worse on Standard German. **[quality]**
- [ ] **WER per track** in `compare`, so microphone and Teams tests are evaluated separately. **[quality]**
- [ ] **Decide default model** after Teams tests: compare Flix, gcoli and large-v3 on 2–3 corrected real calls (`verbalis compare --reference transcript`, see README); also check the licence situation for tocco (gcoli: MIT chain). **[quality]** **[tocco]**
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
- [ ] **Test the Mac version on Andrea's Mac** – install, both permission prompts, recording with «Systemton» (Core Audio tap via the Swift helper), transcription, update to the next version. **[ops]**

- [ ] **Intel Macs** – only Apple Silicon is built; add an Intel build if needed. **[ops]**

## Before using it at tocco **[tocco]**

Devices at tocco are not centrally managed, so Verbalis is distributed as an
installer via GitHub Releases with an update notice in the app.

### Release checklist (from the review of 0.7.11)

Done in the code (0.7.11):
- [x] Both tracks are stopped on an error and the data recorded so far is kept
- [x] A stop timeout is never shown as a finished recording
- [x] Crash and full disk lead to a visible recovery state («unterbrochen», «unvollständig»)
- [x] Recording folders and files are never overwritten; meta.json is written atomically
- [x] App and model updates only after confirmation (models: setting for automatic, off by default)
- [x] Downloads checked against size and SHA-256 from GitHub; a failed model update keeps the old revision
- [x] Model revision fixed and reproducible, rollback to the previous one
- [x] Storage location, retention and what the organisation must arrange documented (README)
- [x] Log export without names and device names

Still open:
- [ ] Installers signed, signature checked before running (needs SignPath / Apple, see «Code signing») **[ops]**
- [x] Windows install and update tested on a second PC (9 Oct 2026, 0.7.11 → 0.7.12). Found two device bugs: no default microphone (fixed in 0.7.12) and devices whose format soundcard can't read (fixed in 0.7.13)
- [ ] macOS system audio tested on real hardware **[ops]**
- [ ] Consent and information process approved by tocco's data protection **[tocco]**
- [ ] Disk encryption, backups, leaving employees and device replacement arranged by tocco IT **[tocco]**
- [ ] Pilot with a few colleagues, results documented **[tocco]**

### Tasks

- [ ] **Installer test, part 2** – on the second PC: a full recording with transcription (after the 0.7.13 device fix), and uninstall. **[ops]**
- [ ] **Offline use** – the spelling dictionary is downloaded on first use like the models; for machines without internet provide both on an internal share. **[ops]**
- [ ] **German release notes for users** – «Was ist neu» and the update dialog show the English changelog; consider a short German summary per release. **[ux]**
- [ ] **Code signing** – Windows: SignPath Foundation offers free certificates for open-source projects (fully automated build required, each release approved by hand; SmartScreen reputation still builds up over time). macOS: Apple Developer Program (99 USD/year) for signing and notarization. **[ops]**

- [ ] Talk to IT and data protection: local processing, consent per recording, retention (audio deleted after N days).
- [ ] Check the licence situation of the default model (Flix: Apache 2.0, trained under the Swiss TDM research exception).
- [ ] Standard consent text for customer calls (German and English).
- [ ] Decide on defaults for colleagues: retention, model, storage location (Verbalis warns about synced folders since 0.7.11).
