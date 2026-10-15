# Backlog

Open items, roughly in priority order. Done items move to `CHANGELOG.md`.
Tags: **[quality]** transcript quality · **[ux]** usability · **[ops]** build/deploy ·
**[privacy]** data protection · **[tocco]** needed before use at tocco

## 0.7.28 – planned and decided with Andrea (waiting for measurements)

0.7.27 (14 Oct 2026): a known number of people joins similar voices (`merge_to_count`) – on-site
recordings with 2 and 4 people: 75 % / 90 % right instead of 56 % / 76 %. Per-turn re-assignment was
tried and dropped (not better). Idea for later: «klingt ähnlich wie …» hints when merging by hand.

1. **Settings for recognition and speakers** – in plain words, few steps, values from measurements:
   - «Sprechertrennung»: eher weniger Personen / Standard / eher mehr Personen (`THRESHOLD`)
   - «Kurze Einwürfe am Rand zeigen» (on/off)
   - «Leise oder undeutliche Stellen»: Standard / empfindlicher (VAD) – needs a `compare` option to measure
   **Waiting for recordings:** on-site (2 and 4 people) is measured. Andrea sends a Teams call with 3–4
   people and a 1:1 Teams call, transcribed without a number and every speaker named correctly; Claude
   measures how much is right per threshold (numbers only). For «Leise oder undeutliche Stellen» Claude
   first builds a comparison; the recording 2026-10-14_110111 (a quiet second speaker) may be used for it.
2. **«Transkript kopieren» with an instruction** (decided 15 Oct 2026): Einstellungen → Allgemein gets a
   text field «Anweisung beim Kopieren» (empty = copy as today). If set, the button copies the instruction,
   then the recording details (title, project, date, participants, notes), then the transcript – Andrea's
   meeting notes with Claude Code become one paste. Small hint under the button. Andrea sends his current
   notes instruction as the starting text.
3. **Done in the working copy** (for the 0.7.28 CHANGELOG):
   - The list groups open and close reliably: «Diese Woche» could be closed but not opened again, and
     «Heute» could not be closed while its recording was selected (`toggleGroup` read localStorage, which
     the app does not keep). First UI test that runs index.html code in Node.js (`tests/test_ui_list.py`).
   - GitHub release notes completely English (the install hints were German).

## After 0.7.28 – AI meeting notes (decided 15 Oct 2026: measure first, then build)

- **Test a local model first:** e.g. Qwen 3 8B (Apache 2.0) via llama.cpp on 2–3 of Andrea's transcripts,
  long ones split into parts and joined; Andrea compares with his Claude notes (are decisions and to-dos
  with owner right?). Measure time on his PC (CPU) and on the Mac.
- **Only if good enough:** «Notizen erstellen» in the transcript – background job in its own process,
  model downloaded like the Whisper models, template Zusammenfassung · Entscheide · Pendenzen (wer, bis
  wann) · offene Fragen, saved as `notes.md`, editable. Cloud (Claude API) at most as an explicit opt-in:
  real conversations would leave the computer. **[ux] [privacy]**

## Proposed (waiting for Andrea's OK)

- **«Problem melden»** (Log tab, later also next to error messages): creates the log ZIP, opens a prepared
  e-mail to andrea@frehner.tech (version, system, short template) and shows the ZIP in Finder/Explorer to
  drag into the mail. Not as a GitHub issue (public repo). Could also attach «Diagnose kopieren». **[ux]**

## Now

- [ ] **Mac: test 0.7.26** – self-install into «Programme» (from the desktop and from the DMG), and that an
  update keeps the permissions (stable signature, «Authority=Verbalis Code Signing»). **[ops]**
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
- [ ] **Call detection on macOS** – via the Swift helper (any call app using the microphone). **[ux]**
- [ ] **Planned recordings from the Outlook calendar.** **[ux]**
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
