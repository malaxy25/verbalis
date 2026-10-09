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
    out = diarization.assign(segs((1.5, 6.0), (20.0, 21.0)), turns, "me", "Raum")
    assert out[0].speaker == "Raum 2"                                # 0.5 s vs 4 s overlap
    assert out[1].speaker == "Raum 2"                                # no overlap: nearest turn


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
    def broken(audio, folder=None):
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
