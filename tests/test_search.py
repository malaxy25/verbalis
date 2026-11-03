"""Search in transcripts: the rules (verbalis/search.py, the same in index.html) and «Alle Aufnahmen»."""

import json
import shutil
import subprocess
import time

import pytest

from verbalis import pipeline, search
from test_service import finished_recording, make_service
from test_ui_list import functions

NODE = shutil.which("node")

TEXT = "Wir besprechen das nächste Release mit Müller. Danach: Rückblick und nochmals das Release."
CASES = [   # query, expected hits in TEXT
    ("release", ["Release", "Release"]),
    ("naechste", ["nächste"]),                # «ä» = «ae»
    ("NÄCHSTE", ["nächste"]),
    ("mueller release", ["Release", "Müller", "Release"]),   # several words: all of them, any order
    ("rueckblick", ["Rückblick"]),
    ("release budget", []),                   # one word missing: no hit at all
    ("   ", []),
]


@pytest.mark.parametrize("query, expected", CASES)
def test_search_rules(query, expected):
    hits = search.spans(TEXT, search.terms(query))
    assert [TEXT[a:b] for a, b in hits] == expected


def test_accents_and_sharp_s():
    assert search.spans("Café Strasse", search.terms("cafe straße")) == [(0, 4), (5, 12)]


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_window_uses_the_same_rules_as_python():
    """The open transcript is searched in the window: it must find exactly what «Alle Aufnahmen» finds."""
    code = functions("foldText", "searchTerms", "matchSpans") + f"""
const SEARCH_FOLD = {json.dumps(search.FOLD, ensure_ascii=False)};
const text = {json.dumps(TEXT, ensure_ascii=False)};
const queries = {json.dumps([q for q, _ in CASES] + ["cafe straße"], ensure_ascii=False)};
console.log(JSON.stringify(queries.map((q) => matchSpans(q === "cafe straße" ? "Café Strasse" : text, searchTerms(q)))));
"""
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    expected = [[list(h) for h in search.spans(TEXT, search.terms(q))] for q, _ in CASES]
    expected.append([list(h) for h in search.spans("Café Strasse", search.terms("cafe straße"))])
    assert json.loads(out) == expected


def test_snippet_is_cut_around_the_first_hit():
    text = "Am Anfang reden wir lange über das Wetter und das Wochenende. " * 3 + "Dann kommt das Budget. " + "Und so weiter. " * 10
    hits = search.spans(text, ["budget"])
    snip = search.snippet(text, hits)
    assert snip.startswith("… ") and snip.endswith(" …") and "Budget" in snip
    assert len(snip) <= search.SNIPPET_LENGTH + 4
    assert search.snippet("Kurz und Budget.", search.spans("Kurz und Budget.", ["budget"])) == "Kurz und Budget."


def write_segments(s, rid, texts):
    path = s._path(rid) / "transcript.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["segments"] = [{"start": 10.0 * i, "end": 10.0 * i + 5, "text": t, "speaker": "Andrea"} for i, t in enumerate(texts)]
    pipeline.write_json_atomic(path, data)


def test_search_across_recordings_newest_first():
    s = make_service()
    old = finished_recording(s)
    write_segments(s, old, ["Das Budget ist knapp.", "Nichts.", "Budget nochmals, das Budget."])
    time.sleep(1.1)   # the recording id is the start time in seconds
    new = finished_recording(s)
    write_segments(s, new, ["Budget für Q4."])
    s.update_details(new, {"title": "Planung", "project": "tocco", "participants": {"others": "Eva Müller"}})

    results = s.search("budget")
    assert [r["id"] for r in results] == [new, old]
    found = results[1]
    assert found["places"] == 2 and found["hits"] == 3
    assert [(sn["index"], sn["start"], sn["speaker"]) for sn in found["snippets"]] == [(0, 0.0, "Andrea"), (2, 20.0, "Andrea")]

    by_details = s.search("mueller tocco")      # participants and project, no paragraph
    assert [(r["id"], r["places"], r["in_details"]) for r in by_details] == [(new, 0, True)]
    assert s.search("") == [] and s.search("gibtsnicht") == []


def test_search_sees_edits_and_skips_broken_transcripts():
    s = make_service()
    rid = finished_recording(s)
    assert s.search("budget") == []
    write_segments(s, rid, ["Jetzt mit Budget."])     # transcript.json changed: the cache is refreshed
    assert len(s.search("budget")) == 1
    (s._path(rid) / "transcript.json").write_text("{kaputt", encoding="utf-8")
    assert s.search("budget") == []


def test_search_shows_at_most_three_snippets():
    s = make_service()
    rid = finished_recording(s)
    write_segments(s, rid, [f"Budget {i}" for i in range(5)])
    [result] = s.search("budget")
    assert result["places"] == 5 and len(result["snippets"]) == search.MAX_SNIPPETS
