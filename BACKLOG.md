# Backlog

Open items, roughly in priority order. Done items move to `CHANGELOG.md`.
Tags: **[quality]** transcript quality · **[ux]** usability · **[ops]** build/deploy ·
**[privacy]** data protection · **[tocco]** needed before use at tocco

## 0.7.34 – next

**Status 22 Oct 2026:** 0.7.34 released (Linux experimental: call detection via pactl, notify-send
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
3. **New user-defined speaker after splitting** – today the second part can only go to a person already
   found on that track. **[ux]**

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
- [ ] **Windows: check the update's signature before running it** – only possible once Windows is signed
  (see «Code signing»). **[ops]**
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
- [ ] **Search across transcripts.** **[ux]**
- [ ] **Export** to Word/PDF (copy as Markdown exists). **[ux]**
- [ ] **Import/export the correction list**, e.g. to share company terms within a team. **[tocco]**
- [ ] **i18n** – UI in English as an option. **[ux]**
- [ ] **GPU support.** Measured 22 Oct 2026: more CPU threads don't help (Intel Core Ultra: 4 threads
  0.66× real time, 8/12 threads slower). **Apple M chips:** `mlx:` in `verbalis compare` (MLX, experimental) –
  Andrea measures speed and WER on a real recording; if clearly faster at similar WER, build it into the app
  (model conversion hosted on our Hugging Face account, mlx-whisper needs torch → bigger Mac app).
  **Nvidia (CUDA):** CTranslate2 already supports it; cuBLAS + cuDNN (~700 MB) downloaded on demand. Test
  device: Andrea's T500 (works, but only ~2–4× faster; RTX cards 15–40×). **[quality]**
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
- [x] **gcoli mirrored** (15 Oct 2026) to `malaxy/whisper-large-v3-turbo-swiss-german-ct2` with
  `tools/mirror_model.py` (revision 540fb2e, ct2 files at the root, licence, original card, provenance);
  Verbalis downloads from there since 0.7.29, the monthly check watches the original.
- [ ] Standard consent text for customer calls (German and English).
- [ ] Decide on defaults for colleagues: retention, model, storage location (Verbalis warns about synced folders since 0.7.11).
