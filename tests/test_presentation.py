"""tools/presentation.py – prepares a presented talk for the /presentation-transcript skill."""

import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import presentation  # noqa: E402

RATE = 16000


def bursts(seconds: float, pattern_seed: int = 1) -> np.ndarray:
    """Speech-like audio: noise bursts of random length and loudness, so the loudness over time is unique."""
    rng = np.random.default_rng(pattern_seed)
    out = np.zeros(int(seconds * RATE), dtype=np.float32)
    t = 0.0
    while t < seconds:
        length, pause = rng.uniform(0.3, 1.5), rng.uniform(0.2, 1.0)
        a, b = int(t * RATE), int(min(t + length, seconds) * RATE)
        out[a:b] = rng.normal(0, rng.uniform(0.05, 0.3), b - a)
        t += length + pause
    return out


def make_video(path: Path, slides: list[tuple[float, int]], seconds: float, audio: np.ndarray):
    """An MP4 with plain coloured «slides» (start time, grey level) and the given sound."""
    import av

    with av.open(str(path), "w") as container:
        video = container.add_stream("mpeg4", rate=5)
        video.width, video.height, video.pix_fmt = 160, 90, "yuv420p"
        sound = container.add_stream("aac", rate=RATE)
        sound.layout = "mono"
        for i in range(int(seconds * 5)):
            level = [g for start, g in slides if start <= i / 5][-1]
            picture = np.full((90, 160, 3), level, dtype=np.uint8)
            picture[70:, 130:] = (i * 37) % 255          # a «webcam tile» that changes all the time
            frame = av.VideoFrame.from_ndarray(picture, format="rgb24")
            frame.pts = i
            container.mux(video.encode(frame))
        container.mux(video.encode(None))
        for n in range(0, len(audio), 1024):
            chunk = audio[n:n + 1024]
            frame = av.AudioFrame.from_ndarray(chunk.reshape(1, -1), format="flt", layout="mono")
            frame.sample_rate, frame.pts = RATE, n
            container.mux(sound.encode(frame))
        container.mux(sound.encode(None))


def make_pptx(path: Path):
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rel = "http://schemas.openxmlformats.org/package/2006/relationships"

    def slide(lines, hidden=False):
        body = "".join(f"<a:p><a:r><a:t>{x}</a:t></a:r></a:p>" for x in lines)
        show = ' show="0"' if hidden else ""
        return (f'<p:sld xmlns:a="{a}" xmlns:p="{p}"{show}><p:cSld><p:spTree><p:sp>'
                f"<p:txBody>{body}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>")

    with zipfile.ZipFile(path, "w") as z:
        z.writestr("ppt/presentation.xml", f'<p:presentation xmlns:p="{p}" xmlns:r="{r}"><p:sldIdLst>'
                   '<p:sldId id="256" r:id="rId9"/><p:sldId id="257" r:id="rId8"/></p:sldIdLst></p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels", f'<Relationships xmlns="{rel}">'
                   '<Relationship Id="rId8" Target="slides/slide2.xml"/>'
                   '<Relationship Id="rId9" Target="slides/slide1.xml"/></Relationships>')
        z.writestr("ppt/slides/slide1.xml", slide(["Willkommen", "Agenda   heute"]))
        z.writestr("ppt/slides/slide2.xml", slide(["Backup"], hidden=True))
        z.writestr("ppt/slides/_rels/slide1.xml.rels", f'<Relationships xmlns="{rel}">'
                   '<Relationship Id="rId2" Target="../notesSlides/notesSlide1.xml"/></Relationships>')
        z.writestr("ppt/notesSlides/notesSlide1.xml", f'<p:notes xmlns:a="{a}" xmlns:p="{p}"><a:p><a:r><a:t>'
                   "Kurz vorstellen</a:t></a:r></a:p><a:p><a:r><a:t>1</a:t></a:r></a:p></p:notes>")


def test_pptx_text_and_notes_in_presentation_order(tmp_path):
    make_pptx(tmp_path / "talk.pptx")
    slides = presentation.pptx_slides(tmp_path / "talk.pptx")
    assert slides == [
        {"number": 1, "hidden": False, "text": ["Willkommen", "Agenda heute"], "notes": ["Kurz vorstellen"]},
        {"number": 2, "hidden": True, "text": ["Backup"], "notes": []}]


def test_scenes_ignore_a_moving_webcam_tile_and_skip_transitions():
    def small(level, tile=0):
        pic = np.full((36, 64), level, dtype=np.uint8)
        pic[30:, 56:] = tile
        return pic

    samples = [(0, small(10, 0), "a0"), (2, small(10, 200), "a1"), (4, small(10, 50), "a2"),
               (6, small(120), "half-built"), (8, small(200), "b1"), (10, small(200), "b2"),
               (12, small(90), "c0")]                           # the last scene has a single sample
    assert list(presentation.scenes_of(samples)) == [(0, "a1"), (6, "half-built"), (8, "b2"), (12, "c0")]


def test_whole_run_finds_scenes_and_the_offset_between_video_and_recording(tmp_path):
    speech = bursts(40)
    folder = tmp_path / "2026-10-28_100000"
    folder.mkdir()
    # Verbalis started 7 s after the Teams recording: recording time 0 = video time 7
    sf.write(folder / "others.flac", speech[7 * RATE:], RATE)
    (folder / "transcript.json").write_text(json.dumps({"segments": [
        {"start": 1.0, "end": 4.0, "speaker": "Basil", "text": "Willkommen zur Schulung."},
        {"start": 15.0, "end": 18.0, "speaker": "Sandra", "text": "Eine Frage zum Ablauf.", "aside": True}]}),
        encoding="utf-8")
    make_video(tmp_path / "talk.mp4", [(0, 30), (12, 220)], 30, speech[:30 * RATE])
    make_pptx(tmp_path / "talk.pptx")

    assert presentation.main([str(folder), "--video", str(tmp_path / "talk.mp4"),
                              "--pptx", str(tmp_path / "talk.pptx")]) == 0
    out = folder / "presentation"
    data = json.loads((out / "scenes.json").read_text(encoding="utf-8"))
    assert abs(data["offset_s"] - 7.0) <= 0.2 and data["offset_certainty"] > 0.5
    assert [(s["index"], s["image"]) for s in data["scenes"]] == [(1, "scene_001.png"), (2, "scene_002.png")]
    assert 11 <= data["scenes"][1]["start"] <= 14
    assert (out / "scene_001.png").read_bytes()[:4] == b"\x89PNG" and (out / "overview_01.png").exists()
    md = (out / "timeline.md").read_text(encoding="utf-8")
    first, second = md.split("## Szene 2")
    assert "Willkommen zur Schulung" in first                      # video time 8 s: the first scene
    assert "**Sandra** (Einwurf): Eine Frage" in second            # video time 22 s: the second scene
    assert json.loads((out / "slides.json").read_text(encoding="utf-8"))[0]["text"][0] == "Willkommen"
