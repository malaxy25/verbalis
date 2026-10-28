"""The speaker box in the UI. Runs functions of index.html in Node.js."""

import json
import subprocess

import pytest

from test_ui_list import NODE, functions

pytestmark = pytest.mark.skipif(NODE is None, reason="needs Node.js")

STUBS = """
function element(tag, attrs, ...children) {
  return { tag, attrs: attrs || {}, children, addEventListener() {}, replaceChildren(...c) { this.children = c; } };
}
function text(node) {
  if (typeof node === "string") return node;
  return node.textContent !== undefined ? node.textContent : (node.children || []).filter(Boolean).map(text).join("");
}
const TRACK_LABELS = { me: "Mikrofon", others: "Systemton" };
"""


def run(script):
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def test_speaker_count_names_the_track():
    """0.7.32: «Anzahl Personen auf dieser Spur ()» – the label used a variable that no longer existed."""
    script = STUBS + functions("speakerCountRow") + """
const t = { speakers: { "others-1": { name: "Gegenüber 1", track: "others" } } };
const row = speakerCountRow({ id: "x", audio: true }, t, { "others-1": 12 }, "others");
console.log(JSON.stringify(row.children[0].children[1].attrs["aria-label"]));
"""
    assert run(script) == "Anzahl Personen im Systemton"


def test_number_of_people_offered_without_speakers():
    """Ubuntu, 0.7.36: the test recording of the introduction is transcribed with «1 Person» per track, so no
    speakers were told apart – and without speakers the box with «Anzahl Personen» didn't appear at all."""
    script = STUBS + functions("speakerCountRow", "speakersPanel", "speakerTracks", "trackGroup") + """
const t = { speakers: {}, segments: [{ track: "others", start: 0, end: 3 }, { track: "me", start: 4, end: 6 }] };
const panel = speakersPanel({ id: "x", audio: true }, t);
const groups = panel.children.slice(2);
console.log(JSON.stringify([text(panel.children[1]), groups.map((g) => [text(g.children[0]), text(g.children[2].children[0])])]));
"""
    hint, groups = run(script)
    assert "nicht unterschieden" in hint
    assert [[label, count.strip()] for label, count in groups] == [["Mikrofon", "Personen"], ["Systemton", "Personen"]]


def test_speaker_box_closed_once_everybody_has_a_name():
    """0.7.40: the speaker box took much room above the transcript. It is closed (one line with the names) once every
    speaker has a name, open while one is still «Gegenüber 2» or «Person 1»; the number of people is next to the
    speakers of its track."""
    script = STUBS + functions("speakerCountRow", "speakersPanel", "speakerTracks", "trackGroup", "unnamedSpeaker",
                               "generatedName") + """
const state = {};
function timeText(s) { return String(s); }
const tracks = { me: "Andrea", others: "Gegenüber" };
const segments = [{ track: "me", speaker_id: "me-1", start: 0, end: 5 }, { track: "others", speaker_id: "others-1", start: 5, end: 8 },
                  { track: "others", speaker_id: "others-2", start: 8, end: 9 }];
const named = speakersPanel({ id: "x", audio: true }, { tracks, segments, speakers: {
  "me-1": { name: "Andrea", track: "me" }, "others-1": { name: "Claudia Gibolli", track: "others" },
  "others-2": { name: "Marc Muster", track: "others" } } });
const open = speakersPanel({ id: "y", audio: true }, { tracks, segments, speakers: {
  "me-1": { name: "Andrea", track: "me" }, "others-1": { name: "Claudia Gibolli", track: "others" },
  "others-2": { name: "Gegenüber 2", track: "others" } } });
const others = named.children[1].children[1];
console.log(JSON.stringify([named.tag, named.open, text(named.children[0].children[1]), open.open,
  text(others.children[0]), others.children[1].children.length, text(others.children[2].children[0])]));
"""
    tag, named_open, names, still_open, label, rows, count = run(script)
    assert tag == "details" and named_open is False and names == "Andrea, Claudia Gibolli, Marc Muster"
    assert still_open is True
    assert (label, rows, count.strip()) == ("Systemton", 2, "Personen")


def test_generated_names_are_recognised():
    """A name Verbalis gave is cleared on focus so the field lists all participants; a typed name is kept."""
    script = functions("generatedName") + """
console.log(JSON.stringify([generatedName("Gegenüber 2", "Gegenüber"), generatedName("Person 3", "Andrea"),
  generatedName("Gegenüber", "Gegenüber"), generatedName("Monika Zunker", "Gegenüber"),
  generatedName("Ich (Test) 2", "Ich (Test)")]));
"""
    assert run(script) == [True, True, True, False, True]


def test_speaker_marks_box_offers_the_participants_and_the_latest_marks():
    """0.7.41: «Wer spricht gerade?» while recording – a button per participant, grouped by track, the latest marks."""
    script = STUBS + functions("speakerMarks") + """
const MARKS_SHOWN = 6;
function timeText(s) { return String(s); }
const marks = Array.from({ length: 8 }, (_, i) => ({ t: i * 60, name: i % 2 ? "Basil" : "Sandra", track: "others" }));
const box = speakerMarks({ participants: { me: ["Andrea"], others: ["Basil", "Sandra"] }, speaker_marks: marks });
const rows = box.children.filter((c) => c && c.attrs.class === "marks-row");
const recent = box.children.find((c) => c && c.attrs.class === "marks-recent");
console.log(JSON.stringify({ rows: rows.map((r) => r.children.map(text)), recent: recent.children.map(text) }));
"""
    result = run(script)
    assert result["rows"][:2] == [["Im Call", "Basil", "Sandra"], ["Am Mikrofon", "Andrea"]]
    assert result["rows"][2][-1] == "spricht jetzt"
    assert result["recent"] == ["120 Sandra×", "180 Basil×", "240 Sandra×", "300 Basil×", "360 Sandra×", "420 Basil×"]
