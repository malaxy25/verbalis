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
    script = STUBS + functions("speakerCountRow", "speakersPanel", "markDoubts", "splitButton", "speakerTracks", "trackGroup") + """
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
    script = STUBS + functions("speakerCountRow", "speakersPanel", "markDoubts", "splitButton", "speakerTracks", "trackGroup", "unnamedSpeaker",
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


def test_unclear_speaker_marks_shown_with_the_moment_to_listen_to():
    """0.7.43: «… klingen für Verbalis gleich» was a global notice without saying where – now the speaker box lists
    each unclear mark with ▶ for that moment (from 5 s before) and opens itself."""
    script = STUBS + functions("speakerCountRow", "speakersPanel", "markDoubts", "splitButton", "speakerTracks", "trackGroup",
                               "unnamedSpeaker", "generatedName") + """
const state = {};
function timeText(s) { return `t${Math.floor(s)}`; }
const played = [];
function call(name, ...args) { played.push([name, ...args]); return Promise.resolve({ url: "" }); }
function playAudio(key, fetch) { fetch(); }
const panel = speakersPanel({ id: "x", audio: true }, { tracks: { others: "Gegenüber" },
  segments: [{ track: "others", speaker_id: "others-1", start: 0, end: 5 }],
  speakers: { "others-1": { name: "maurice", track: "others" } },
  mark_doubts: [{ t: 4563.1, name: "lara", heard: "maurice" }] });
const box = panel.children[1].children[0];
const item = box.children[0].children[2].children[0];
item.children[1].attrs.onclick({ currentTarget: {} });
console.log(JSON.stringify([panel.open, box.attrs.class, text(item), played]));
"""
    opened, cls, item, played = run(script)
    assert opened is True and cls == "mark-doubts"
    assert item.startswith("Bei t4563 war «lara» markiert, Verbalis hört dort «maurice».")
    assert played == [["audio_clip", "x", 4558.1, 4573.1]]



def test_unclear_marks_offer_to_split_the_voice():
    """5 Nov 2026: «sascha» marked three times where Verbalis heard «Paul» – Sascha had no voice of her own and the
    hint said «Neu zuordnen», which only joins voices. Now a button splits that voice by the marks.
    5 Nov 2026, later: the button also showed for a mark only next to the voice (8:53) – no sample there, so
    «trennen» failed with «keine Marken». It shows only where the backend found samples (split_with)."""
    script = STUBS + functions("markDoubts", "splitButton") + """
const state = {};
function timeText(s) { return String(s); }
const asked = [];
function call(name, ...args) { asked.push([name, ...args]); return Promise.resolve(null); }
async function loadList() {}
function showMessage(m) { console.error(m); }
const doubts = [{ t: 270.1, name: "sascha", heard: "Paul" }, { t: 533.9, name: "sascha", heard: "Paul" }];
const box = markDoubts({ id: "x", audio: true }, { speakers: { "me-1": { name: "Paul", track: "me" } }, mark_doubts: doubts,
  split_with: { "me-1": ["sascha"] } })[0];
const near = markDoubts({ id: "x", audio: true }, { speakers: { "me-1": { name: "Paul", track: "me" } }, mark_doubts: doubts })[0];
const nearActions = near.children[0].children.filter((c) => c && c.attrs && c.attrs.class === "doubt-actions").length;
const buttons = box.children[0].children.find((c) => c && c.attrs && c.attrs.class === "doubt-actions").children;
buttons[0].attrs.onclick();
setTimeout(() => console.log(JSON.stringify([buttons.map((b) => b.textContent), asked, nearActions])), 10);
"""
    labels, asked, near_actions = run(script)
    assert labels == ["Wird getrennt …"] and asked == [["split_speaker", "x", "me-1"]]
    assert near_actions == 0


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
const state = {};
function timeText(s) { return String(s); }
const original = element;
element = (...args) => Object.assign(original(...args), { classList: { toggle() {} } });
const marks = Array.from({ length: 8 }, (_, i) => ({ t: i * 60, name: i % 2 ? "Basil" : "Sandra", track: "others" }));
const show = (box) => ({ title: text(box.children[0]),
  rows: box.children.filter((c) => c && c.attrs.class === "marks-row").map((r) => r.children.map(text)),
  recent: (box.children.find((c) => c && c.attrs.class === "marks-recent") || { children: [] }).children.map(text) });
const participants = { me: ["Andrea"], others: ["Basil", "Sandra", "Peter"] };
console.log(JSON.stringify([show(speakerMarks({ participants, speaker_marks: marks })),
                            show(speakerMarks({ participants, speaker_marks: [...marks, { t: 9, name: "peter", track: "others" }] }))]));
"""
    some, every = run(script)
    # marked people and a track's only participant (named automatically) get ✓
    # marked people get the number of their marks next to the name (0.7.45)
    assert some["rows"][:2] == [["Im Call", "✓ Basil4", "✓ Sandra4", "Peter"], ["Am Mikrofon", "✓ Andrea"]]
    assert some["rows"][2][-1] == "spricht jetzt" and some["title"] == "Wer spricht gerade?"
    assert some["recent"] == ["120 Sandra×", "180 Basil×", "240 Sandra×", "300 Basil×", "360 Sandra×", "420 Basil×"]
    assert every["title"] == "Wer spricht gerade? ✓ Alle markiert"



def test_all_marks_of_a_person_are_listed_with_what_was_said():
    """5 Nov 2026, 2:50 h meeting on site: only the latest 6 marks were shown – were the others still saved? Now the
    number of marks stands next to each name; a click on it lists all of them with the words said there and ×."""
    script = STUBS + functions("speakerMarks") + """
const MARKS_SHOWN = 6;
const state = {};
function timeText(s) { return String(s); }
function showMessage(m) { console.error(m); }
const original = element;
element = (...args) => Object.assign(original(...args), { classList: { toggle() {} }, isConnected: true });
const marks = Array.from({ length: 8 }, (_, i) => ({ t: i * 60, name: i % 2 ? "Basil" : "Sandra", track: "others" }));
const asked = [];
async function call(name, ...args) {
  asked.push([name, ...args]);
  if (name === "speaker_mark_texts") return { live: true, texts: marks.map((m, i) => i < 3 ? `Satz ${i}` : i === 3 ? "" : null) };
  if (name === "remove_speaker_mark") { marks.splice(args[0], 1); return [...marks]; }
}
const box = speakerMarks({ participants: { others: ["Basil", "Sandra"] }, speaker_marks: [...marks] });
const list = () => box.children.find((c) => c && c.attrs.class === "marks-list");
const basil = box.children.find((c) => c && c.attrs.class === "marks-row").children[1];
(async () => {
  basil.children[1].attrs.onclick();                      // the number next to «Basil»
  await new Promise((r) => setTimeout(r, 10));
  const items = list().children[1].children;
  const before = items.map(text);
  items[0].children[2].attrs.onclick();                   // × at the first mark of Basil
  await new Promise((r) => setTimeout(r, 10));
  const after = list().children[1].children.map(text);
  list().children[0].children[1].attrs.onclick();          // close
  console.log(JSON.stringify({ before, after, asked, closed: !list() }));
  process.exit(0);
})();
"""
    result = run(script)
    assert result["before"] == ["60«Satz 1»×", "180(nichts gesagt)×",
                                "300Text folgt, sobald dieser Teil transkribiert ist …×",
                                "420Text folgt, sobald dieser Teil transkribiert ist …×"]
    assert ["remove_speaker_mark", 1] in result["asked"]   # the index in all marks, not in Basil's list
    assert result["after"][0].startswith("180") and len(result["after"]) == 3 and result["closed"]


def test_speaker_marks_box_shows_yourself_at_the_microphone():
    """28 Oct 2026: Andrea marked himself during a call – not needed, the microphone is named after him anyway.
    With nobody listed at the microphone, his own name is shown there with ✓."""
    script = STUBS + functions("speakerMarks") + """
const MARKS_SHOWN = 6;
const state = {};
function timeText(s) { return String(s); }
const original = element;
element = (...args) => Object.assign(original(...args), { classList: { toggle() {} } });
state.settings = { name: "Andrea" };
const rows = (a) => speakerMarks(a).children.filter((c) => c && c.attrs.class === "marks-row")
  .map((r) => r.children.map(text));
console.log(JSON.stringify([rows({ participants: { others: ["Basil"] } }),
                            rows({ participants: { others: ["Basil"] }, only_microphone: true })]));
"""
    call, on_site = run(script)
    assert call[:2] == [["Im Call", "✓ Basil"], ["Am Mikrofon", "✓ Andrea"]]
    assert on_site[1][0] == ""                                  # only a microphone: nobody assumed there
