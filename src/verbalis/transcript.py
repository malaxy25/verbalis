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
  answer – when nobody else is speaking – stays a normal paragraph. The setting
  «Kurze Einwürfe am Rand zeigen» switches this off (`merge(…, asides=False)`).
- Consecutive sentences of the same person become one paragraph.

Since 0.7.32 every paragraph keeps its word timestamps (`words`) in transcript.json, so a paragraph
split by hand gets the time of the first word of its second part (`split_times`).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from difflib import SequenceMatcher
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


def merge(tracks: dict[str, list[Segment]], asides: bool = True) -> list[Segment]:
    """tracks: display name → segments. Returns paragraphs and asides, sorted by start.

    asides=False: interjections are normal paragraphs where they were said.
    """
    # a speaker set by diarization stays; otherwise the track's display name
    units = [replace(s, speaker=s.speaker or name) for name, segments in tracks.items() for s in sentences(segments)]
    units.sort(key=lambda s: (s.start, s.end))
    if asides:
        units = mark_asides(units)

    result: list[Segment] = []
    last_index: int | None = None          # the last paragraph (asides don't count)
    for s in units:
        if s.aside:
            result.append(s)
            continue
        last = result[last_index] if last_index is not None else None
        if (last and last.speaker == s.speaker and last.speaker_id == s.speaker_id
                and s.start - last.end <= MAX_PAUSE_IN_PARAGRAPH_S):
            result[last_index] = replace(last, end=max(last.end, s.end), text=f"{last.text} {s.text}",
                                         words=joined_words(last.words, s.words))
        else:
            result.append(s)
            last_index = len(result) - 1
    return result


def joined_words(a: list | None, b: list | None) -> list | None:
    """The words of two joined paragraphs – None when one of them has none (then they would not match)."""
    return a + b if a and b else None


def clean_text(text: str) -> str:
    """A paragraph as typed: spaces collapsed, line breaks (Shift+Enter) kept, empty lines dropped."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _token(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def split_times(start: float, end: float, words: list | None, before: str, after: str):
    """Where a paragraph is split into `before` and `after`: (end of the first part, start of the second,
    words of the first, words of the second).

    The text may have been corrected, so it is compared with the transcribed words (like a text
    comparison); the second part starts at the word that matches its first word. Without words, or when
    nothing matches, the time is estimated from the length of the text.
    """
    if words:
        tokens = [_token(t) for t in before.split() + after.split()]
        cut_at = len(before.split())
        to_word: dict[int, int] = {}
        matcher = SequenceMatcher(None, [_token(str(w[2])) for w in words], tokens, autojunk=False)
        for a, b, size in matcher.get_matching_blocks():
            for i in range(size):
                to_word[b + i] = a + i
        earlier = [to_word[j] for j in range(cut_at) if j in to_word]
        later = [(j, to_word[j]) for j in range(cut_at, len(tokens)) if j in to_word]
        lowest = earlier[-1] + 1 if earlier else 0
        cut = max(lowest, later[0][1] - (later[0][0] - cut_at)) if later else lowest
        if 0 < cut < len(words):
            return float(words[cut - 1][1]), float(words[cut][0]), words[:cut], words[cut:]
    share = len(before) / max(len(before) + len(after), 1)
    middle = round(start + (end - start) * share, 2)
    return middle, middle, None, None


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
            lines.append(f"**[{_time(p.start)}] {p.speaker}:** " + p.text.replace("\n", "  \n"))   # line break
        lines.append("")
    return "\n".join(lines)


def segment_dict(p: Segment) -> dict:
    """A paragraph as stored in transcript.json – `words` and `aside` only when set."""
    data = asdict(p)
    if not data.get("words"):
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


def complete_speakers(data: dict, participants: dict[str, list[str]] | None = None) -> bool:
    """Every track gets a speaker the speaker box can name (0.7.39). Returns whether `data` changed.

    Without diarization (switched off, «1 Person») a track's paragraphs had no speaker id: the speaker box could
    only offer «Anzahl Personen», so «Gegenüber» could not be renamed. Such a track now gets one speaker «<track>-1».
    The only speaker of a track with only one participant entered for it gets that participant's name – as long as
    the speaker still has the name Verbalis gave, so a name typed in the speaker box stays."""
    segments = data.get("segments") or []
    speakers = data.setdefault("speakers", {})
    tracks = data.get("tracks") or {}
    changed = False
    for track in dict.fromkeys(s.get("track") for s in segments):
        own = [s for s in segments if s.get("track") == track]
        if not track or any(s.get("speaker_id") for s in own):
            continue
        sid = f"{track}-1"
        speakers[sid] = {"name": own[0].get("speaker") or tracks.get(track) or "", "track": track}
        for s in own:
            s["speaker_id"], s["speaker"] = sid, speakers[sid]["name"]
        changed = True
    for track, names in (participants or {}).items():
        on_track = [sid for sid, info in speakers.items() if info.get("track") == track
                    and any(s.get("speaker_id") == sid for s in segments)]
        if len(names) != 1 or len(on_track) != 1:
            continue
        sid = on_track[0]
        if speakers[sid]["name"] == names[0] or not is_default_name(speakers[sid]["name"], tracks.get(track, "")):
            continue
        speakers[sid]["name"] = names[0]
        for s in segments:
            if s.get("speaker_id") == sid:
                s["speaker"] = names[0]
        changed = True
    return changed


def speakers_of(paragraphs: list[Segment]) -> dict[str, dict]:
    """speaker id → {"name", "track"} for paragraphs from speaker diarization, in order of appearance."""
    found: dict[str, dict] = {}
    for p in paragraphs:
        if p.speaker_id and p.speaker_id not in found:
            found[p.speaker_id] = {"name": p.speaker, "track": p.track}
    return found
