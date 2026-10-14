# Backlog

Open items, roughly in priority order. Done items move to `CHANGELOG.md`.
Tags: **[quality]** transcript quality · **[ux]** usability · **[ops]** build/deploy ·
**[privacy]** data protection · **[tocco]** needed before use at tocco

## 0.7.26 – planned and decided with Andrea (build once item 3 is measured)

1. **Maximum recording time**: setting «Aufnahme automatisch beenden nach», default **2 hours** (decided),
   empty = no limit. Notice 5 minutes before («Aufnahme endet in 5 Min.», button «+30 Min.»; Windows
   notification when in the background). Ends cleanly as a complete recording; meta.json says why.
2. **Ask to stop when the call is over**: only if a call was recognised when the recording started; when the
   call app hasn't used the microphone for ~30 s: «Der Teams-Call ist zu Ende – Aufnahme beenden?»
   («Beenden» / «Weiter aufnehmen»). Never stops by itself – the maximum time is the safety net.
3. **Settings for recognition and speakers** – in plain words, few steps, values from measurements:
   - «Sprechertrennung»: eher weniger Personen / Standard / eher mehr Personen (`THRESHOLD`)
   - «Kurze Einwürfe am Rand zeigen» (on/off)
   - «Leise oder undeutliche Stellen»: Standard / empfindlicher (VAD) – needs a `compare` option to measure
   **Waiting for measurements:** Andrea runs `verbalis speakers-test <folder> --track others|me
   --thresholds 0.5 0.6 0.7 0.8 0.9` on 2–3 real recordings (Teams with 3–4 people, room meeting with 2,
   1:1) and sends the numbers with the true number of people.
4. **«Keiner – nur Mikrofon»** as a choice under «Ton der anderen kommt über» (proposed by Andrea, 14 Oct 2026):
   for meetings in a room – only the microphone track is recorded, no system audio warning, speaker
   diarization on the own track.
5. **Is the model up to date?** Show «✓ Neuester Stand (geprüft heute 14:05)» / «Update verfügbar: Stand vom
   …» / «Nicht geprüft – keine Internetverbindung», button «Jetzt prüfen»; the date is when the revision
   was published, not when it was downloaded; the short id small below.

## Proposed (waiting for Andrea's OK)

- **Mac: install into the right place by itself** (agreed with Andrea, 14 Oct 2026):
  1. At start, if Verbalis runs from «Downloads», «Dokumente», a translocated copy or any other unsuitable
     place, ask once «Verbalis in den Ordner Programme verschieben?» – move itself and restart. Target:
     `/Applications` when writable (admin), else `~/Applications` (create it). This also fixes self-updates
     without an admin account and the read-only copy from «Downloads».
  2. A DMG for the first download (Verbalis + arrow to «Programme»); the ZIP stays for automatic updates.
  Item 1 matters more (it also helps when someone forgets to move it). Test build first; needs Andrea's Mac. **[ux]**
- **«Problem melden»** (Log tab, later also next to error messages): creates the log ZIP, opens a prepared
  e-mail to andrea@frehner.tech (version, system, short template) and shows the ZIP in Finder/Explorer to
  drag into the mail. Not as a GitHub issue (public repo). Could also attach «Diagnose kopieren». **[ux]**
- **Remove the test branch `mac-audio`** on GitHub once 0.7.23 is confirmed on the Mac. **[ops]**

## Now

- [ ] **Mac: confirm after the update 0.7.23 → 0.7.24** (14 Oct 2026): no new permission question and sound on
  both tracks = the stable signature works. Found: the signature was fine («Authority=Verbalis Code
  Signing»); 0.7.23 aborted recordings after 3 s without audio (permission question open / nothing playing),
  fixed in 0.7.24. Then remove the test branch `mac-audio`. **[ops]**
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
