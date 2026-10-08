"""Merge the segments of both tracks into one conversation.

The tracks are in sync (see recorder), so sorting all segments by start time
is enough. Consecutive segments of the same person become one paragraph.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

from .transcription.base import Segment

MAX_PAUSE_IN_PARAGRAPH_S = 2.0


def merge(tracks: dict[str, list[Segment]]) -> list[Segment]:
    """tracks: display name → segments."""
    everything = [replace(s, speaker=name) for name, segments in tracks.items() for s in segments]
    everything.sort(key=lambda s: (s.start, s.end))

    paragraphs: list[Segment] = []
    for s in everything:
        last = paragraphs[-1] if paragraphs else None
        if last and last.speaker == s.speaker and s.start - last.end <= MAX_PAUSE_IN_PARAGRAPH_S:
            paragraphs[-1] = replace(last, end=max(last.end, s.end), text=f"{last.text} {s.text}")
        else:
            paragraphs.append(s)
    return paragraphs


def _time(seconds: float) -> str:
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def to_markdown(paragraphs: list[Segment], title: str, header: dict[str, str]) -> str:
    lines = [f"# {title}", ""]
    lines += [f"- **{k}:** {v}" for k, v in header.items()]
    lines.append("")
    for p in paragraphs:
        lines.append(f"**[{_time(p.start)}] {p.speaker}:** {p.text}")
        lines.append("")
    return "\n".join(lines)


def save(folder: Path, filename: str, paragraphs: list[Segment], title: str, header: dict[str, str],
         tracks: dict[str, str] | None = None) -> Path:
    """tracks: track → display name, e.g. {"me": "Andrea", "others": "Gegenüber"}.

    `header` holds user-facing labels and values (German), shown in the
    Markdown file and in the app.
    """
    md = folder / f"{filename}.md"
    md.write_text(to_markdown(paragraphs, title, header), encoding="utf-8")
    data = {"title": title, "header": header, "tracks": tracks or {}, "segments": [asdict(p) for p in paragraphs]}
    (folder / f"{filename}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return md
