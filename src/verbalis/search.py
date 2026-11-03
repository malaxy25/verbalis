"""Search in transcripts. The window searches the open transcript itself (same rules in index.html,
`foldText`/`matchSpans`); here the search across all recordings."""

import unicodedata

SNIPPET_BEFORE = 25    # characters shown before the first hit of a paragraph
SNIPPET_LENGTH = 90    # characters shown in total
MAX_SNIPPETS = 3       # paragraphs shown per recording

# Swiss German is written in many ways: «ä» and «ae» count as the same, as do «ö/oe», «ü/ue», «ß/ss».
FOLD = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def fold(text: str) -> tuple[str, list[int]]:
    """Lower case, umlauts as two letters, other accents dropped. Returns the folded text and, for every
    folded character, its position in `text` (to mark hits in the original)."""
    folded, positions = [], []
    for i, ch in enumerate(text):
        lower = ch.lower()
        rep = FOLD.get(lower)
        if rep is None:
            rep = "".join(c for c in unicodedata.normalize("NFD", lower) if not unicodedata.combining(c))
        folded.append(rep)
        positions.extend([i] * len(rep))
    return "".join(folded), positions


def terms(query: str) -> list[str]:
    """The words searched for: all of them must be in the same paragraph, in any order."""
    return list(dict.fromkeys(fold(query or "")[0].split()))


def spans(text: str, words: list[str]) -> list[tuple[int, int]]:
    """(start, end) of every hit in `text`, sorted – empty unless every word is in it."""
    if not words:
        return []
    folded, positions = fold(text)
    found = []
    for word in words:
        start = folded.find(word)
        if start < 0:
            return []
        while start >= 0:
            found.append((positions[start], positions[start + len(word) - 1] + 1))
            start = folded.find(word, start + len(word))
    return sorted(found)


def snippet(text: str, hits: list[tuple[int, int]]) -> str:
    """A short piece of the paragraph around its first hit, cut at word boundaries."""
    text = " ".join(text.split())
    if len(text) <= SNIPPET_LENGTH:
        return text
    start = max(0, hits[0][0] - SNIPPET_BEFORE) if hits else 0
    if start > 0:
        space = text.find(" ", start)
        start = space + 1 if 0 <= space < hits[0][0] else start
    end = min(len(text), start + SNIPPET_LENGTH)
    if end < len(text):
        space = text.rfind(" ", start, end)
        end = space if space > start + SNIPPET_LENGTH // 2 else end
    return ("… " if start > 0 else "") + text[start:end] + (" …" if end < len(text) else "")


def details_text(meta: dict, title: str) -> str:
    """Title, project and participants – a recording is found by these too."""
    people = meta.get("participants") or {}
    names = [n for track in people.values() for n in (track if isinstance(track, list) else [track])]
    return " ".join([title, meta.get("project") or "", *map(str, names)])


def find(segments: list[dict], words: list[str]) -> list[dict]:
    """The paragraphs with every word: index (as in transcript.json), time, speaker, snippet."""
    found = []
    for index, seg in enumerate(segments):
        hits = spans(seg.get("text") or "", words)
        if hits:
            found.append({"index": index, "start": seg.get("start", 0), "speaker": seg.get("speaker") or "",
                          "hits": len(hits), "text": snippet(seg["text"], hits)})
    return found
