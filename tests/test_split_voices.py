"""Splitting one speaker into the people marked on it (0.7.45: diarization.split_voices, transcript.split_by_voice)."""

import json

import pytest

from verbalis import diarization, pipeline
from verbalis.transcript import apply_marks, apply_voice_split, split_by_voice, voice_split_plan
from test_service import finished_recording, make_service, wait_until

# Two «voices» on a time line: Sascha talks from 20 to 40 s and from 70 to 80 s, Paul otherwise.
SASCHA = [(20.0, 40.0), (70.0, 80.0)]


def fake_embed(intervals):
    """A voice print pointing to Sascha or Paul by how much of the intervals Sascha talks in."""
    total = sum(e - s for s, e in intervals) or 1.0
    sascha = sum(max(0.0, min(e, b) - max(s, a)) for s, e in intervals for a, b in SASCHA) / total
    return [sascha + 0.05, 1.0 - sascha + 0.05]


def test_two_people_in_one_speaker_are_told_apart_by_their_marks():
    """5 Nov 2026, meeting on site with 7 people: Sascha and Paul were one speaker. «Neu zuordnen» with 7 people
    only joins speakers and could not part them; the marks of both on that speaker can."""
    labeled = diarization.split_voices([(0.0, 90.0)], {"Paul": [(5.0, 11.0)], "Sascha": [(25.0, 31.0)]}, fake_embed)
    sascha = [(s, e) for s, e, name in labeled if name == "Sascha"]
    assert sascha[0][0] == 21.0 and sascha[-1][1] == 81.0       # 3-second windows, by the voice heard most
    assert all(name == "Paul" for s, e, name in labeled if e <= 18 or 42 <= s <= 66)
    assert diarization.split_voices([(0.0, 90.0)], {"Paul": [(5.0, 11.0)]}, fake_embed) == []


def words(start, *texts, step=1.0):
    return [[start + i * step, start + (i + 1) * step, " " + t] for i, t in enumerate(texts)]


def test_a_paragraph_is_cut_where_the_voice_changes_and_keeps_corrections():
    labeled = [(0.0, 5.0, "Paul"), (5.0, 10.0, "Sascha")]
    seg = {"start": 0.0, "end": 10.0, "text": "Eins zwei drei vier fünf Sechs sieben acht neun zehn",
           "words": words(0.0, "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "nein", "zehn"),
           "speaker_id": "me-1", "speaker": "Paul", "track": "me"}
    (first, a), (second, b) = split_by_voice(seg, labeled)
    assert (a, b) == ("Paul", "Sascha")
    assert first["text"] == "Eins zwei drei vier fünf" and second["text"] == "Sechs sieben acht neun zehn"
    assert (first["start"], first["end"], second["start"], second["end"]) == (0.0, 5.0, 5.0, 10.0)
    assert len(first["words"]) == len(second["words"]) == 5
    # a short stretch of the other voice (a cough, a misjudged window) doesn't cut the paragraph
    short = [(0.0, 4.0, "Paul"), (4.0, 5.0, "Sascha"), (5.0, 10.0, "Paul")]
    assert [name for _, name in split_by_voice(seg, short)] == ["Paul"]
    # without words the paragraph stays whole, with the voice heard longest
    whole = {**seg, "words": None}
    assert [(p["text"], name) for p, name in split_by_voice(whole, [(0.0, 3.0, "Paul"), (3.0, 10.0, "Sascha")])] \
        == [(seg["text"], "Sascha")]


def test_the_hidden_person_becomes_a_speaker_of_its_own():
    data = {"tracks": {"me": "Andrea"}, "speakers": {"me-1": {"name": "Paul", "track": "me"},
                                                     "me-3": {"name": "Odilia", "track": "me"}},
            "segments": [
                {"start": 0.0, "end": 10.0, "text": "a b c d e f g h i j", "track": "me", "speaker_id": "me-1",
                 "speaker": "Paul", "words": words(0.0, *"abcdefghij")},
                {"start": 11.0, "end": 14.0, "text": "Odilia redet", "track": "me", "speaker_id": "me-3",
                 "speaker": "Odilia", "words": None}]}
    marks = [{"t": 1.0, "name": "Paul", "track": "me"}, {"t": 6.0, "name": "sascha", "track": "me"},
             {"t": 8.0, "name": "Sascha", "track": "me"}, {"t": 12.0, "name": "Odilia", "track": "me"}]
    spans, seeds = voice_split_plan(data, marks, "me-1")
    assert spans == [(0.0, 10.0)] and list(seeds) == ["Paul", "sascha"]     # one person, however it was typed
    ids = apply_voice_split(data, "me-1", [(0.0, 5.0, "Paul"), (5.0, 10.0, "sascha")])
    assert ids == {"Paul": "me-1", "sascha": "me-4"}                         # the next free number
    assert data["speakers"]["me-4"] == {"name": "sascha", "track": "me"}
    assert [(s["speaker_id"], s["text"]) for s in data["segments"]] == [
        ("me-1", "a b c d e"), ("me-4", "f g h i j"), ("me-3", "Odilia redet")]
    _, doubts = apply_marks(data, [{**m, "name": m["name"].lower()} if m["name"] == "Sascha" else m for m in marks])
    assert doubts == []                                                     # «Unklar» is gone


def test_split_speaker_runs_in_the_background(monkeypatch):
    s = make_service()
    rid = finished_recording(s)
    folder = s._path(rid)
    data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
    data["speakers"] = {"me-1": {"name": "Paul", "track": "me"}}
    data["segments"] = [{"start": 0.0, "end": 10.0, "text": "a b c d e f g h i j", "track": "me",
                         "speaker_id": "me-1", "speaker": "Paul", "words": words(0.0, *"abcdefghij")}]
    (folder / "transcript.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Absätze der anderen Person"):
        s.split_speaker(rid, "me-1")
    pipeline.update_meta(folder, speaker_marks=[{"t": 1.0, "name": "Paul", "track": "me"},
                                                {"t": 7.0, "name": "Sascha", "track": "me"}])
    monkeypatch.setattr(diarization, "split_voices", lambda spans, seeds, embed, **options: [
        (0.0, 5.0, "Paul"), (5.0, 10.0, "Sascha")])
    monkeypatch.setattr("verbalis.transcription.faster.load_audio", lambda path, until=None: None)
    monkeypatch.setattr(type(s), "_voice_embedder", staticmethod(lambda audio: (None, None)))
    s.split_speaker(rid, "me-1")
    assert wait_until(lambda: len(s.speakers(rid)) == 2, timeout=15)
    assert [(x["name"], x["seconds"]) for x in s.speakers(rid)] == [("Paul", 5), ("Sascha", 5)]
    assert (folder / "transcript_original.json").exists()                # the version before stays
    with pytest.raises(ValueError, match="gibt es nicht"):
        s.split_speaker(rid, "me-99")


def test_a_paragraph_moved_to_a_new_person_is_a_sample_to_split_with():
    """5 Nov 2026: marks could only be set while recording – after it there was no way to show Verbalis «this is
    Sascha». Now a paragraph given to a person by name (a new one too) is a voice sample, and «heraustrennen»
    is offered on the voice it came from."""
    s = make_service()
    rid = finished_recording(s)
    folder = s._path(rid)
    data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
    data["speakers"] = {"me-1": {"name": "Paul", "track": "me"}}
    data["segments"] = [{"start": 10.0 * i, "end": 10.0 * i + 8, "text": f"Absatz {i}", "track": "me",
                         "speaker_id": "me-1", "speaker": "Paul", "words": None} for i in range(3)]
    (folder / "transcript.json").write_text(json.dumps(data), encoding="utf-8")
    assert s.transcript(rid)["split_with"] == {}
    assert s.assign_paragraph(rid, 1, " Sascha ") == {"speaker_id": "me-2"}
    t = s.transcript(rid)
    assert t["speakers"]["me-2"] == {"name": "Sascha", "track": "me"} and t["segments"][1]["speaker"] == "Sascha"
    assert t["split_with"] == {"me-1": ["Sascha"]}
    assert "Sascha" in pipeline.read_meta(folder)["participants"]["me"]
    assert s.assign_paragraph(rid, 2, "sascha") == {"speaker_id": "me-2"}       # the same person, however typed
    with pytest.raises(ValueError):
        s.assign_paragraph(rid, 0, "  ")


def test_the_own_voice_without_a_sample_is_found_from_the_rest():
    """Only Sascha's paragraphs were moved out of «Paul»: Paul's voice is taken from the windows least like her."""
    labeled = diarization.split_voices([(0.0, 90.0)], {"Sascha": [(25.0, 31.0)], "Paul": None}, fake_embed)
    sascha = [(s, e) for s, e, name in labeled if name == "Sascha"]
    assert sascha[0][0] == 21.0 and sascha[-1][1] == 81.0
    assert diarization.split_voices([(0.0, 90.0)], {"Sascha": None, "Paul": None}, fake_embed) == []
