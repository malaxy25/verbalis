"""The speaker box in the UI. Runs functions of index.html in Node.js."""

import json
import subprocess

import pytest

from test_ui_list import NODE, functions

pytestmark = pytest.mark.skipif(NODE is None, reason="needs Node.js")

STUBS = """
function element(tag, attrs, ...children) {
  return { tag, attrs: attrs || {}, children, addEventListener() {} };
}
function text(node) { return typeof node === "string" ? node : (node.children || []).filter(Boolean).map(text).join(""); }
const TRACK_LABELS = { me: "Mikrofon", others: "Systemton" };
"""


def run(script):
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def test_speaker_count_names_the_track():
    """0.7.32: «Anzahl Personen auf dieser Spur ()» – the label used a variable that no longer existed."""
    script = STUBS + functions("speakerCountRows") + """
const t = { speakers: { "others-1": { name: "Gegenüber 1", track: "others" } } };
const rows = speakerCountRows({ id: "x", audio: true }, t, { "others-1": 12 });
console.log(JSON.stringify(text(rows[0].children[0])));
"""
    assert run(script).startswith("Anzahl Personen auf dieser Spur (Systemton)")


def test_generated_names_are_recognised():
    """A name Verbalis gave is cleared on focus so the field lists all participants; a typed name is kept."""
    script = functions("generatedName") + """
console.log(JSON.stringify([generatedName("Gegenüber 2", "Gegenüber"), generatedName("Person 3", "Andrea"),
  generatedName("Gegenüber", "Gegenüber"), generatedName("Monika Zunker", "Gegenüber"),
  generatedName("Ich (Test) 2", "Ich (Test)")]));
"""
    assert run(script) == [True, True, True, False, True]
