"""Speaker diarization: who of the others is speaking when.

Uses sherpa-onnx (Apache 2.0) with two small ONNX models, downloaded once into
~/.verbalis/models/diarization/ from fixed URLs with fixed SHA-256:
- segmentation: pyannote segmentation 3.0 (MIT) – finds speech turns and speaker changes
- embedding: 3D-Speaker ERes2Net (Apache 2.0) – a «voice print» per turn for clustering
In a test with three synthetic voices this embedding model grouped all turns correctly
at threshold 0.7; the English VoxCeleb model mixed up two similar voices.

The voice prints only exist while a recording is processed – nothing is stored, so
no voice database is built (recognising people across calls would be a separate,
opt-in feature).
"""

from __future__ import annotations

import hashlib
import logging
import os
import tarfile
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

from .transcription.base import Segment
from .transcription.models import verbalis_home

log = logging.getLogger(__name__)

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
SEGMENTATION = {
    "url": RELEASES + "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
    "sha256": "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488",
    "file": "segmentation.onnx",            # model.onnx from the archive
}
EMBEDDING = {
    "url": RELEASES + "speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
    "sha256": "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b",
    "file": "embedding.onnx",
}
THRESHOLD = 0.7          # cosine distance for clustering; higher = fewer speakers
SAMPLERATE = 16_000


def models_dir() -> Path:
    return verbalis_home() / "models" / "diarization"


def models_ready(folder: Path | None = None) -> bool:
    folder = folder or models_dir()
    return all((folder / m["file"]).exists() for m in (SEGMENTATION, EMBEDDING))


def _fetch(url: str, sha256: str, opener=urllib.request.urlopen) -> bytes:
    with opener(urllib.request.Request(url, headers={"User-Agent": "Verbalis"}), timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise RuntimeError("Ein Modell für die Sprechererkennung ist beschädigt angekommen (Prüfsumme falsch).")
    return data


def ensure_models(folder: Path | None = None, opener=urllib.request.urlopen) -> Path:
    """Download both models once (about 46 MB). Raises with a German message when offline."""
    folder = folder or models_dir()
    if models_ready(folder):
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if not (folder / SEGMENTATION["file"]).exists():
            archive = folder / "segmentation.tar.bz2"
            archive.write_bytes(_fetch(SEGMENTATION["url"], SEGMENTATION["sha256"], opener))
            with tarfile.open(archive) as tar:
                member = next(m for m in tar.getmembers() if m.name.endswith("/model.onnx"))
                (folder / SEGMENTATION["file"]).write_bytes(tar.extractfile(member).read())
            archive.unlink()
        if not (folder / EMBEDDING["file"]).exists():
            tmp = folder / (EMBEDDING["file"] + ".part")
            tmp.write_bytes(_fetch(EMBEDDING["url"], EMBEDDING["sha256"], opener))
            tmp.replace(folder / EMBEDDING["file"])
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError("Die Modelle für die Sprechererkennung konnten nicht geladen werden "
                           f"(Internetverbindung prüfen). ({e})") from e
    log.info("Speaker diarization models downloaded to %s", folder)
    return folder


def _threads() -> int:
    return max(1, min(4, (os.cpu_count() or 2) - 1))


def find_turns(audio, folder: Path | None = None) -> list[tuple[float, float, int]]:
    """(start, end, speaker index) for 16 kHz mono float32 audio."""
    import sherpa_onnx

    folder = folder or models_dir()
    threads = _threads()
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(folder / SEGMENTATION["file"])), num_threads=threads),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(folder / EMBEDDING["file"]),
                                                               num_threads=threads),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=THRESHOLD),
        min_duration_on=0.3, min_duration_off=0.5)
    diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)
    started = time.monotonic()
    result = diarizer.process(audio).sort_by_start_time()
    turns = [(r.start, r.end, r.speaker) for r in result]
    log.info("Diarization: %d turns, %d speakers, %.1f s for %.0f s audio (%d threads)",
             len(turns), len({t[2] for t in turns}), time.monotonic() - started, len(audio) / SAMPLERATE, threads)
    return turns


def assign(segments: list[Segment], turns: list[tuple[float, float, int]], track: str,
           base_name: str) -> list[Segment]:
    """Give every transcribed segment the speaker who talks most during it.

    Speakers are numbered in order of first appearance. With only one speaker the
    track's display name stays as it is («Gegenüber»); with several they become
    «Gegenüber 1», «Gegenüber 2», … – ready to be renamed in the app.
    """
    order: dict[int, int] = {}
    for _, _, speaker in turns:
        order.setdefault(speaker, len(order) + 1)
    several = len(order) > 1
    result, last = [], None
    for s in segments:
        overlap: dict[int, float] = {}
        for start, end, speaker in turns:
            shared = min(end, s.end) - max(start, s.start)
            if shared > 0:
                overlap[speaker] = overlap.get(speaker, 0.0) + shared
        if overlap:
            speaker = max(overlap, key=overlap.get)
        elif turns:   # no turn overlaps (e.g. very short): the nearest turn
            speaker = min(turns, key=lambda t: min(abs(t[0] - s.end), abs(t[1] - s.start)))[2]
        else:
            speaker = last
        last = speaker
        number = order.get(speaker, 1)
        name = f"{base_name} {number}" if several else base_name
        result.append(replace(s, speaker=name, track=track, speaker_id=f"{track}-{number}"))
    return result
