// Fake backend for tools/ui_preview.py: answers the pywebview API with sample data.
window.__scenario = window.__scenario || "transcript";
const segments = [
  ["Andrea", 1, "Guten Tag zusammen. Das ist eine Testaufnahme für die Mitschrift, und ich lese jedes Mal genau denselben Text vor."],
  ["Gegenüber", 9, "Ja, danke. Können wir kurz mit dem Hund über das nächste Release von Toko sprechen? Die Deadline ist am 24. Oktober."],
  ["Andrea", 17, "Gerne. Das Budjet liegt bei 25'300 Franken, das sollte reichen, wenn wir den Umfang halten."],
].map(([s, t, x]) => ({ speaker: s, start: t, end: t + 6, text: x }));
const recs = [
  { id: "2026-10-08_093012", start: "2026-10-08T09:30:12+02:00", duration_s: 1834, status: "running", error: null, audio: true, audio_mb: 60, audio_delete: null },
  { id: "2026-10-07_204727", start: "2026-10-07T20:47:27+02:00", duration_s: 66.1, status: "done", error: null, audio: true, audio_mb: 2.4, audio_delete: "2026-10-10T20:47+02:00" },
  { id: "2026-10-07_143000", start: "2026-10-07T14:30:00+02:00", duration_s: 412, status: "none", error: null, audio: false, audio_mb: 0, audio_delete: null },
  { id: "2026-10-06_101500", start: "2026-10-06T10:15:00+02:00", duration_s: 2710, status: "error", error: "Modell konnte nicht geladen werden.", audio: true, audio_mb: 80, audio_delete: null },
];
const ok = (d) => Promise.resolve({ ok: true, data: d });
let t0 = 754;
window.pywebview = { api: {
  version: () => ok("0.7.0"),
  settings: () => ok({ model_auto_update: "off", storage_warning: window.__scenario === "dev" ? "Der Aufnahmeordner liegt in einem synchronisierten Ordner (Verbalis in «onedrive - tocco ag»). Aufnahmen würden so in die Cloud kopiert – für vertrauliche Gespräche einen lokalen Ordner wählen." : null, update_check: "on", name: "Andrea", others: "Gegenüber", model: "Flix-AI/flix-swissgerman-full", quality: "accurate", keywords: "tocco, Höngg", recordings_dir: "", microphone: "", speakers: "", audio_days: "3", audio_max_mb: "", recordings_path: "C:\\Users\\AndreaFrehner\\.verbalis\\recordings" }),
  devices: () => window.__scenario === "nomic" ? ok({ platform: "win32", virtual_device: true, microphones: [], speakers: ["Lautsprecher (Realtek(R) Audio)"], default_microphone: "", default_speakers: "Lautsprecher (Realtek(R) Audio)", problems: ["Es wurde kein Mikrofon gefunden. Headset oder Mikrofon anschliessen – und unter Windows in den Einstellungen → Datenschutz und Sicherheit → Mikrofon den Zugriff für Desktop-Apps erlauben. Danach «Geräte neu laden»."] }) : ok({ platform: "win32", virtual_device: true, problems: [], microphones: ["Microphone Array (Intel® Smart Sound Technology)", "Jabra Evolve2 65"], speakers: ["Speakers (Realtek(R) Audio)", "Jabra Evolve2 65"], default_microphone: "Microphone Array (Intel® Smart Sound Technology)", default_speakers: "Speakers (Realtek(R) Audio)" }),
  models: () => ok([
    { id: "Flix-AI/flix-swissgerman-full", name: "Flix Schweizerdeutsch", size_gb: 3.1, description: "Schweizerdeutsch-Fine-Tune (large-v3), bestes Ergebnis im Test", status: "auf diesem PC", local: true, label: "Flix-AI/flix-swissgerman-full – auf diesem PC", page: "https://huggingface.co/malaxy/flix-swissgerman-ct2", revision: "4f2e9c1", loaded: "2026-10-08T15:20+02:00", source: "Hugging Face" },
    { id: "large-v3", name: "Whisper large-v3", size_gb: 3.1, description: "Original von OpenAI, fast gleich gut, etwas schneller", status: "wird bei Bedarf heruntergeladen (ca. 3,1 GB)", local: false, label: "large-v3 – wird bei Bedarf heruntergeladen (ca. 3,1 GB)", page: "https://huggingface.co/Systran/faster-whisper-large-v3", revision: null, loaded: null, source: "Hugging Face" },
    { id: "large-v3-turbo", previous: true, name: "Whisper large-v3 turbo", size_gb: 1.6, description: "deutlich schneller, aber schwächer bei Dialekt", status: "auf diesem PC", local: true, label: "large-v3-turbo – auf diesem PC", page: "https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo", revision: "0c94664", loaded: "2026-10-07T21:43+02:00", source: "Hugging Face" }]),
  model_updates: () => new Promise((res) => setTimeout(() => res({ ok: true, data: { "Flix-AI/flix-swissgerman-full": { revision: "9be17d0", changed: "2026-11-02T08:00+01:00" } } }), 300)),
  open_model_page: (id) => { window.__modelPage = id; return ok(null); },
  update_model: (id) => { window.__modelDl = { model: id, progress: 0.42 }; return ok(null); },
  rollback_model: (id) => { window.__rolledBack = id; return ok("a".repeat(40)); },
  dismiss_model_updates: () => { window.__modelsDismissed = true; return ok(null); },
  dismiss_notice: () => { window.__noticeGone = true; return ok(null); },
  recordings: () => ok((list => window.__scenario === "transcript" ? list.map((a, i) => i === 1 ? { ...a, state: "interrupted", problem: "Verbalis wurde während der Aufnahme beendet (Absturz oder Stromausfall). Das Audio bis dahin ist gesichert.", missing_tracks: ["others"] } : a) : list)(window.__scenario === "paused" ? recs.map((a, i) => i === 0 ? { ...a, status: "paused" } : a) : window.__scenario === "empty" ? [] : window.__scenario === "recording" ? [{ id: "2026-10-08_110000", start: "2026-10-08T11:00:00+02:00", duration_s: null, status: "recording", audio: true, audio_mb: 0 }, ...recs.slice(1)] : recs)),
  state: () => ok({ recording: window.__scenario === "recording" ? { id: "2026-10-08_110000", duration_s: (t0 += 0.25), levels: { me: -14 - Math.random() * 6, others: -90 }, paused: !!window.__recPaused, others_silent_s: 75, others_device: "Speakers (Realtek(R) Audio)", disk_minutes_left: 42 } : null, model_updates: window.__modelsDismissed ? [] : ["Flix-AI/flix-swissgerman-full"], model_download: window.__modelDl || null, notice: window.__scenario === "notice" && !window.__noticeGone ? "Das Modell Flix-AI/flix-swissgerman-full wurde aktualisiert (neuer Stand 9be17d0). Details auf der Modellseite in den Einstellungen." : null, update: window.__scenario === "empty" ? null : { latest: "0.7.5" }, update_progress: window.__progress ?? null, job: { id: "2026-10-08_093012", phase: "Spur «Andrea» wird transkribiert", progress: 0.37, remaining_s: 1260 }, queued: [], pause: window.__scenario === "paused" ? "manual" : (window.__scenario === "recording" ? "recording" : null), recording_error: null }),
  transcript: () => ok({ title: "", header: { Modell: "Flix-AI/flix-swissgerman-full", Aufnahmedauer: "1.1 min", Rechenzeit: "1.7 min (1.54× Echtzeit)" }, tracks: { me: "Andrea", others: "Gegenüber" }, segments, markdown: "# x", edited: true }),
  edit_transcript: (id, i, text) => { segments[i].text = text; return ok({ suggestions: [
    { variant: "Toko", target: "tocco", kind: "new", previous: null },
    { variant: "Limet nah", target: "Limmat", kind: "added", previous: null },
    { variant: "Hund", target: "Kunden", kind: "replaces", previous: "Hunde" } ] }); },
  corrections: () => ok([{ target: "Limmat", variants: ["Limetnah"] }, { target: "tocco", variants: ["Tokko", "Toko"] }]),
  remember_corrections: () => ok({ remembered: 2, replaced: 3 }),
  remove_correction: () => ok([{ target: "tocco", variants: ["Tokko"] }]),
  audio_usage: () => ok({ audio_mb: 412.3 }),
  delete_audio: () => ok(null), transcribe: () => ok(null), open_folder: () => ok(null),
  start_recording: () => ok("x"), stop_recording: () => ok("x"), save_settings: (d) => { window.__saved = d; return ok(d); },
  pause: () => ok(null), resume: () => ok(null),
  pause_recording: () => { window.__recPaused = true; return ok(null); },
  resume_recording: () => { window.__recPaused = false; return ok(null); },
  spelling_check: (words) => ok({ status: "ready", error: null, misspelled: words.filter((w) => ["Toko", "Hund", "Budjet"].includes(w) && !(window.__known || []).includes(w)) }),
  spelling_suggest: (w) => new Promise((res) => setTimeout(() => res({ ok: true, data: { suggestions: { Toko: ["Tokio", "Toto"], Budjet: ["Budget"], Hund: [] }[w] || [] } }), 150)),
  spelling_add: (w) => { (window.__known = window.__known || []).push(w); return ok(null); },
  add_correction: (v, t) => v && t ? ok({ info: { variant: v, target: t, kind: t === "tocco" ? "added" : "new", previous: null }, list: [{ target: "tocco", variants: ["Tokko", "Toko", v] }] }) : Promise.resolve({ ok: false, error: "Bitte beide Felder ausfüllen: was falsch erkannt wird und wie es richtig heisst." }),
  open_project_page: () => { window.__opened = true; return ok(true); },
  update_info: () => ok({ current: "0.7.4", latest: "0.7.5", available: true, can_install: window.__scenario !== "dev",
    installer_mb: 263, notes: "- **Neue Funktion:** Sprechererkennung für mehrere Personen auf der Gegenüber-Spur\n- Fix: Export im Protokoll\n  funktioniert wieder\n\n**Installation:** `Verbalis-0.7.5-setup.exe` herunterladen und ausführen." }),
  check_updates: () => ok({ current: "0.7.4", latest: "0.7.5", available: true }),
  install_update: () => new Promise((res) => { window.__progress = 0.42; setTimeout(() => res({ ok: true, data: { started: true } }), 400); }),
  whats_new: () => ok(window.__scenario === "news" ? [
    { version: "0.7.4", title: "0.7.4 – 2026-10-08", body: "- **Update-Hinweis** in der App\n- Modelle werden bei Bedarf geladen" },
    { version: "0.7.3", title: "0.7.3 – 2026-10-08", body: "- **Eigene Rechtschreibprüfung**\n- Pause bei der Aufnahme" } ] : []),
  whats_new_seen: () => { window.__seen = true; return ok(null); },
  delete_recording: (id) => { const i = recs.findIndex((r) => r.id === id); if (i >= 0) recs.splice(i, 1); return ok(null); },
  logs: (errorsOnly) => ok([
    { time: "2026-10-08 11:02:00", level: "INFO", source: "verbalis", message: "Verbalis closed", details: "" },
    { time: "2026-10-08 11:01:00", level: "ERROR", source: "verbalis.service", message: "Transcription of 2026-10-06_101500 failed", details: "Traceback (most recent call last):\n  File \"~/dev/verbalis/src/verbalis/service.py\", line 312, in _work\nRuntimeError: Modell konnte nicht geladen werden\n" },
    { time: "2026-10-08 11:00:05", level: "WARNING", source: "verbalis.app", message: "Could not enable the context menu (spelling suggestions)", details: "" },
    { time: "2026-10-08 11:00:00", level: "INFO", source: "verbalis", message: "Verbalis 0.7.1 starting", details: "" },
  ].filter((e) => !errorsOnly || e.level !== "INFO")),
  export_logs: () => ok({ path: "C:\\Users\\AndreaFrehner\\Downloads\\verbalis-protokoll-2026-10-08_1102.zip" }),
}};
