# Backlog

Open items, roughly in priority order. Done items move to `CHANGELOG.md`.
Tags: **[quality]** transcript quality · **[ux]** usability · **[ops]** build/deploy ·
**[privacy]** data protection · **[tocco]** needed before use at tocco

## 0.7.19 – planned with Andrea (proposals marked «Vorschlag» still need his OK)

Build as one version. UI texts German, code and docs English. Show Andrea a screenshot or a description of
the new list, the recording form and the call notice before finishing.

1. **Recording details (metadata)** in `meta.json`, editable at the top of a recording:
   - **Name** (title), editable; default «Aufnahme Mo 13.10., 14:30». Shown in the list instead of the date,
     in the transcript header and the Markdown file. The folder name stays the id.
   - **Projekt**: free text with suggestions from earlier recordings (Vorschlag: no fixed project list).
   - **Datum und Startzeit**: from the recording; for a planned recording the planned time.
   - **Teilnehmende** per track («Am Mikrofon», «Im Call»): names, one per line or comma-separated. They
     preset «Anzahl Personen» and are offered as names in the speaker box (choose instead of typing).
   - **Notizen** (agenda, context) – later useful for a summary; never sent anywhere.
2. **Plan a recording**: a «+» in the list creates a planned recording (state `planned`, no audio yet) with
   the details above. It shows under «Geplant» at the top. Selecting it shows the details and the normal
   record button – consent is still confirmed right before recording. Recording fills this planned entry
   (same id); a planned entry that is never recorded can be deleted. Retention and clean-up ignore it.
   (Later: import from the Outlook calendar.)
3. **List grouped by time**: «Geplant», «Heute», «Diese Woche», «Letzte Woche», «Älter» (Vorschlag: «Älter»
   split by month – «September 2026», … – once it gets long). Groups can be collapsed.
4. **Recognise calls (Windows first)**: while Verbalis runs and isn't recording, check every few seconds
   whether another app uses the microphone (Windows records this in the registry: CapabilityAccessManager
   ConsentStore, the same source as the microphone icon in the taskbar). Verbalis itself is ignored (level
   meters). Then suggest «Teams-Call erkannt – aufnehmen?»: in the window as a notice; when Verbalis is
   minimised as a Windows notification. If a planned recording is due (± 30 min), the notice offers that one.
   A click opens Verbalis ready to record – **never records by itself**, consent stays a checkbox (StGB
   179ter). Only once per call, «Nicht mehr fragen» for this call; setting «Calls erkennen» (Vorschlag: on).
   macOS later via the Swift helper (any app using the microphone) – needs Andrea's test.

## Now

- [ ] **Teams call tests** – record real calls: quality of the compressed remote track, several remote speakers, Swiss German vs. Standard German speakers. **[quality]**
- [ ] **Correct while transcribing** – edit finished parts while a long transcription still runs; edits must survive the final diarization and correction pass. Decided against for 0.7.17/0.7.18 (safe way first). **[ux]**

## Next

- [ ] **Speaker diarization: test with real calls** – since 0.7.18 short-only speakers and small speakers are
  merged (`refine`) and the number of people can be given. Check with 2–4 people on Teams and with similar
  voices; tune `THRESHOLD`, `MIN_TURN_S`, `SMALL_SPEAKER_S`, `MERGE_DISTANCE` with `verbalis speakers-test`. **[quality]**
- [ ] **Reading flow: check on real calls** – are interjections recognised well (≤ 3 words or ≤ 1 s while someone
  else speaks)? How much slower are word timestamps? **[quality]**
- [ ] **License check of gcoli for tocco** (MIT chain incl. training data). **[tocco]**
- [ ] **Standard German reference text** – second read-aloud text with reference, check that the Swiss German model does not get worse on Standard German. **[quality]**
- [ ] **Remove the migration from «Mitschrift»** once no old installations remain (≥ 1.0). **[ops]**

## Later

- [ ] **Recognize speakers across calls** – voice fingerprints. Biometric data under the Swiss revDSG: opt-in only, consent of the people concerned, deletable. **[privacy]** **[tocco]**
- [ ] **Summary and action items** via LLM – optional and off by default; local model or a provider approved by tocco. **[tocco]**
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
- [ ] Check the licence situation of the default model (gcoli since 0.7.17: MIT chain; Flix: Apache 2.0, trained under the Swiss TDM research exception).
- [ ] Standard consent text for customer calls (German and English).
- [ ] Decide on defaults for colleagues: retention, model, storage location (Verbalis warns about synced folders since 0.7.11).
