"""Reading, filtering and exporting the log without personal data."""

import json
import zipfile
from pathlib import Path

from verbalis import logs

SAMPLE = """2026-10-08 09:00:00,001 INFO verbalis: Verbalis 0.7.1 starting
2026-10-08 09:00:05,123 WARNING verbalis.service: Compressing x failed
2026-10-08 09:01:00,000 ERROR verbalis.service: Transcription of 2026-10-08_090000 failed
Traceback (most recent call last):
  File "{home}/dev/verbalis/src/verbalis/service.py", line 1, in _work
RuntimeError: Modell kaputt
2026-10-08 09:02:00,000 INFO verbalis: Verbalis closed
"""


def _write_log(home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "verbalis.log.1").write_text("2026-10-07 20:00:00,000 INFO verbalis: older file\n", encoding="utf-8")
    (home / "verbalis.log").write_text(SAMPLE.format(home=Path.home().as_posix()), encoding="utf-8")


def test_entries_newest_first_with_details(home):
    _write_log(home)
    entries = logs.read_entries()
    assert [e["message"] for e in entries][:2] == ["Verbalis closed", "Transcription of 2026-10-08_090000 failed"]
    assert entries[-1]["message"] == "older file"               # backup file is included
    assert "RuntimeError: Modell kaputt" in entries[1]["details"]


def test_errors_only(home):
    _write_log(home)
    assert [e["level"] for e in logs.read_entries(errors_only=True)] == ["ERROR", "WARNING"]


def test_no_log_yet(home):
    assert logs.read_entries() == []


def test_export_is_anonymised_and_without_personal_settings(home, tmp_path):
    _write_log(home)
    settings = {"name": "Andrea", "others": "Gegenüber", "keywords": "tocco, Höngg", "model": "large-v3",
                "recordings_dir": "C:/Users/x/geheim", "audio_days": "3"}
    target = logs.export(tmp_path / "export.zip", settings)
    with zipfile.ZipFile(target) as z:
        assert set(z.namelist()) == {"info.json", "verbalis.log", "verbalis.log.1"}
        info = json.loads(z.read("info.json"))
        log_text = z.read("verbalis.log").decode("utf-8")
    assert info["settings"]["model"] == "large-v3" and info["custom_recordings_dir"] is True
    dumped = json.dumps(info, ensure_ascii=False)
    assert "Andrea" not in dumped and "tocco" not in dumped and "geheim" not in dumped
    assert Path.home().as_posix() not in log_text and "~/dev/verbalis" in log_text
