# Backlog

Open items, roughly in priority order. Done items move to `CHANGELOG.md`.
Tags: **[quality]** transcript quality · **[ux]** usability · **[ops]** build/deploy ·
**[privacy]** data protection · **[tocco]** needed before use at tocco

## Current state (25 Nov 2026)

- **Released 0.7.47 and 0.7.48 (24 Nov 2026):** devices (microphone, system audio, screen) switch during a
  recording (`Track.switch`, `Service.switch_device` / `switch_screen`); one search for everything (no more scope
  switch) that also finds notes, speaker names and date/folder name and says where («Gefunden in»; details first);
  progress of speaker jobs shows the percentage once; «Beta» badge on experimental features (`BETA` in index.html:
  screens, device_switch) with «Rückmeldung geben» → prefilled «Problem melden», setting `experimental` hides them.
- **0.7.48 has no Mac build:** GitHub cancelled the macOS job after 15 min without running a step (no runner).
  Macs stay on 0.7.47 and the fixed link `releases/latest/download/Verbalis-Mac.dmg` is broken until a release
  with a Mac build. Proposed to Andrea: a 0.7.49 right away («Mac-Build nachgeliefert») – no answer yet.
- **Snapshots planned (25 Nov):** six items agreed in «Next – snapshots» below (view = the AI's choice,
  panel «Bilder» per mockup, pause button, suggest the meeting window, picture count, edit title while
  transcribing). Proposed start: items 1 and 5 – waiting for Andrea's go.
- **Next step:** Andrea tests the device switch in a real Teams call (headset ↔ laptop, screen ↔ window, see
  `docs/TESTING.md`) and gives feedback; then decide 0.7.49. Still open from 0.7.46: in-app tests of snapshots
  and «Für KI kopieren»; Mac: rail/Cmd+B, snapshots, `caffeinate`, «heraustrennen».
- **Code signing:** SignPath application sent (waiting for the answer); Apple Developer Program on hold (CHF 109).
  See the «Code signing» item below and `docs/CODE-SIGNING.md`.
- **Open questions for Andrea:** 0.7.49 now for the Mac build, or with the next change?
- **Prerequisites / start check:** restart Verbalis after a pull (start menu runs the repo `.venv`).
- **Decided:** no video recording; Markdown + picture folder; one search field (Andrea 24 Nov); «Nur Mikrofon»
  can't be switched during a recording; no client-side encryption needed elsewhere.
- **Later:** adding system audio to a microphone-only recording mid-way (second step of the switch); OCR on the
  snapshots; diarization during a recording parked (needs the whole recording).

## Next – snapshots (planned with Andrea 25 Nov 2026)

Seen in the recordings «SBV LA» and «Halle 44» of 25 Nov (whole screen captured, not the Teams window): before
anyone shares, pictures come from windows moving/opening on the desktop (SBV 7 before 02:09 + 3 after the end;
Halle 44 ~24 before 07:52, including unrelated windows – editor, browser). Not the faces: the video tiles are
ignored already. An automatic «everything moves = no picture» rule only helps when the meeting window is captured.

1. **Transcript view shows what the AI gets** – the chosen, cropped pictures (`screens_crop/`) instead of all
   originals (`service.py` `data["screens"]` uses `screens.listing`; `image_path` only allows `screens/`), so one
   sees what was dropped. **[ux]**
2. **Panel «Bilder» with all pictures** (mockup agreed 25 Nov) – collapsed like the speaker box, summary line
   «16 – 9 im Transkript, 7 nicht verwendet». Grid of all pictures: used ones marked green «im Transkript» (« (von
   Hand)» if added by hand), left-out ones faded with the reason (nur kurz gezeigt / gleich wie 03:13 / von Hand
   weggelassen). Filters: Alle (default), Im Transkript, Nicht verwendet, per reason. Multiple selection; buttons
   «n ins Transkript» (sorted in at its time), «n weglassen», «n endgültig löschen» (asks, deletes the file –
   privacy, Halle 44). In the transcript, hovering a picture shows «Original» and «Weglassen». Undo for 5 s after
   moving (not after deleting). Manual choices stored in `screens_crop/index.json` (forced in/out) so a new
   `prepare` (other `min_shown_s`) keeps them; transcript.md rewritten. **[ux] [privacy]**
3. **Button «Bilder pausieren / fortsetzen»** during a recording, audio keeps running; setting «Bilder erst nach
   Klick starten» (recording begins without pictures). **[ux] [privacy]**
4. **Suggest the meeting window** – when a call window is recognised (`meeting_kind`, `call_detect`) while the
   whole screen is captured: hint «Teams-Meeting erkannt – Bilder nur vom Meeting-Fenster?» [Wechseln]
   (`switch_screen` exists). Test first: does PrintWindow capture the new Teams call window (GPU, maybe black)?
   When Andrea shares himself, Teams shrinks to a bar – then the whole screen is right, so only a suggestion,
   never automatic. Windows only (Mac has no window capture). **[ux]**
5. **Overview: number of pictures** – «Bilder 38, davon 27 für KI» next to Aufnahmedauer/Rechenzeit. **[ux]**
6. **Edit title and project while transcribing** – currently locked; the finished transcription must take the
   title from `meta.json` instead of overwriting the change. **[ux]**

## 0.7.34 – next

**Status 23 Oct 2026:** 0.7.38 released (speaker box without speakers, MLX file name, Linux Qt/lspci,
GPU measurements). 0.7.37 released (fixed download names for frehner.tech). 0.7.36 released (experimental tests in the diagnosis: load Nvidia libraries or
MLX with a button, speed test CPU vs. graphics chip, notification and call-detection checks). 0.7.35 released (lost audio device reconnects instead of ending the recording;
Nvidia GPU via `verbalis gpu --install`; MLX measuring on Macs). 0.7.34 released (Linux experimental: call detection via pactl, notify-send
notifications, single instance, pipx install; macOS: no crash on quitting with an open audio device). 0.7.33 released (speaker box: the name field is the only list of
participants; the track named in «Anzahl Personen auf dieser Spur»). 0.7.32 released (split paragraphs with Enter, Shift+Enter line breaks, word
timestamps kept, time left during diarization, participants to pick in the speaker box, wider fields,
monthly search for new Swiss German models). Not measured: `gcoli/whisper-large-v3-swiss-german-mit` –
turbo already needs ~1.1–1.2× real time on Andrea's PC, large-v3 would be several times slower.
`Flurin17/cohere-transcribe-swiss-german` is new but non-commercial (cc-by-nc).

0.7.33 (20 Oct 2026): one participant list in the speaker box, track named in the people count.
0.7.32 (20 Oct 2026): split paragraphs with Enter, word timestamps kept, time left during diarization,
participants in the speaker box, model search.
0.7.31 (19 Oct 2026): «Sprechertrennung» Standard 0.7 / Eher weniger Personen 0.9, «Kurze Einwürfe am Rand
zeigen», «1» shown for a track that is not told apart.
0.7.30 (17 Oct 2026): introduction for new users, tracks «Mikrofon»/«Systemton», «Person 1, 2, …» on the
microphone, Mac no longer experimental.
0.7.29 (15 Oct 2026): «Problem melden» (Google Sheet via Apps Script), Mac certificate path after the
self-move, gcoli from our mirror.
0.7.28 (15 Oct 2026): stricter update checks (SHA-256 required, Mac: same certificate), list groups fixed.
0.7.27 (14 Oct 2026): a known number of people joins similar voices (`merge_to_count`) – on-site
recordings with 2 and 4 people: 75 % / 90 % right instead of 56 % / 76 %. Per-turn re-assignment was
tried and dropped (not better). Idea for later: «klingt ähnlich wie …» hints when merging by hand.

1. **«Leise oder undeutliche Stellen»: Standard / empfindlicher (VAD)** – first a `compare` option to
   measure; the recording 2026-10-14_110111 (a quiet second speaker) may be used for it. **[quality]**
2. **Split automatically at a speaker change** – diarization sees a change within a sentence; the words are
   there now. Measure first how often it happens, so short overlaps don't chop paragraphs. **[quality]**

**Speaker measurements 19 Oct 2026** (speakers after refining · right without merging by hand · pure = right
   after naming · right with the known number):

   | Recording | 0.7 | 0.9 | 1.0 | with number (0.7) |
   |---|---|---|---|---|
   | Teams 1:1, Mikrofon (1 person) | 7 · 28 % · 100 % | 3 · 54 % · 100 % | 3 · 46 % · 100 % | 100 % |
   | Teams 1:1, Systemton (1) | 11 · 20 % · 100 % | 5 · 52 % · 100 % | 3 · 83 % · 100 % | 100 % |
   | Teams 3 people, Mikrofon (1) | 7 · 40 % · 100 % | 4 · 61 % · 99 % | 2 · 90 % · 99 % | 99 % |
   | Teams 3 people, Systemton (2) | 19 · 52 % · 100 % | 11 · 71 % · 99 % | 6 · 87 % · 98 % | 100 % |
   | On site, 4 people | 7 · 78 % · 96 % | 5 · 87 % · 97 % | 5 · 88 % · 97 % | 96 % |
   | On site, 2 people (Andrea, Basil) | 10 · 46 % · 99.7 % | 9 · 49 % · 97.5 % | 6 · 53 % · 97 % | 78 % |

   Findings: Teams calls split one person into many speakers but hardly ever mix two people; the known
   number fixes Teams calls almost completely. A higher threshold mixes similar voices on site (Basil),
   so 0.7 stays the default. On-site, 2 people: the number still mixes 22 % (part of Andrea sounds like
   Basil to the model). Also seen: a turn that started with one person and went on with another (once in
   48 min) – the reference uses whole segments, so the measurement cannot see this; if it happens more
   often, split paragraphs at speaker changes (word timestamps exist).

## Later – AI meeting notes (planned 20 Oct 2026, on hold – Andrea: «lassen wir es mal sein»)

Today Andrea writes the notes with Claude Code: transcript + e-mails after the meeting + template + project
context from his vault, result into the vault. Expectation for a local model: a good first draft to edit,
not Claude's judgment. Measure first, then build.

- **What his notes need** (from his Claude Code prompt, 20 Oct 2026): one block per topic/CR with status,
  questions and tasks («Aufgabe: … *(Verantwortlich · Status · Deadline)*»); sources ranked corrections in
  mails > mail summary > transcript; things only in the transcript marked «(in der Mail nicht
  festgehalten)»; «Entscheid» only when confirmed as final, proposals and open points marked as such;
  leave out small talk, private matters, personnel matters; names spelled as in the mails, uncertain names
  marked 🔶; dates absolute; frontmatter (date, type, project, participants with role). The model also needs
  project context in one sentence and who took part (the transcript often says «Person 3»).
- **Let Python do what rules can do:** absolute dates (the meeting date is known), 🔶 for names that are not
  among the participants/speakers or in the mail. The model only writes.
- **Technique:** `llama-server` from llama.cpp (MIT) as a separate process, downloaded with a fixed SHA-256
  like the other models (no GIL freeze, Metal on the Mac). Two steps: per ~10-min chunk extract facts as
  JSON forced by a schema (topic, statement, who, decision/proposal/open, task, time), then write the note
  from the facts + mail + template – easier for small models, every statement traceable to the transcript.
- **Models to compare:** Qwen 3 8B (Apache 2.0, ~5 GB) and Phi-4 14B (MIT, ~9 GB – tight: Andrea's PC has
  15.5 GB RAM, Intel Core Ultra 7 255U without a graphics card; the speaker measurement already ran out of
  memory). Estimate for a 48-min meeting: 10–20 min in the background on his PC, maybe 3–5 min on the Mac.
- **Step 1 – measure without UI:** `verbalis notes <folder> --template … --mail mail.txt --model …` writes
  `notes.md`. 2–3 meetings that already have a Claude note (e.g. SGUM 19 Oct 2026); Andrea rates: decisions
  right, tasks with owner complete, nothing invented, private things left out, how much he would rewrite.
  Claude does not read transcripts or notes unless Andrea names a file. Measure time and RAM on PC and Mac.
  **Bar:** if more than about a third has to be rewritten, don't build it.
- **Step 2 – build only if good:** Einstellungen → Notizen with templates (instruction + sections; his rules
  above as the default instruction, generic, not tocco-specific), model download on request; «Notizen
  erstellen» in the transcript with template, a field for the mail/additions, project context, participants
  with role (prefilled from the recording details); background job with progress, `notes.md` editable and
  copyable. **[ux] [privacy]**
- **Independent and cheap:** «Transkript kopieren mit Vorlage» – prompt, template, participants and
  transcript in one go for Claude Code. **[ux]**
- **Open questions for Andrea:** only for him or also for colleagues (their laptops)? Mail pasted into a
  field (recommended) or fetched from Outlook? Write the note into a vault folder per project, or copy and
  `notes.md` only? Cloud (Claude API) as an explicit opt-in – the transcript would leave the computer,
  needs tocco's consent.

## Security (from the review on 15 Oct 2026)

Done in 0.7.28: an update needs a SHA-256 from GitHub; on the Mac the new app must satisfy the running app's
code requirement (same certificate), checked in the release build with the real `codesign`.

- [ ] **GitHub account and repo** **[ops]**: two-factor / passkey on the account; protect `main` (no force
  push, no deletion); signing secrets only in a GitHub «Environment» used by the release job; pin
  third-party actions (`softprops/action-gh-release`, ideally all) to a commit SHA – Dependabot updates them.
- [ ] **Windows: check the update's signature before running it** – built (`updates.check_windows_signature`),
  switched on by `WINDOWS_PUBLISHER` after the first signed release (see «Code signing»). **[ops]**
- [ ] **Recordings at rest** are not encrypted: rely on BitLocker/FileVault (document for users and tocco IT);
  later maybe «Audio nach N Tagen löschen». **[privacy]**

## Proposed (waiting for Andrea's OK)

- **«Problem melden» next to error messages** too (the dialog exists since 0.7.29). **[ux]**

## Now

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
- [ ] **Export** to Word/PDF (copy as Markdown exists). **[ux]**
- [ ] **Import/export the correction list**, e.g. to share company terms within a team. **[tocco]**
- [ ] **i18n** – UI in English as an option. **[ux]**
- [ ] **GPU support.** **Measured 23 Oct 2026 (speed test, 120 s, gcoli turbo):** Mac M1: CPU 13.3 s (0.11×),
  MLX 11.5 s – only 1.2× faster, 96 % same words (MLX greedy, CPU beam 5) → MLX not worth building into the
  app for now. Windows i7-1165G7 + T500: CPU 48 s (0.4×), CUDA 36 s – 1.3×, 99 % same words (weak card).
  Revisit with an RTX card or a newer Mac (M3/M4). Measured 22 Oct 2026: more CPU threads don't help (Intel Core Ultra: 4 threads
  0.66× real time, 8/12 threads slower). **Apple M chips:** `mlx:` in `verbalis compare` (MLX, experimental) –
  Andrea measures speed and WER on a real recording; if clearly faster at similar WER, build it into the app
  (model conversion hosted on our Hugging Face account, mlx-whisper needs torch → bigger Mac app).
  **Nvidia (CUDA):** built (experimental): `verbalis gpu --install` downloads cuBLAS + cuDNN (1.3 GB), then
  «auto» uses the GPU with CPU fallback. Test device: Andrea's T500 (expect only ~2–4× faster; RTX 15–40×).
  If it works: a button in the settings instead of the command line, diarization on the GPU. **[quality]**
- [ ] **Echo without headset** – reduce remote voices on the microphone track. **[quality]**
- [ ] **Taskbar icon on Windows** – may still show the Python icon; set an AppUserModelID / window icon. **[ux]**
- [ ] **Ubuntu test** (Linux experimental since 0.7.34) – PipeWire monitor source, pywebview with GTK or Qt,
  clipboard and save dialog in WebKitGTK, call detection with Teams/Zoom/browser (`pactl`), notification click
  (`notify-send`), second start refused. Then decide on an AppImage (+ auto-update). **[ops]**
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
- [ ] **Code signing** – decided 23 Nov 2026: Mac = Apple Developer Program (individual, Developer ID +
  notarization), Windows = SignPath Foundation. **Pipeline prepared** (not released yet, switches on with the
  secrets): `docs/CODE-SIGNING.md` is the checklist. **Status 23 Nov 2026:** SignPath Foundation application
  sent (waiting for the answer). Apple **on hold** (Andrea: CHF 109/year, waits for now; enrollment started, not
  paid – can be continued later). Until then Mac stays on the own certificate as today. Next: SignPath answer →
  secrets → first signed Windows release → `WINDOWS_PUBLISHER`. Apple later: enroll → Team ID → bridge release
  with `updates.APPLE_TEAM_ID` → secrets → first Developer ID release.
  Risks: entitlements only verified by the CI self-test, not yet on a real Mac (TCC prompts, process tap,
  MLX); SignPath approval needed for every release (Windows job waits up to 5 h). **[ops]**

- [ ] Talk to IT and data protection: local processing, consent per recording, retention (audio deleted after N days).
- [x] **Licence of the default model gcoli checked (15 Oct 2026):** model MIT; base `whisper-large-v3-turbo` MIT;
  training data FHNW/i4ds Swiss Parliaments Corpus (Bern) and Gemeinderat Zürich corpus MIT (stated on
  cs.technik.fhnw.ch/i4ds-datasets); pseudo-labels from `whisper-large-v3` (Apache 2.0); commercial use
  permitted; attribution to FHNW/i4ds in the README. Remaining small risks: the dataset on Hugging Face
  (i4ds/SPC) shows no licence tag – the MIT statement is only on the FHNW page (archive it, or ask FHNW for a
  written confirmation if tocco wants certainty); gcoli is an individual account (created Sept 2026), so
  the claims can't be verified further – Verbalis pins the revision. Flix (Apache 2.0) was trained under the
  Swiss TDM research exception – not the default any more.
- [x] **gcoli mirrored** (15 Oct 2026) to `malaxy/whisper-large-v3-turbo-swiss-german-ct2` with
  `tools/mirror_model.py` (revision 540fb2e, ct2 files at the root, licence, original card, provenance);
  Verbalis downloads from there since 0.7.29, the monthly check watches the original.
- [ ] Standard consent text for customer calls (German and English).
- [ ] Decide on defaults for colleagues: retention, model, storage location (Verbalis warns about synced folders since 0.7.11).
