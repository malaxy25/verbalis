"""Speaker diarization: assigning speakers, model download, transcript, naming, merging, samples.

The real models are never used here (conftest replaces them); the integration with the real
models and three synthetic voices was checked by hand – all seven turns were assigned correctly.
"""

import hashlib
import io
import json
import tarfile

import numpy as np
import pytest
import soundfile as sf

from verbalis import diarization, pipeline
from verbalis.transcription.base import Segment
from test_service import make_service, wait_until


def segs(*spans):
    return [Segment(a, b, f"Satz {i}") for i, (a, b) in enumerate(spans, 1)]


# ---------------------------------------------------------------- assigning speakers

def test_speakers_numbered_in_order_of_appearance():
    turns = [(0.0, 3.0, 5), (3.5, 6.0, 2), (6.5, 9.0, 5)]           # the clustering's own numbers
    out = diarization.assign(segs((0.2, 2.8), (3.6, 5.9), (6.6, 8.9)), turns, "others", "Gegenüber")
    assert [s.speaker for s in out] == ["Gegenüber 1", "Gegenüber 2", "Gegenüber 1"]
    assert [s.speaker_id for s in out] == ["others-1", "others-2", "others-1"]
    assert {s.track for s in out} == {"others"}


def test_one_speaker_keeps_the_track_name():
    out = diarization.assign(segs((0, 2), (3, 4)), [(0.0, 5.0, 0)], "others", "Gegenüber")
    assert [s.speaker for s in out] == ["Gegenüber", "Gegenüber"] and out[0].speaker_id == "others-1"


def test_segment_goes_to_the_speaker_who_talks_most_or_the_nearest():
    turns = [(0.0, 2.0, 0), (2.0, 10.0, 1)]
    out = diarization.assign(segs((1.5, 6.0), (20.0, 21.0)), turns, "others", "Raum")
    assert out[0].speaker == "Raum 2"                                # 0.5 s vs 4 s overlap
    assert out[1].speaker == "Raum 2"                                # no overlap: nearest turn


def test_several_voices_on_the_microphone_are_persons():
    """0.7.30 (Andrea): on site the others speak into the same microphone – «Andrea 1, Andrea 2» was wrong.
    Several voices there are «Person 1, 2, …»; one voice keeps the user's name."""
    turns = [(0.0, 2.0, 0), (2.0, 10.0, 1)]
    out = diarization.assign(segs((0.2, 1.8), (3.0, 6.0)), turns, "me", "Andrea")
    assert [s.speaker for s in out] == ["Person 1", "Person 2"] and out[1].speaker_id == "me-2"
    alone = diarization.assign(segs((0, 2), (3, 4)), [(0.0, 5.0, 0)], "me", "Andrea")
    assert {s.speaker for s in alone} == {"Andrea"}
    from verbalis.transcript import is_default_name
    assert is_default_name("Person 3", "Andrea") and is_default_name("Andrea 2", "Andrea")   # old transcripts too
    assert not is_default_name("Basil", "Andrea") and not is_default_name("Personal", "Andrea")


# ---------------------------------------------------------------- model download

def test_models_are_downloaded_once_and_checked(tmp_path, monkeypatch, no_real_diarization):
    monkeypatch.setattr(diarization, "models_ready", no_real_diarization.real_models_ready)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:bz2") as tar:
        data = b"segmentation-model"
        info = tarfile.TarInfo("sherpa-onnx-pyannote-segmentation-3-0/model.onnx")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    files = {"https://example.test/seg": archive.getvalue(), "https://example.test/emb": b"embedding-model"}
    monkeypatch.setattr(diarization, "SEGMENTATION", {**diarization.SEGMENTATION, "url": "https://example.test/seg",
                        "sha256": hashlib.sha256(files["https://example.test/seg"]).hexdigest()})
    monkeypatch.setattr(diarization, "EMBEDDING", {**diarization.EMBEDDING, "url": "https://example.test/emb",
                        "sha256": hashlib.sha256(files["https://example.test/emb"]).hexdigest()})

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    calls = []

    def opener(request, timeout=None):
        calls.append(request.full_url)
        return Response(files[request.full_url])

    folder = no_real_diarization.real_ensure_models(tmp_path / "dia", opener=opener)
    assert (folder / "segmentation.onnx").read_bytes() == b"segmentation-model"
    assert (folder / "embedding.onnx").read_bytes() == b"embedding-model"
    no_real_diarization.real_ensure_models(tmp_path / "dia", opener=opener)
    assert calls == ["https://example.test/seg", "https://example.test/emb"]                                  # second time: nothing downloaded

    files["https://example.test/emb"] = b"tampered"
    with pytest.raises(RuntimeError, match="Prüfsumme"):
        no_real_diarization.real_ensure_models(tmp_path / "other", opener=opener)


# ---------------------------------------------------------------- in the transcript

class TwoSentences:
    model, beam_size, keywords = "fake", 5, None

    def transcribe(self, audio, language="de", progress=None):
        return [Segment(0.2, 2.0, "Guten Tag zusammen."), Segment(2.6, 4.5, "Danke für die Einladung.")]


def recording(tmp_path):
    folder = tmp_path / "rec"
    folder.mkdir()
    for track in ("me", "others"):
        sf.write(folder / f"{track}.wav", np.zeros(5 * 16_000, dtype=np.float32), 16_000)
    return folder


def test_transcript_has_speakers_of_the_others(tmp_path, no_real_diarization):
    no_real_diarization.value = [(0.0, 2.3, 0), (2.4, 5.0, 1)]
    folder = recording(tmp_path)
    pipeline.create_transcript(folder, TwoSentences(), "fake", {"me": "Andrea", "others": "Gegenüber"},
                               diarize={"others": True, "me": False})
    data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
    others = [s for s in data["segments"] if s["track"] == "others"]
    assert [s["speaker"] for s in others] == ["Gegenüber 1", "Gegenüber 2"]
    assert {s["speaker"] for s in data["segments"] if s["track"] == "me"} == {"Andrea"}   # own track untouched
    assert data["speakers"] == {"others-1": {"name": "Gegenüber 1", "track": "others"},
                                "others-2": {"name": "Gegenüber 2", "track": "others"}}
    assert "Gegenüber 2:**" in (folder / "transcript.md").read_text(encoding="utf-8")


def test_switched_off_means_no_speakers(tmp_path, no_real_diarization):
    no_real_diarization.value = [(0.0, 2.3, 0), (2.4, 5.0, 1)]
    folder = recording(tmp_path)
    pipeline.create_transcript(folder, TwoSentences(), "fake", {"me": "Andrea", "others": "Gegenüber"},
                               diarize={"others": False, "me": False})
    data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
    assert data["speakers"] == {} and {s["speaker"] for s in data["segments"]} == {"Andrea", "Gegenüber"}


def test_failing_diarization_keeps_the_transcript(tmp_path, monkeypatch):
    def broken(audio, folder=None, **kwargs):
        raise RuntimeError("Modell defekt")
    monkeypatch.setattr(diarization, "find_turns", broken)
    folder = recording(tmp_path)
    pipeline.create_transcript(folder, TwoSentences(), "fake", {"me": "Andrea", "others": "Gegenüber"},
                               diarize={"others": True})
    data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
    assert len(data["segments"]) == 4 and "Modell defekt" in data["header"]["Sprecher"]


# ---------------------------------------------------------------- naming, merging, samples (service)

def service_with_speakers(no_real_diarization):
    no_real_diarization.value = [(0.0, 0.5, 0), (0.5, 1.0, 1)]
    s = make_service()
    rid = s.start_recording(consent=True)
    s.stop_recording()
    assert wait_until(lambda: (s._path(rid) / "transcript.json").exists())
    return s, rid


def test_settings_switch_diarization_per_track():
    s = make_service()
    assert (s._s.diarize_others, s._s.diarize_me) == ("on", "off")      # others on, own track off
    s.save_settings({"diarize_me": "on", "diarize_others": "off"})
    assert (s._s.diarize_others, s._s.diarize_me) == ("off", "on")


def test_speaker_split_setting_sets_the_threshold(no_real_diarization, monkeypatch):
    """«Sprechertrennung: Eher weniger Personen» clusters with the higher threshold – Teams calls split one
    person into 7–19 speakers at 0.7 (measured 19 Oct 2026)."""
    used = []
    monkeypatch.setattr(diarization, "find_turns",
                        lambda audio, folder=None, **kwargs: used.append(kwargs.get("threshold")) or [(0.0, 1.0, 0)])
    s = make_service()
    assert s._s.speaker_split == "normal"
    s.save_settings({"speaker_split": "something else"})
    assert s._s.speaker_split == "normal"
    s.save_settings({"speaker_split": "fewer"})
    rid = s.start_recording(consent=True)
    s.stop_recording()
    assert wait_until(lambda: (s._path(rid) / "transcript.json").exists())
    assert used == [diarization.THRESHOLD_FEWER] and diarization.THRESHOLD_FEWER > diarization.THRESHOLD


def test_asides_setting_is_kept_and_checked():
    s = make_service()
    assert s._s.asides == "on"
    s.save_settings({"asides": "off"})
    assert s._s.asides == "off"
    s.save_settings({"asides": "maybe"})
    assert s._s.asides == "on"


def test_rename_merge_and_reassign(no_real_diarization):
    s, rid = service_with_speakers(no_real_diarization)
    folder, data = s._transcript_data(rid)
    # the fake transcriber gives one segment per track; add a second «others» speaker by hand
    data["segments"].append({**data["segments"][-1], "start": 2.0, "end": 3.0, "text": "Noch etwas.",
                             "speaker": "Gegenüber 2", "speaker_id": "others-2", "track": "others"})
    data["speakers"]["others-2"] = {"name": "Gegenüber 2", "track": "others"}
    s._write_transcript(folder, data)
    first = next(sp["id"] for sp in s.speakers(rid))

    speakers = s.rename_speakers(rid, {"others-2": "Hans Muster"})
    assert {sp["name"] for sp in speakers} >= {"Hans Muster"}
    assert "Hans Muster:**" in (folder / "transcript.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="leer"):
        s.rename_speakers(rid, {"others-2": "  "})

    index = next(i for i, seg in enumerate(s._transcript_data(rid)[1]["segments"]) if seg["speaker_id"] == "others-2")
    s.set_paragraph_speaker(rid, index, first)
    assert s._transcript_data(rid)[1]["segments"][index]["speaker_id"] == first

    s.rename_speakers(rid, {"others-2": "Hans Muster"})
    remaining = s.merge_speakers(rid, "others-2", first)
    assert [sp["id"] for sp in remaining] == [first]


def test_speaker_sample_is_playable_wav(no_real_diarization):
    s, rid = service_with_speakers(no_real_diarization)
    sid = s.speakers(rid)[0]["id"]
    sample = s.speaker_sample(rid, sid)
    assert sample["url"].startswith("data:audio/wav;base64,")
    import base64
    raw = base64.b64decode(sample["url"].split(",", 1)[1])
    assert raw[:4] == b"RIFF" and sf.info(io.BytesIO(raw)).frames > 0


def test_reference_and_compare_use_the_track_not_the_name(tmp_path):
    from verbalis.evaluation import load_reference
    (tmp_path / "transcript.json").write_text(json.dumps({"tracks": {"me": "Andrea", "others": "Gegenüber"},
        "edited": True, "segments": [
            {"start": 0, "end": 1, "text": "Hallo", "speaker": "Andrea", "track": "me"},
            {"start": 1, "end": 2, "text": "Grüezi", "speaker": "Hans Muster", "track": "others"},
            {"start": 2, "end": 3, "text": "Merci", "speaker": "Gegenüber 2", "track": "others"}]}), encoding="utf-8")
    ref = load_reference("transcript", tmp_path)
    assert ref.tracks == {"me": "Hallo", "others": "Grüezi Merci"}


def test_merging_never_loses_a_given_name(no_real_diarization):
    """0.7.17: merging «Hans Muster» into the unnamed «Gegenüber 1» kept «Gegenüber 1» – the name was lost."""
    s, rid = service_with_speakers(no_real_diarization)
    folder, data = s._transcript_data(rid)
    data["segments"].append({**data["segments"][-1], "start": 2.0, "end": 3.0, "text": "Noch etwas.",
                             "speaker": "Gegenüber 2", "speaker_id": "others-2", "track": "others"})
    data["segments"].append({**data["segments"][-1], "start": 4.0, "end": 5.0, "text": "Und das.",
                             "speaker": "Gegenüber 3", "speaker_id": "others-3", "track": "others"})
    data["speakers"].update({"others-2": {"name": "Gegenüber 2", "track": "others"},
                             "others-3": {"name": "Gegenüber 3", "track": "others"}})
    s._write_transcript(folder, data)
    first = next(sp["id"] for sp in s.speakers(rid) if sp["track"] == "others")

    s.rename_speakers(rid, {"others-2": "Hans Muster"})
    s.merge_speakers(rid, "others-2", first)                   # target unnamed → takes the given name
    names = {sp["id"]: sp["name"] for sp in s.speakers(rid)}
    assert names[first] == "Hans Muster"
    assert all(seg["speaker"] == "Hans Muster" for seg in s._transcript_data(rid)[1]["segments"]
               if seg.get("speaker_id") == first)

    s.rename_speakers(rid, {"others-3": "Eva Beispiel"})
    s.merge_speakers(rid, "others-3", first)                   # both named → the target's name wins
    assert {sp["id"]: sp["name"] for sp in s.speakers(rid)}[first] == "Hans Muster"


# ---------------------------------------------------------------- fewer, more plausible speakers

VOICES = {0: [1.0, 0.0, 0.0], 1: [0.0, 1.0, 0.0], 2: [0.9, 0.1, 0.0], 3: [0.0, 0.0, 1.0]}


def fake_embed(turns):
    """Voice print of whoever speaks in the given intervals (looked up in `turns`)."""
    def embed(intervals):
        speaker = next(sp for s, e, sp in turns if (s, e) == tuple(intervals[0]))
        return VOICES[speaker]
    return embed


def test_speaker_with_only_short_turns_goes_to_the_most_similar_voice():
    """0.7.18: a 40-min call with 4 people gave 60+ speakers – short turns created speakers of their own."""
    turns = [(0, 30, 0), (30, 60, 1), (61, 62, 2), (70, 71.2, 2)]     # speaker 2: only short turns, voice like 0
    refined = diarization.refine(turns, fake_embed(turns), small_s=0)
    assert [sp for _, _, sp in refined] == [0, 1, 0, 0]


def test_small_speaker_merged_only_when_the_voice_is_close():
    turns = [(0, 60, 0), (60, 120, 1), (121, 126, 2), (130, 135, 3)]  # 2 sounds like 0, 3 like nobody
    refined = diarization.refine(turns, fake_embed(turns))
    assert [sp for _, _, sp in refined] == [0, 1, 0, 3]


def test_known_number_of_people_joins_the_similar_voices_not_the_outliers():
    """0.7.26: on site with 2 people, the clustering told «2» put nearly everything into one speaker and a few
    coughs into the other (56 % right). Now the many small, pure speakers are joined by voice."""
    voices = {0: [1.0, 0.1, 0.0], 1: [0.9, 0.2, 0.0], 2: [0.1, 1.0, 0.0], 3: [0.0, 0.9, 0.2], 4: [0.0, 0.0, 1.0]}
    turns = [(0, 60, 0), (60, 120, 2), (120, 170, 1), (170, 230, 3), (231, 234, 4)]   # 4: a cough, like nobody

    def embed(intervals):
        return voices[next(sp for s, e, sp in turns if (s, e) == tuple(intervals[0]))]

    who = [sp for _, _, sp in diarization.merge_to_count(turns, embed, 2)]
    assert len(set(who)) == 2
    assert who[0] == who[2] and who[1] == who[3] and who[0] != who[1]


def test_known_number_of_people_leaves_fewer_speakers_alone():
    turns = [(0, 60, 0), (60, 120, 1)]
    assert diarization.merge_to_count(turns, lambda intervals: [1.0, 0.0], 3) == turns


def test_reassign_with_known_number_of_people_keeps_given_names(no_real_diarization):
    s, rid = service_with_speakers(no_real_diarization)
    folder, data = s._transcript_data(rid)
    others = next(seg for seg in data["segments"] if seg["track"] == "others")
    for i, (start, end) in enumerate([(0.0, 0.4), (0.5, 0.9)]):
        data["segments"].append({**others, "start": start + 2, "end": end + 2, "text": f"Teil {i}",
                                 "speaker_id": f"others-{i + 5}", "speaker": "Hans Muster" if i == 0 else "Gegenüber 6"})
    data["speakers"].update({"others-5": {"name": "Hans Muster", "track": "others"},
                             "others-6": {"name": "Gegenüber 6", "track": "others"}})
    s._write_transcript(folder, data)

    asked = {}
    no_real_diarization.value = [(0.0, 2.45, 0), (2.45, 5.0, 1)]
    from verbalis import diarization as d
    real = d.find_turns

    def counting(audio, folder=None, **kwargs):
        asked.update(kwargs)
        return real(audio, folder, **kwargs)
    d.find_turns = counting
    try:
        s.reassign_speakers(rid, "others", 2)            # runs in the background, like a transcription
        assert wait_until(lambda: "num_speakers" in asked and s.recordings()[0]["status"] == "done")
    finally:
        d.find_turns = real
    assert asked["num_speakers"] == 2 and callable(asked["progress"])
    speakers = s.speakers(rid)
    names = sorted(sp["name"] for sp in speakers if sp["track"] == "others")
    assert names == ["Gegenüber 2", "Hans Muster"]                    # the given name survived
    assert {sp["track"] for sp in speakers} == {"others"}
    with pytest.raises(ValueError, match="Anzahl"):
        s.reassign_speakers(rid, "others", 0)


def test_speakers_test_prints_only_numbers(tmp_path, monkeypatch, capsys, no_real_diarization):
    from verbalis import cli
    folder = recording(tmp_path)
    no_real_diarization.value = [(0.0, 2.0, 0), (2.0, 4.0, 1), (4.0, 4.5, 2)]
    monkeypatch.setattr(diarization, "embedder", lambda audio, folder=None: lambda intervals: [1.0, 0.0])
    assert cli.main(["speakers-test", str(folder), "--thresholds", "0.5", "0.9"]) == 0
    out = capsys.readouterr().out
    assert "Schwelle 0.50:   3 Sprecher roh,   1 bereinigt" in out and "Schwelle 0.90" in out


def test_diarization_runs_in_its_own_process_and_reports_errors(tmp_path, monkeypatch):
    """0.7.18 bug: sherpa-onnx blocks Python while it computes – the app froze during «Neu zuordnen».
    It now runs in a separate process; errors there come back readable."""
    monkeypatch.setattr(diarization, "SEPARATE_PROCESS", True)
    with pytest.raises(RuntimeError) as error:
        diarization.turns_for_file(tmp_path / "fehlt.flac")
    assert "fehlt.flac" in str(error.value)
