"""Compressing and retaining the audio files."""

import json
import threading
from datetime import datetime, timedelta

import numpy as np
import pytest
import soundfile as sf

from verbalis import pipeline
from verbalis.service import MB, Service
from verbalis.settings import Settings


def _wav(path, seconds=3.0, sr=48000):
    t = np.arange(int(seconds * sr)) / sr
    sf.write(path, (0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), sr)


def _recording(base, days_old: float, transcript=True, mb=0.5):
    start = datetime.now().astimezone() - timedelta(days=days_old)
    folder = base / start.strftime("%Y-%m-%d_%H%M%S")
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"start": start.isoformat(timespec="seconds")}))
    for track in pipeline.TRACKS:
        (folder / f"{track}.flac").write_bytes(b"x" * int(mb * MB / 2))
    if transcript:
        (folder / "transcript.json").write_text('{"segments": []}')
    return folder


def _service(**settings):
    return Service(settings=Settings(**settings), list_devices=lambda: {}, cleanup_on_start=False)


def test_compress_wav_to_flac(tmp_path):
    for track in pipeline.TRACKS:
        _wav(tmp_path / f"{track}.wav")
    before = pipeline.audio_bytes(tmp_path)
    assert pipeline.compress_audio(tmp_path) == 2
    assert not (tmp_path / "me.wav").exists()
    data, sr = sf.read(tmp_path / "me.flac")
    assert sr == 16000 and abs(len(data) - 48000) < 10
    assert 0.35 < np.abs(data[1000:-1000]).max() < 0.45     # tone preserved
    assert pipeline.audio_bytes(tmp_path) < before / 3
    assert pipeline.read_meta(tmp_path)["audio"]["samplerate"] == 16000
    assert pipeline.audio_file(tmp_path, "me").suffix == ".flac"


def test_delete_audio_keeps_transcript(tmp_path):
    folder = _recording(tmp_path, 0, mb=1)
    assert pipeline.delete_audio(folder, "Test") == MB
    assert not pipeline.has_audio(folder) and pipeline.is_recording_folder(folder)
    assert (folder / "transcript.json").exists()
    assert pipeline.read_meta(folder)["audio_deleted"]["reason"] == "Test"


def test_retention_in_days(home):
    base = home / "recordings"
    old = _recording(base, 4)
    new = _recording(base, 1)
    without_transcript = _recording(base, 10, transcript=False)
    s = _service(audio_days="3")
    assert s.cleanup() == [old.name]
    assert pipeline.has_audio(new) and pipeline.has_audio(without_transcript)   # protected without transcript
    entry = {r["id"]: r for r in s.recordings()}
    assert entry[old.name]["audio"] is False
    assert entry[new.name]["audio_delete"][:10] == (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")


def test_zero_days_and_unlimited(home):
    r = _recording(home / "recordings", 0.01)
    assert _service(audio_days="").cleanup() == []
    assert _service(audio_days="0").cleanup() == [r.name]


def test_size_limit_deletes_oldest_first(home):
    base = home / "recordings"
    a = _recording(base, 2.0, mb=4)
    b = _recording(base, 1.5, mb=4)
    c = _recording(base, 1.0, mb=4)
    s = _service(audio_days="", audio_max_mb="9")
    assert s.audio_usage() == {"audio_mb": 12.0}
    assert s.cleanup() == [a.name]
    assert s.audio_usage() == {"audio_mb": 8.0}
    assert pipeline.has_audio(b) and pipeline.has_audio(c)


def test_no_retranscription_without_audio(home):
    folder = _recording(home / "recordings", 0)
    s = _service()
    s.delete_audio(folder.name)
    with pytest.raises(RuntimeError, match="gelöscht"):
        s.transcribe(folder.name)


def test_settings_validate_input():
    s = Settings.from_dict({"audio_days": "abc", "audio_max_mb": "-5"})
    assert (s.days, s.max_mb) == (3, None)
    assert Settings.from_dict({"audio_days": "", "audio_max_mb": "500"}).max_mb == 500


def test_size_query_while_compressing(tmp_path):
    """Regression: GitHub Action on Windows – FileNotFoundError for gegenueber.wav.

    The UI queries the size while the background thread deletes the WAV after
    compressing.
    """
    errors = []
    for round_ in range(20):
        folder = tmp_path / f"r{round_}"
        folder.mkdir()
        for track in pipeline.TRACKS:
            _wav(folder / f"{track}.wav", seconds=1)
        stop = threading.Event()

        def query():
            while not stop.is_set():
                try:
                    pipeline.audio_bytes(folder)
                except FileNotFoundError as e:
                    errors.append(e)
                    return

        t = threading.Thread(target=query)
        t.start()
        pipeline.compress_audio(folder)
        stop.set()
        t.join()
    assert errors == []
