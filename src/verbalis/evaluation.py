"""Word error rate (WER) of a transcript against a reference.

WER = (substituted + missing + extra words) / words in the reference.

Caution with Swiss German: the models *translate* into Standard German. A
correct but differently worded translation («Karotten» instead of «Rüebli»)
counts as an error. WER is therefore mainly useful to compare models with each
other, not as an absolute grade.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


def normalize(text: str) -> list[str]:
    """Lower case, drop punctuation, join digit groups.

    "25'300" / "25.300" / "25 300" → "25300", "079 123 45 67" → "0791234567",
    so different number notations don't count as errors.
    """
    t = text.lower().replace("ß", "ss")
    t = re.sub(r"(?<=\d)[\s'’.,](?=\d)", "", t)
    t = re.sub(r"[^\w\s]|_", " ", t)
    return t.split()


@dataclass
class ErrorRate:
    wer: float
    substituted: int
    missing: int
    extra: int
    reference_words: int

    def __str__(self) -> str:  # user-facing (German)
        return (
            f"{self.wer:.1%} (ersetzt {self.substituted}, fehlend {self.missing}, "
            f"zusätzlich {self.extra} bei {self.reference_words} Wörtern)"
        )


def error_rate(reference: str, hypothesis: str) -> ErrorRate:
    ref, hyp = normalize(reference), normalize(hypothesis)
    n, m = len(ref), len(hyp)
    # d[i][j] = (cost, substituted, missing, extra) for ref[:i] vs. hyp[:j]
    d = [[(j, 0, 0, j) for j in range(m + 1)]]
    for i in range(1, n + 1):
        row = [(i, 0, i, 0)]
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                row.append(d[i - 1][j - 1])
                continue
            k, s, mi, e = d[i - 1][j - 1]
            substitute = (k + 1, s + 1, mi, e)
            k, s, mi, e = d[i - 1][j]
            delete = (k + 1, s, mi + 1, e)
            k, s, mi, e = row[j - 1]
            insert = (k + 1, s, mi, e + 1)
            row.append(min(substitute, delete, insert))
        d.append(row)
    cost, s, mi, e = d[n][m]
    return ErrorRate(wer=cost / max(n, 1), substituted=s, missing=mi, extra=e, reference_words=n)


@dataclass
class Reference:
    """What a transcription is compared against."""
    text: str                          # whole conversation
    tracks: dict[str, str] | None      # per track ("me", "others") – only from a transcript
    edited: bool | None                # was the reference transcript corrected? None for plain text
    source: str


def load_reference(value: str, folder: Path, until_s: float | None = None) -> Reference:
    """Reference for `verbalis compare`.

    - "transcript": the recording's own transcript.json – correct it in the app first
    - a .json file: a transcript of the same recording (e.g. a corrected copy)
    - any other file: plain text, e.g. testdata/reference_standard_german.txt

    For transcripts only paragraphs starting before `until_s` count, so a
    comparison of the first minutes isn't measured against the whole call.
    """
    path = folder / "transcript.json" if value == "transcript" else Path(value)
    if path.suffix.lower() != ".json":
        return Reference(path.read_text(encoding="utf-8"), None, None, str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = [s for s in data.get("segments", []) if not until_s or s["start"] < until_s]
    names = data.get("tracks") or {}
    def belongs(seg: dict, track: str, name: str) -> bool:
        # since 0.7.16 segments carry their track; older transcripts only the speaker name
        return seg.get("track") == track if seg.get("track") else seg.get("speaker") == name

    per_track = {track: " ".join(s["text"] for s in segments if belongs(s, track, name))
                 for track, name in names.items()}
    return Reference(" ".join(s["text"] for s in segments), per_track or None,
                     bool(data.get("edited")), str(path))
