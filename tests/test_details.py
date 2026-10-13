"""Recording details (name, project, participants, notes) and planned recordings."""

import json

import pytest

from verbalis import pipeline
from test_service import finished_recording, make_service, wait_until


def test_details_are_saved_and_shown_in_the_transcript():
    s = make_service()
    rid = finished_recording(s)
    assert s.recordings()[0]["title"].startswith("Aufnahme ")        # default name from date and time
    s.update_details(rid, {"title": "  Sprint   Review ", "project": "Verbalis",
                           "participants": {"me": "Andrea\nHans", "others": "Eva, Eva, Tom"}, "notes": "Agenda: Demo"})
    entry = s.recordings()[0]
    assert entry["title"] == "Sprint Review" and entry["project"] == "Verbalis"
    assert entry["participants"] == {"me": ["Andrea", "Hans"], "others": ["Eva", "Tom"]}
    md = (s._path(rid) / "transcript.md").read_text(encoding="utf-8")
    assert md.startswith("# Sprint Review") and "**Projekt:** Verbalis" in md
    assert s.projects() == ["Verbalis"]
    with pytest.raises(ValueError, match="Startzeit"):
        s.update_details(rid, {"start": "2026-10-20T10:00"})        # a real recording keeps its time


def test_details_survive_the_end_of_the_recording():
    """meta.json is rewritten when a recording ends – what was entered meanwhile must stay."""
    s = make_service()
    rid = s.start_recording(consent=True)
    s.update_details(rid, {"title": "Kundengespräch", "project": "tocco"})
    s.stop_recording()
    meta = pipeline.read_meta(s._path(rid))
    assert meta["title"] == "Kundengespräch" and meta["project"] == "tocco" and meta["state"] == "complete"


def test_planned_recording_is_recorded_into_with_its_details():
    s = make_service()
    pid = s.plan_recording({"start": "2026-10-20T14:00", "title": "Workshop", "participants": {"me": "Andrea, Hans"}})
    entry = next(r for r in s.recordings() if r["id"] == pid)
    assert entry["status"] == "planned" and entry["audio"] is False and entry["start"].startswith("2026-10-20T14:00")
    s.update_details(pid, {"start": "2026-10-20T15:30"})              # moved
    assert pipeline.read_meta(s._path(pid))["start"].startswith("2026-10-20T15:30")
    assert s.cleanup() == []                                           # nothing to clean up, nothing deleted

    rid = s.start_recording(consent=True, planned_id=pid)
    assert rid == pid
    s.stop_recording()
    assert wait_until(lambda: s.recordings()[0]["status"] == "done")
    meta = pipeline.read_meta(s._path(pid))
    assert meta["title"] == "Workshop" and meta["participants"]["me"] == ["Andrea", "Hans"]
    assert meta["planned_start"].startswith("2026-10-20T15:30") and meta["state"] == "complete"
    with pytest.raises(RuntimeError, match="geplante"):
        s.start_recording(consent=True, planned_id=pid)                # already recorded


def test_planned_recording_can_be_deleted():
    s = make_service()
    pid = s.plan_recording({})
    assert json.loads((s._path(pid) / "meta.json").read_text(encoding="utf-8"))["state"] == "planned"
    s.delete_recording(pid)
    assert not s._path(pid).exists()
