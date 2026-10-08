"""Migration from «Mitschrift» (≤ 0.6) to Verbalis."""

import json

from verbalis import migration
from verbalis.corrections import CorrectionList
from verbalis.settings import Settings
from verbalis.transcription.models import converted_models


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _old_home(tmp_path, custom_dir=""):
    old = tmp_path / "old-home"
    _write(old / "einstellungen.json", {
        "name": "Andrea", "gegenueber": "Gegenüber", "modell": "Flix-AI/flix-swissgerman-full",
        "qualitaet": "schnell", "stichworte": "tocco", "aufnahme_ordner": custom_dir, "mikrofon": "Jabra",
        "lautsprecher": "Jabra", "fenster": "1180x620", "audio_tage": "3", "audio_max_mb": "500",
    })
    _write(old / "korrekturen.json", {"regeln": {"tocco": ["Toko"]}})
    _write(old / "statistik.json", {"echtzeitfaktor": {"x|beam5": 1.2}})
    model = old / "modelle" / "Flix-AI__flix-swissgerman-full"
    model.mkdir(parents=True)
    (model / "model.bin").write_bytes(b"x")
    _write(model / "mitschrift.json", {"quelle": "Flix-AI/flix-swissgerman-full", "quantisierung": "float16"})

    rec = old / "aufnahmen" / "2026-10-07_204727"
    for track in ("ich", "gegenueber"):
        rec.mkdir(parents=True, exist_ok=True)
        (rec / f"{track}.flac").write_bytes(b"audio")
    _write(rec / "meta.json", {
        "start": "2026-10-07T20:47:27+02:00", "dauer_s": 66.1, "samplerate": 48000,
        "einwilligung": {"bestaetigt": True, "zeitpunkt": "2026-10-07T20:47:20+02:00"},
        "spuren": {"ich": {"datei": "ich.wav", "geraet": "Mic", "laenge_s": 66.1, "aufgefuellte_stille_s": 0.0},
                   "gegenueber": {"datei": "gegenueber.wav", "geraet": "Lautsprecher", "laenge_s": 66.1,
                                  "aufgefuellte_stille_s": 0.0}},
        "audio": {"format": "flac", "samplerate": 16000},
    })
    transcript = {
        "titel": "Transkript 2026-10-07_204727", "kopf": {"Modell": "Flix"},
        "spuren": {"ich": "Andrea", "gegenueber": "Gegenüber"}, "bearbeitet": True,
        "segmente": [{"start": 1.0, "ende": 5.0, "text": "Grüezi", "sprecher": "Andrea"}],
    }
    _write(rec / "transkript.json", transcript)
    _write(rec / "transkript_original.json", transcript)
    (rec / "transkript.md").write_text("# Transkript", encoding="utf-8")
    (rec / "vergleich.md").write_text("# Vergleich", encoding="utf-8")
    return old


def test_full_migration(tmp_path, home):
    old = _old_home(tmp_path)
    done = migration.migrate_if_needed()
    assert "Einstellungen" in done and "Korrekturliste" in done and "1 Aufnahmen" in done

    s = Settings.load()
    assert (s.name, s.others, s.quality, s.keywords, s.microphone, s.window_size, s.audio_max_mb) == \
        ("Andrea", "Gegenüber", "fast", "tocco", "Jabra", "1180x620", "500")
    assert CorrectionList.load().target_of("Toko") == "tocco"
    assert json.loads((home / "stats.json").read_text())["realtime_factor"] == {"x|beam5": 1.2}
    assert converted_models() == ["Flix-AI/flix-swissgerman-full"]

    rec = home / "recordings" / "2026-10-07_204727"
    assert (rec / "me.flac").exists() and (rec / "others.flac").exists() and not (rec / "ich.flac").exists()
    meta = json.loads((rec / "meta.json").read_text(encoding="utf-8"))
    assert meta["duration_s"] == 66.1 and meta["consent"]["confirmed"] is True
    assert meta["tracks"]["me"] == {"file": "me.wav", "device": "Mic", "length_s": 66.1, "padded_silence_s": 0.0}
    t = json.loads((rec / "transcript.json").read_text(encoding="utf-8"))
    assert t["tracks"] == {"me": "Andrea", "others": "Gegenüber"} and t["edited"] is True
    assert t["segments"] == [{"start": 1.0, "end": 5.0, "text": "Grüezi", "speaker": "Andrea"}]
    assert (rec / "transcript_original.json").exists() and (rec / "transcript.md").exists()
    assert (rec / "comparison.md").exists() and not (rec / "transkript.json").exists()
    assert (old / migration.MARKER).exists()
    assert migration.migrate_if_needed() == []  # only once


def test_custom_recordings_folder_migrated_in_place(tmp_path, home):
    custom = tmp_path / "eigene"
    old = _old_home(tmp_path, custom_dir=str(custom))
    (custom / "2026-10-01_100000").mkdir(parents=True)
    (old / "aufnahmen" / "2026-10-07_204727" / "ich.flac").rename(custom / "2026-10-01_100000" / "ich.flac")
    migration.migrate_if_needed()
    assert (custom / "2026-10-01_100000" / "me.flac").exists()
    assert Settings.load().recordings == custom


def test_nothing_to_do_without_old_folder(home):
    assert migration.migrate_if_needed() == []
    assert not home.exists()


def test_existing_new_files_are_not_overwritten(tmp_path, home):
    _old_home(tmp_path)
    home.mkdir(parents=True)
    (home / "settings.json").write_text(json.dumps({"name": "Neu"}))
    migration.migrate_if_needed()
    assert Settings.load().name == "Neu"


def test_missing_custom_folder_falls_back_to_default(tmp_path, home):
    _old_home(tmp_path, custom_dir=str(tmp_path / "gibt-es-nicht"))
    migration.migrate_if_needed()
    assert Settings.load().recordings_dir == ""
