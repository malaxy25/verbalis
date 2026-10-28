"""Prepare a presentation for the /presentation-transcript skill: video scenes, PowerPoint text, timeline.

    python tools/presentation.py <recording folder> --video <Teams recording.mp4> [--pptx <slides.pptx>]

Writes into <recording folder>/presentation/:
- scene_NNN.png   one picture per scene of the video (a slide, a demo, …), 1280 px wide
- overview_NN.png 12 scenes per picture (4 × 3, row by row, small), to compare them with the slides quickly
- slides.json     the PowerPoint: text and speaker notes per slide (if --pptx)
- timeline.md     per scene: time, picture and what was said then (from the Verbalis transcript)
- scenes.json     the same as data, plus the time offset between video and Verbalis recording

The Verbalis recording and the Teams video don't start at the same moment. The offset is found by comparing
the loudness over time of both (the video has the sound of the call too); without --video only slides.json
and the transcript are prepared. Needs only what Verbalis has installed anyway (PyAV, numpy, soundfile).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

SAMPLE_S = 2.0          # look at the video every this many seconds
SMALL = (64, 36)        # pictures are compared at this size (width, height), grey
PIXEL_CHANGE = 25       # a pixel counts as changed above this difference (0–255) …
SCENE_CHANGE = 0.12     # … and a new scene starts when this share of the pixels changed
ENVELOPE_HZ = 10        # loudness values per second for finding the offset
MAX_OFFSET_S = 1800     # video and recording start at most this far apart
IMAGE_WIDTH = 1280
GRID = (4, 3)           # scenes per overview picture: columns, rows

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


# ---------------------------------------------------------------- video scenes

def changed_share(a: np.ndarray, b: np.ndarray) -> float:
    """Share of pixels that changed clearly between two small grey pictures."""
    return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16)) > PIXEL_CHANGE))


def scenes_of(samples, threshold: float = SCENE_CHANGE):
    """(start time, picture) per scene from (time, small grey picture, picture) samples, in order.

    A sample starts a new scene when it differs clearly from the *first* sample of the current scene – so a slow
    build-up (bullets appearing one by one) becomes a new scene once enough has changed. The small webcam tiles
    of a Teams recording move all the time but cover too little of the picture to count. The picture is the one a
    sample after the change: transitions and half-built slides are over by then. Only the current scene is kept
    in memory, so an hour of video needs no more than a few pictures."""
    ref = start = first = None
    picked = True
    for t, small, picture in samples:
        if ref is None or changed_share(ref, small) > threshold:
            if not picked:
                yield start, first
            ref, start, first, picked = small, t, picture, False
        elif not picked:
            yield start, picture
            picked = True
    if not picked:
        yield start, first


def video_samples(video: Path, seen: dict):
    """(time, small grey picture, full picture) every SAMPLE_S seconds. seen["end"]: time of the last frame."""
    import av

    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        next_t, count = 0.0, 0
        for frame in container.decode(stream):
            if frame.time is None:
                continue
            seen["end"] = frame.time
            if frame.time < next_t:
                continue
            small = frame.reformat(width=SMALL[0], height=SMALL[1], format="gray").to_ndarray()
            yield round(frame.time, 2), small, frame
            next_t, count = frame.time + SAMPLE_S, count + 1
            if count % 300 == 0:
                print(f"  Video: {frame.time / 60:.0f} min gelesen", flush=True)


def _height(frame, width: int) -> int:
    return max(2, round(frame.height * width / frame.width / 2) * 2)


def png(rgb: np.ndarray) -> bytes:
    """A picture (height × width × 3, uint8) as PNG – with PyAV, so no Pillow is needed."""
    import av

    frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
    codec = av.CodecContext.create("png", "w")
    codec.width, codec.height, codec.pix_fmt = frame.width, frame.height, "rgb24"
    return b"".join(bytes(p) for p in codec.encode(frame)) + b"".join(bytes(p) for p in codec.encode(None))


def overview(pictures: list[np.ndarray], width: int = 480) -> np.ndarray:
    """Up to GRID pictures in one, row by row, with a thin white line between them."""
    cols, rows = GRID
    h = round(pictures[0].shape[0] * width / pictures[0].shape[1])
    sheet = np.full((rows * (h + 4), cols * (width + 4), 3), 255, dtype=np.uint8)
    for i, pic in enumerate(pictures[:cols * rows]):
        ys = np.linspace(0, pic.shape[0] - 1, h).astype(int)
        xs = np.linspace(0, pic.shape[1] - 1, width).astype(int)
        r, c = divmod(i, cols)
        sheet[r * (h + 4):r * (h + 4) + h, c * (width + 4):c * (width + 4) + width] = pic[ys][:, xs]
    return sheet


# ---------------------------------------------------------------- offset video ↔ recording

def envelope(blocks, rate: int) -> np.ndarray:
    """Loudness (log energy) ENVELOPE_HZ times per second from mono blocks at `rate` Hz."""
    step = rate // ENVELOPE_HZ
    values, rest = [], np.zeros(0, dtype=np.float32)
    for block in blocks:
        data = np.concatenate([rest, block])
        n = len(data) // step
        if n:
            values.append(np.log10(np.mean(data[:n * step].reshape(n, step) ** 2, axis=1) + 1e-10))
        rest = data[n * step:]
    return np.concatenate(values) if values else np.zeros(0)


def video_envelope(video: Path) -> np.ndarray:
    import av

    with av.open(str(video)) as container:
        if not container.streams.audio:
            return np.zeros(0)
        resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)

        def blocks():
            for frame in container.decode(audio=0):
                for out in resampler.resample(frame):
                    yield out.to_ndarray().reshape(-1)
        return envelope(blocks(), 16000)


def recording_envelope(folder: Path) -> np.ndarray:
    """Both Verbalis tracks together – the video has everybody, also the own microphone."""
    import soundfile as sf

    tracks = []
    for name in ("others", "me"):
        path = next((p for p in (folder / f"{name}.flac", folder / f"{name}.wav") if p.exists()), None)
        if path is None:
            continue
        with sf.SoundFile(path) as f:
            rate = f.samplerate
            tracks.append(10 ** envelope((b.mean(axis=1) for b in f.blocks(rate * 10, dtype="float32",
                                                                           always_2d=True)), rate))
    if not tracks:
        return np.zeros(0)
    n = max(len(t) for t in tracks)
    return np.log10(sum(np.pad(t, (0, n - len(t))) for t in tracks) + 1e-10)


def find_offset(video_env: np.ndarray, recording_env: np.ndarray) -> tuple[float, float]:
    """Seconds to add to a recording time to get the video time, and how sure (correlation 0…1)."""
    def norm(x):
        x = np.clip(x, np.percentile(x, 5), None)      # silence of different depth must not count
        return (x - x.mean()) / (x.std() or 1.0)

    v, r = norm(video_env), norm(recording_env)
    size = 1 << int(np.ceil(np.log2(len(v) + len(r))))
    corr = np.fft.irfft(np.fft.rfft(v, size) * np.conj(np.fft.rfft(r, size)), size)
    lags = np.concatenate([np.arange(0, len(v)), np.arange(-len(r) + 1, 0)])
    values = np.concatenate([corr[:len(v)], corr[size - len(r) + 1:]])
    allowed = np.abs(lags) <= MAX_OFFSET_S * ENVELOPE_HZ
    best = int(np.argmax(np.where(allowed, values, -np.inf)))
    lag = int(lags[best])
    overlap = min(len(v), len(r) + lag) - max(0, lag)
    return lag / ENVELOPE_HZ, float(values[best] / max(overlap, 1))


# ---------------------------------------------------------------- PowerPoint

def _texts(xml: bytes) -> list[str]:
    root = ElementTree.fromstring(xml)
    lines = ("".join(t.text or "" for t in p.iter(f"{{{NS['a']}}}t")) for p in root.iter(f"{{{NS['a']}}}p"))
    return [" ".join(line.split()) for line in lines if line.strip()]


def _rels(z: zipfile.ZipFile, part: str) -> dict[str, str]:
    folder, name = part.rsplit("/", 1)
    path = f"{folder}/_rels/{name}.rels"
    if path not in z.namelist():
        return {}
    result = {}
    for rel in ElementTree.fromstring(z.read(path)).iter(f"{{{NS['rel']}}}Relationship"):
        target = rel.get("Target", "")
        parts = [] if target.startswith("/") else folder.split("/")
        for piece in target.lstrip("/").split("/"):
            parts = parts[:-1] if piece == ".." else parts + [piece]
        result[rel.get("Id")] = "/".join(parts)
    return result


def pptx_slides(path: Path) -> list[dict]:
    """Text and speaker notes per slide, in the order of the presentation (hidden slides marked)."""
    with zipfile.ZipFile(path) as z:
        rels = _rels(z, "ppt/presentation.xml")
        order = [rels[s.get(f"{{{NS['r']}}}id")]
                 for s in ElementTree.fromstring(z.read("ppt/presentation.xml")).iter(f"{{{NS['p']}}}sldId")]
        slides = []
        for number, part in enumerate(order, 1):
            xml = z.read(part)
            notes = next((t for t in _rels(z, part).values() if "notesSlide" in t), None)
            note_lines = [line for line in _texts(z.read(notes)) if not re.fullmatch(r"\d+", line)] if notes else []
            slides.append({"number": number, "hidden": ElementTree.fromstring(xml).get("show") == "0",
                           "text": _texts(xml), "notes": note_lines})
    return slides


# ---------------------------------------------------------------- timeline

def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def timeline(scenes: list[dict], segments: list[dict], offset: float) -> list[dict]:
    """The transcript paragraphs per scene. Recording time + offset = video time; before the first scene → first."""
    result = [dict(s, said=[]) for s in scenes]
    for seg in segments:
        t = seg["start"] + offset
        i = max((k for k, s in enumerate(result) if s["start"] <= t), default=0)
        result[i]["said"].append(seg)
    return result


def timeline_md(items: list[dict]) -> str:
    lines = ["# Zeitachse (Video-Zeit)", ""]
    for s in items:
        lines += [f"## Szene {s['index']} · {clock(s['start'])}–{clock(s['end'])} · {s['image']}", ""]
        for seg in s["said"]:
            aside = " (Einwurf)" if seg.get("aside") else ""
            lines.append(f"- [{clock(seg['start'])}] **{seg.get('speaker') or '?'}**{aside}: {seg['text']}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("recording", type=Path, help="Verbalis-Aufnahmeordner (mit transcript.json)")
    parser.add_argument("--video", type=Path, help="Teams-Aufzeichnung (MP4)")
    parser.add_argument("--pptx", type=Path, help="Die gezeigte PowerPoint-Präsentation")
    parser.add_argument("--offset", type=float, help="Video-Zeit minus Aufnahme-Zeit in Sekunden (sonst gemessen)")
    parser.add_argument("--threshold", type=float, default=SCENE_CHANGE,
                        help=f"Anteil geänderter Pixel für eine neue Szene (Standard {SCENE_CHANGE})")
    args = parser.parse_args(argv)

    folder: Path = args.recording
    transcript = folder / "transcript.json"
    if not transcript.exists():
        print(f"Kein Transkript in {folder} – zuerst in Verbalis transkribieren.")
        return 1
    out = folder / "presentation"
    out.mkdir(exist_ok=True)
    segments = json.loads(transcript.read_text(encoding="utf-8")).get("segments") or []

    if args.pptx:
        slides = pptx_slides(args.pptx)
        (out / "slides.json").write_text(json.dumps(slides, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"PowerPoint: {len(slides)} Folien → slides.json")

    if not args.video:
        return 0
    print("Video wird gelesen (bei einer Stunde einige Minuten) …", flush=True)
    seen: dict = {}
    scenes, thumbs = [], []
    for start, frame in scenes_of(video_samples(args.video, seen), args.threshold):
        rgb = frame.reformat(width=IMAGE_WIDTH, height=_height(frame, IMAGE_WIDTH), format="rgb24").to_ndarray()
        name = f"scene_{len(scenes) + 1:03d}.png"
        (out / name).write_bytes(png(rgb))
        thumbs.append(rgb[::3, ::3])          # enough for the overview pictures
        if scenes:
            scenes[-1]["end"] = start
        scenes.append({"index": len(scenes) + 1, "start": start, "end": None, "image": name})
    if not scenes:
        print("Im Video wurden keine Bilder gefunden.")
        return 1
    scenes[-1]["end"] = round(seen.get("end", scenes[-1]["start"]), 2)
    per_sheet = GRID[0] * GRID[1]
    for n in range(0, len(thumbs), per_sheet):
        (out / f"overview_{n // per_sheet + 1:02d}.png").write_bytes(png(overview(thumbs[n:n + per_sheet])))
    print(f"Video: {len(scenes)} Szenen → scene_*.png, overview_*.png")

    if args.offset is not None:
        offset, sure = args.offset, None
    else:
        print("Zeitversatz zwischen Video und Aufnahme wird gemessen …", flush=True)
        offset, sure = find_offset(video_envelope(args.video), recording_envelope(folder))
        print(f"Versatz: Video-Zeit = Aufnahme-Zeit {offset:+.1f} s (Übereinstimmung {sure:.2f}"
              f"{' – unsicher, bitte prüfen' if sure < 0.3 else ''})")
    items = timeline(scenes, segments, offset)
    (out / "timeline.md").write_text(timeline_md(items), encoding="utf-8")
    (out / "scenes.json").write_text(json.dumps({"offset_s": offset, "offset_certainty": sure, "scenes": scenes},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fertig: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
