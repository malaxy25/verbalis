"""Speaker diarization: who of the others is speaking when.

Uses sherpa-onnx (Apache 2.0) with two small ONNX models, downloaded once into
~/.verbalis/models/diarization/ from fixed URLs with fixed SHA-256:
- segmentation: pyannote segmentation 3.0 (MIT) – finds speech turns and speaker changes
- embedding: 3D-Speaker ERes2Net (Apache 2.0) – a «voice print» per turn for clustering
In a test with three synthetic voices this embedding model grouped all turns correctly
at threshold 0.7; the English VoxCeleb model mixed up two similar voices.

Real calls gave far too many speakers (60+ for 4 people), mostly from short turns
and short coughs/interjections. After clustering, `refine` therefore
- gives turns of speakers who only ever say something short (< MIN_TURN_S) to the
  most similar established speaker, and
- merges speakers with little talk time into the most similar one when close enough.
With a known number of people (`num_speakers`) the same happens first; then `merge_to_count`
joins the most similar speakers until that number is left. (Until 0.7.26 the clustering was told the
number directly: in an on-site meeting with 2 people it put nearly everything into one speaker and a few
coughs into the other – 56 % right, while the many small speakers without the number were 94 % pure.)

The voice prints only exist while a recording is processed – nothing is stored, so
no voice database is built (recognising people across calls would be a separate,
opt-in feature).
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import tarfile
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

from .transcript import is_default_name
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
MIN_TURN_S = 1.5         # a speaker with only shorter turns is no speaker of its own
SMALL_SPEAKER_S = 20.0   # speakers with less talk time are merged into a similar one …
MERGE_DISTANCE = 0.8     # … if their voice prints are at most this far apart (cosine distance)
PROFILE_S = 30.0         # seconds of audio per voice print
MERGE_PROFILE_S = 120.0  # … when joining down to a known number of people (more audio: 75 % instead of 71 % right)
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


def _config(folder: Path, threshold: float):
    import sherpa_onnx

    threads = _threads()
    return sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(folder / SEGMENTATION["file"])), num_threads=threads),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(folder / EMBEDDING["file"]),
                                                               num_threads=threads),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=threshold),
        min_duration_on=0.3, min_duration_off=0.5)


def find_turns(audio, folder: Path | None = None, threshold: float = THRESHOLD, num_speakers: int | None = None,
               refine_turns: bool = True, progress=None) -> list[tuple[float, float, int]]:
    """(start, end, speaker index) for 16 kHz mono float32 audio.

    num_speakers: the known number of people on this track (the found speakers are merged down to it).
    progress(fraction) is called while sherpa-onnx works.
    """
    import sherpa_onnx

    folder = folder or models_dir()
    diarizer = sherpa_onnx.OfflineSpeakerDiarization(_config(folder, threshold))
    started = time.monotonic()

    def report(done, total):
        if progress:
            progress(done / total if total else 0.0)
        return 0   # non-zero would abort

    result = diarizer.process(audio, callback=report).sort_by_start_time()
    turns = [(r.start, r.end, r.speaker) for r in result]
    found = len({t[2] for t in turns})
    if refine_turns and found > 1:
        turns = refine(turns, embedder(audio, folder))
    if num_speakers and found > num_speakers:
            turns = merge_to_count(turns, embedder(audio, folder, MERGE_PROFILE_S), num_speakers)
    log.info("Diarization: %d turns, %d speakers (%d before refining), %.1f s for %.0f s audio",
             len(turns), len({t[2] for t in turns}), found, time.monotonic() - started, len(audio) / SAMPLERATE)
    return turns


# sherpa-onnx keeps Python's global lock while it computes: in the app's process every other thread –
# also the one answering the window – stood still for minutes («the app freezes»). So the app runs it
# in a separate process. Tests switch this off: they replace find_turns with a fake.
SEPARATE_PROCESS = True


def turns_for_file(path: Path, until_s: float | None = None, progress=None, **options) -> list[tuple[float, float, int]]:
    """find_turns for an audio file, in a separate process. progress(fraction) is called in this process."""
    if not SEPARATE_PROCESS:
        from .transcription.faster import load_audio
        return find_turns(load_audio(Path(path), until_s), progress=progress, **options)
    import multiprocessing
    import queue

    context = multiprocessing.get_context("spawn")
    messages = context.Queue()
    process = context.Process(target=_turns_worker, args=(str(path), until_s, options, messages),
                              name="verbalis-diarization", daemon=True)
    process.start()
    try:
        while True:
            try:
                kind, value = messages.get(timeout=0.5)
            except queue.Empty:
                if process.is_alive():
                    continue
                try:
                    kind, value = messages.get(timeout=1)
                except queue.Empty:
                    raise RuntimeError("Die Sprechererkennung wurde unerwartet beendet.") from None
            if kind == "progress":
                if progress:
                    progress(value)
            elif kind == "result":
                return [(float(s), float(e), int(sp)) for s, e, sp in value]
            else:
                raise RuntimeError(value)
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)


def _turns_worker(path: str, until_s, options: dict, messages) -> None:
    """Runs in the separate process."""
    try:
        from .transcription.faster import load_audio
        audio = load_audio(Path(path), until_s)
        messages.put(("result", find_turns(audio, progress=lambda f: messages.put(("progress", f)), **options)))
    except Exception as e:
        messages.put(("error", str(e) or repr(e)))


def embedder(audio, folder: Path | None = None, profile_s: float = PROFILE_S):
    """A function (intervals) → voice print from up to profile_s seconds of them, for the given audio."""
    import numpy as np
    import sherpa_onnx

    folder = folder or models_dir()
    extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(folder / EMBEDDING["file"]), num_threads=_threads()))

    def embed(intervals: list[tuple[float, float]]) -> list[float]:
        pieces, total = [], 0.0
        for start, end in intervals:
            take = min(end - start, profile_s - total)
            if take <= 0:
                break
            pieces.append(audio[int(start * SAMPLERATE):int((start + take) * SAMPLERATE)])
            total += take
        samples = np.concatenate(pieces) if pieces else np.zeros(SAMPLERATE // 2, dtype=np.float32)
        stream = extractor.create_stream()
        stream.accept_waveform(sample_rate=SAMPLERATE, waveform=samples.astype(np.float32, copy=False))
        stream.input_finished()
        return list(extractor.compute(stream))

    return embed


def distance(a, b) -> float:
    """Cosine distance of two voice prints (0 = same direction, 2 = opposite)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 1.0 - dot / norm if norm else 2.0


def refine(turns: list[tuple[float, float, int]], embed, min_turn_s: float = MIN_TURN_S,
           small_s: float = SMALL_SPEAKER_S, merge_distance: float = MERGE_DISTANCE) -> list[tuple[float, float, int]]:
    """Fewer, more plausible speakers (see module docstring). embed(intervals) → voice print."""
    def by_speaker(ts):
        groups: dict[int, list[tuple[float, float]]] = {}
        for start, end, speaker in ts:
            groups.setdefault(speaker, []).append((start, end))
        return groups

    groups = by_speaker(turns)
    established = {sp for sp, spans in groups.items() if any(e - s >= min_turn_s for s, e in spans)}
    if not established:
        return turns
    # voice prints from the longest turns
    profiles = {sp: embed(sorted(groups[sp], key=lambda t: t[0] - t[1])) for sp in established}
    relabel: dict[int, int] = {}
    for sp in groups:
        if sp not in established:   # only short turns: belongs to the most similar real speaker
            print_ = embed(groups[sp])
            relabel[sp] = min(established, key=lambda other: distance(print_, profiles[other]))
    turns = [(s, e, relabel.get(sp, sp)) for s, e, sp in turns]

    # second pass: little talk time and a similar voice → the same person
    talk = {sp: sum(e - s for s, e in spans) for sp, spans in by_speaker(turns).items()}
    for sp in sorted(talk, key=talk.get):
        if talk[sp] >= small_s or len(talk) <= 1:
            continue
        others = [o for o in talk if o != sp]
        nearest = min(others, key=lambda o: distance(profiles[sp], profiles[o]))
        if distance(profiles[sp], profiles[nearest]) <= merge_distance:
            turns = [(s, e, nearest if x == sp else x) for s, e, x in turns]
            talk[nearest] += talk.pop(sp)
    return turns


def merge_to_count(turns: list[tuple[float, float, int]], embed, count: int,
                   small_s: float = SMALL_SPEAKER_S) -> list[tuple[float, float, int]]:
    """Join speakers until `count` are left. embed(intervals) → voice print.

    A speaker with little talk time (coughs, noise) first goes to the most similar voice – otherwise such
    an outlier would stay a «person» of its own. Then the two most similar voices are joined, again and again.
    """
    talk: dict[int, float] = {}
    spans: dict[int, list[tuple[float, float]]] = {}
    for start, end, speaker in turns:
        talk[speaker] = talk.get(speaker, 0.0) + end - start
        spans.setdefault(speaker, []).append((start, end))
    if len(talk) <= max(1, count):
        return turns
    profiles = {sp: _unit(embed(sorted(spans[sp], key=lambda t: t[0] - t[1]))) for sp in talk}
    joined: dict[int, int] = {}
    while len(talk) > count:
        smallest = min(talk, key=talk.get)
        if talk[smallest] < small_s:
            gone = smallest
            stays = min((o for o in talk if o != gone), key=lambda o: distance(profiles[gone], profiles[o]))
        else:
            pairs = [(a, b) for a in talk for b in talk if a < b]
            a, b = min(pairs, key=lambda p: distance(profiles[p[0]], profiles[p[1]]))
            stays, gone = (a, b) if talk[a] >= talk[b] else (b, a)
        weight = talk[gone] / (talk[stays] + talk[gone])   # the joined voice print: weighted by talk time
        profiles[stays] = _unit([x * (1 - weight) + y * weight for x, y in zip(profiles[stays], profiles[gone])])
        talk[stays] += talk.pop(gone)
        del profiles[gone]
        joined[gone] = stays
        for old, new in joined.items():
            if new == gone:
                joined[old] = stays
    return [(s, e, joined.get(sp, sp)) for s, e, sp in turns]


def _unit(vector) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else list(vector)


def reassign_names(old: list[dict], new: list, base_name: str) -> dict[str, str]:
    """After diarizing again: new speaker id → name the user had given, where the voices overlap most.

    old: segments as stored before (with speaker_id and speaker); new: the same segments re-assigned.
    """
    overlap: dict[tuple[str, str], float] = {}
    named = {}
    for before, after in zip(old, new):
        sid = before.get("speaker_id")
        if not sid or is_default_name(before.get("speaker") or "", base_name):
            continue
        named[sid] = before["speaker"]
        key = (sid, after.speaker_id)
        overlap[key] = overlap.get(key, 0.0) + before["end"] - before["start"]
    result: dict[str, str] = {}
    used: set[str] = set()
    for (sid, new_id), _ in sorted(overlap.items(), key=lambda kv: -kv[1]):
        if new_id in result or sid in used:
            continue
        result[new_id] = named[sid]
        used.add(sid)
    return result


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
