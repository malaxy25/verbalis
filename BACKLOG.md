# Backlog

Open items, roughly in priority order. Done items move to `CHANGELOG.md`.
Tags: **[quality]** transcript quality · **[ux]** usability · **[ops]** build/deploy ·
**[privacy]** data protection · **[tocco]** needed before use at tocco

## 0.7.29 – planned and decided with Andrea (waiting for measurements)

0.7.28 (15 Oct 2026): stricter update checks (SHA-256 required, Mac: same certificate), list groups fixed.
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

## After 0.7.28 – AI meeting notes (decided 15 Oct 2026: measure first, then build)

- **Meeting notes must be generic, not tocco-specific** (Andrea, 15 Oct 2026 – how exactly is open): the
  instruction and the structure of the minutes are set in Einstellungen (e.g. several templates such as
  «Protokoll», «Kurznotiz», each with instruction + sections). Used both for «Transkript kopieren» (copy with
  the template, for Claude Code) and later for «Notizen erstellen». Not built yet – design with Andrea first.
- **Test a local model first:** e.g. Qwen 3 8B (Apache 2.0) via llama.cpp on 2–3 of Andrea's transcripts,
  long ones split into parts and joined; Andrea compares with his Claude notes (are decisions and to-dos
  with owner right?). Measure time on his PC (CPU) and on the Mac.
- **Only if good enough:** «Notizen erstellen» in the transcript – background job in its own process,
  model downloaded like the Whisper models, template Zusammenfassung · Entscheide · Pendenzen (wer, bis
  wann) · offene Fragen, saved as `notes.md`, editable. Cloud (Claude API) at most as an explicit opt-in:
  real conversations would leave the computer. **[ux] [privacy]**

## Security (from the review on 15 Oct 2026)

Done in 0.7.28: an update needs a SHA-256 from GitHub; on the Mac the new app must satisfy the running app's
code requirement (same certificate), checked in the release build with the real `codesign`.

- [ ] **GitHub account and repo** **[ops]**: two-factor / passkey on the account; protect `main` (no force
  push, no deletion); signing secrets only in a GitHub «Environment» used by the release job; pin
  third-party actions (`softprops/action-gh-release`, ideally all) to a commit SHA – Dependabot updates them.
- [ ] **Windows: check the update's signature before running it** – only possible once Windows is signed
  (see «Code signing»). **[ops]**
- [ ] **Recordings at rest** are not encrypted: rely on BitLocker/FileVault (document for users and tocco IT);
  later maybe «Audio nach N Tagen löschen». **[privacy]**

## Proposed (waiting for Andrea's OK)

- **«Problem melden»** (Log tab, later also next to error messages): creates the log ZIP, opens a prepared
  e-mail to andrea@frehner.tech (version, system, short template) and shows the ZIP in Finder/Explorer to
  drag into the mail. Not as a GitHub issue (public repo). Could also attach «Diagnose kopieren». **[ux]**

## Now

- [ ] **Mac: test 0.7.26–0.7.28** – self-install into «Programme» (from the desktop and from the DMG), and that
  the update to 0.7.28 works (now checks the certificate) and keeps the permissions. **[ops]**
- [ ] **Teams call quality** – compressed remote track, Swiss German vs. Standard German speakers
  (speaker measurements: see the 0.7.29 plan). **[quality]**
- [ ] **Correct while transcribing** – edit finished parts while a long transcription still runs; edits must survive the final diarization and correction pass. Decided against for 0.7.17/0.7.18 (safe way first). **[ux]**

## Next

- [ ] **Reading flow: check on real calls** – are interjections recognised well (≤ 3 words or ≤ 1 s while someone
  else speaks)? How much slower are word timestamps? **[quality]**
- [ ] **Standard German reference text** – second read-aloud text with reference, check that the Swiss German model does not get worse on Standard German. **[quality]**
- [ ] **Remove the migration from «Mitschrift»** once no old installations remain (≥ 1.0). **[ops]**

## Later

- [ ] **Recognize speakers across calls** – voice fingerprints. Biometric data under the Swiss revDSG: opt-in only, consent of the people concerned, deletable. **[privacy]** **[tocco]**
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
- [ ] Installers signed, signature checked before running (needs SignPath / Apple, see «Code signing»). Mac
  updates check the own certificate since 0.7.28. **[ops]**
- [x] Windows install and update tested on a second PC (9 Oct 2026, 0.7.11 → 0.7.12). Found two device bugs: no default microphone (fixed in 0.7.12) and devices whose format soundcard can't read (fixed in 0.7.13)
- [x] macOS system audio tested on real hardware (Andrea's Mac, 14 Oct 2026, 0.7.24)
- [ ] Consent and information process approved by tocco's data protection **[tocco]**
- [ ] Disk encryption, backups, leaving employees and device replacement arranged by tocco IT **[tocco]**
- [ ] Pilot with a few colleagues, results documented **[tocco]**

### Tasks

- [ ] **Installer test, part 2** – on the second PC: a full recording with transcription (after the 0.7.13 device fix), and uninstall. **[ops]**
- [ ] **Offline use** – the spelling dictionary is downloaded on first use like the models; for machines without internet provide both on an internal share. **[ops]**
- [ ] **German release notes for users** – «Was ist neu» and the update dialog show the English changelog; consider a short German summary per release. **[ux]**
- [ ] **Code signing** – Windows: SignPath Foundation offers free certificates for open-source projects (fully automated build required, each release approved by hand; SmartScreen reputation still builds up over time). macOS: Apple Developer Program (99 USD/year) for signing and notarization. Alternative for Windows: Certum «Open
  Source Code Signing» (about 50–100 EUR/year, cloud key usable from CI). Notarization needs more than the
  certificate: hardened runtime (`--options runtime`), `--timestamp`, every binary in the PyInstaller bundle
  signed on its own instead of `--deep`, entitlements for audio input (maybe more for Python). Changing
  the certificate makes macOS ask for the permissions once more. **[ops]**

- [ ] Talk to IT and data protection: local processing, consent per recording, retention (audio deleted after N days).
- [x] **Licence of the default model gcoli checked (15 Oct 2026):** model MIT; base `whisper-large-v3-turbo` MIT;
  training data FHNW/i4ds Swiss Parliaments Corpus (Bern) and Gemeinderat Zürich corpus MIT (stated on
  cs.technik.fhnw.ch/i4ds-datasets); pseudo-labels from `whisper-large-v3` (Apache 2.0); commercial use
  permitted; attribution to FHNW/i4ds in the README. Remaining small risks: the dataset on Hugging Face
  (i4ds/SPC) shows no licence tag – the MIT statement is only on the FHNW page (archive it, or ask FHNW for a
  written confirmation if tocco wants certainty); gcoli is an individual account (created Sept 2026), so
  the claims can't be verified further – Verbalis pins the revision. Flix (Apache 2.0) was trained under the
  Swiss TDM research exception – not the default any more.
- [ ] **Mirror the pinned gcoli revision** under `malaxy/` (MIT allows it, with licence and attribution), so
  the default model can't disappear or change upstream. **[ops]**
- [ ] Standard consent text for customer calls (German and English).
- [ ] Decide on defaults for colleagues: retention, model, storage location (Verbalis warns about synced folders since 0.7.11).
