"""Merge the segments of both tracks into one conversation.

The tracks are in sync (see recorder), so sorting by start time is enough to
interleave them. Reading flow:

- Segments with word timestamps are split into sentences first. Paragraphs are
  then formed from sentences, so when someone asks a question in the middle of a
  long answer, the question appears where it was asked and the answer continues
  in a new paragraph.
- Short interjections («ja», «genau», «mhm») said *while someone else is
  speaking* become asides (`aside=True`): they don't interrupt the paragraph and
  the app shows them in a narrow column next to it. A short «Ja.» as a real
  answer – when nobody else is speaking – stays a normal paragraph.
- Consecutive sentences of the same person become one paragraph.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from pathlib import Path

from .transcription.base import Segment

MAX_PAUSE_IN_PARAGRAPH_S = 2.0
ASIDE_MAX_WORDS = 3      # an interjection has at most this many words …
ASIDE_MAX_S = 1.0        # … or lasts at most this long
SENTENCE_END = (".", "?", "!", "…")


def sentences(segments: list[Segment]) -> list[Segment]:
    """Split segments with word timestamps at sentence ends. Segments without words stay as they are."""
    result: list[Segment] = []
    for s in segments:
        if not s.words:
            result.append(s)
            continue
        current: list = []
        for word in s.words:
            current.append(word)
            if str(word[2]).strip().endswith(SENTENCE_END):
                result.append(_sentence(s, current))
                current = []
        if current:
            result.append(_sentence(s, current))
    return result


def _sentence(segment: Segment, words: list) -> Segment:
    text = "".join(str(w[2]) for w in words).strip()
    return replace(segment, start=float(words[0][0]), end=float(words[-1][1]), text=text, words=list(words))


def _is_short(s: Segment) -> bool:
    return len(s.text.split()) <= ASIDE_MAX_WORDS or s.end - s.start <= ASIDE_MAX_S


def mark_asides(units: list[Segment]) -> list[Segment]:
    """Short units that start while another person is speaking a longer sentence become asides."""
    hosts = [u for u in units if not _is_short(u)]
    result = []
    for u in units:
        aside = _is_short(u) and any(h.speaker != u.speaker and h.start < u.start < h.end for h in hosts)
        result.append(replace(u, aside=aside))
    return result


def merge(tracks: dict[str, list[Segment]]) -> list[Segment]:
    """tracks: display name → segments. Returns paragraphs and asides, sorted by start."""
    # a speaker set by diarization stays; otherwise the track's display name
    units = [replace(s, speaker=s.speaker or name) for name, segments in tracks.items() for s in sentences(segments)]
    units.sort(key=lambda s: (s.start, s.end))
    units = mark_asides(units)

    result: list[Segment] = []
    last_index: int | None = None          # the last paragraph (asides don't count)
    for s in units:
        s = replace(s, words=None)
        if s.aside:
            result.append(s)
            continue
        last = result[last_index] if last_index is not None else None
        if (last and last.speaker == s.speaker and last.speaker_id == s.speaker_id
                and s.start - last.end <= MAX_PAUSE_IN_PARAGRAPH_S):
            result[last_index] = replace(last, end=max(last.end, s.end), text=f"{last.text} {s.text}")
        else:
            result.append(s)
            last_index = len(result) - 1
    return result


def _time(seconds: float) -> str:
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def to_markdown(paragraphs: list[Segment], title: str, header: dict[str, str]) -> str:
    lines = [f"# {title}", ""]
    lines += [f"- **{k}:** {v}" for k, v in header.items()]
    lines.append("")
    for p in paragraphs:
        if p.aside:   # interjection: small, doesn't interrupt the conversation
            lines.append(f"*[{_time(p.start)}] {p.speaker}: {p.text}*")
        else:
            lines.append(f"**[{_time(p.start)}] {p.speaker}:** {p.text}")
        lines.append("")
    return "\n".join(lines)


def segment_dict(p: Segment) -> dict:
    """A paragraph as stored in transcript.json – without word timestamps, `aside` only when set."""
    data = asdict(p)
    data.pop("words", None)
    if not data.get("aside"):
        data.pop("aside", None)
    return data


def segment_from_dict(data: dict) -> Segment:
    return Segment(data["start"], data["end"], data["text"], data.get("speaker"), data.get("track"),
                   data.get("speaker_id"), data.get("words"), bool(data.get("aside")))


def save(folder: Path, filename: str, paragraphs: list[Segment], title: str, header: dict[str, str],
         tracks: dict[str, str] | None = None) -> Path:
    """tracks: track → display name, e.g. {"me": "Andrea", "others": "Gegenüber"}.

    `header` holds user-facing labels and values (German), shown in the
    Markdown file and in the app.
    """
    md = folder / f"{filename}.md"
    md.write_text(to_markdown(paragraphs, title, header), encoding="utf-8")
    data = {"title": title, "header": header, "tracks": tracks or {}, "speakers": speakers_of(paragraphs),
            "segments": [segment_dict(p) for p in paragraphs]}
    (folder / f"{filename}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return md


# Several voices on the microphone are «Person 1, 2, …» (0.7.30): in a meeting on site the others speak into the
# same microphone, so «Ich 1, Ich 2» was wrong. One voice keeps the user's name, the Systemton «Gegenüber 1, 2, …».
MIC_GROUP = "Person"


def is_default_name(name: str, track_name: str) -> bool:
    """Is this the name diarization gave («Gegenüber 2», «Person 3»), not one the user typed?"""
    name = name or ""
    if re.fullmatch(MIC_GROUP + r" \d+", name):
        return True
    return bool(track_name) and re.fullmatch(re.escape(track_name) + r"( \d+)?", name) is not None


def speakers_of(paragraphs: list[Segment]) -> dict[str, dict]:
    """speaker id → {"name", "track"} for paragraphs from speaker diarization, in order of appearance."""
    found: dict[str, dict] = {}
    for p in paragraphs:
        if p.speaker_id and p.speaker_id not in found:
            found[p.speaker_id] = {"name": p.speaker, "track": p.track}
    return found
