"""The introduction in the UI: its last step. Runs the tour functions of index.html in Node.js."""

import json
import shutil
import subprocess

import pytest

from test_ui_list import functions

NODE = shutil.which("node")

STUBS = """
function element(tag, attrs, ...children) { return { tag, attrs: attrs || {}, children, disabled: false }; }
function text(node) { return typeof node === "string" ? node : (node.children || []).filter(Boolean).map(text).join(""); }
function find(node, tag) {
  if (!node || typeof node === "string") return null;
  if (node.tag === tag) return node;
  for (const child of node.children || []) { const hit = find(child, tag); if (hit) return hit; }
  return null;
}
const deleted = [];
async function call(name, id) { if (name === "delete_recording") { deleted.push(id); if (deleted.length > 1) throw new Error("Die Aufnahme gibt es nicht mehr."); } }
const state = { selected: "probe", listSignature: "x" };
const tour = { recordingId: "probe", deleted: false, deleting: false, deleteError: "" };
let rendered = 0;
function renderTour() { rendered++; }
async function loadList() {}
async function renderContent() {}
"""

SCRIPT = """
(async () => {
  const before = find(tourDeleteLine(), "button");
  const first = deleteTourRecording(), second = deleteTourRecording();   // a double click
  await first; await second;
  const after = tourDeleteLine();
  await deleteTourRecording();                                          // a later click
  console.log(JSON.stringify({ before: text(before), deleted, button: find(after, "button") ? text(find(after, "button")) : null,
                               line: text(after), error: tour.deleteError, id: tour.recordingId, selected: state.selected }));
})();
"""


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_test_recording_is_deleted_once_and_the_step_stays():
    """0.7.30 draft: after «Probeaufnahme löschen» the button stayed (the step count shrank and the card was
    no longer redrawn) – a second click showed «gibt es nicht mehr» behind the introduction."""
    code = STUBS + functions("tourCheck", "tourDeleteLine", "deleteTourRecording") + SCRIPT
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    result = json.loads(out)
    assert result["before"] == "Probeaufnahme löschen"
    assert result["deleted"] == ["probe"]                    # deleted once, double click included
    assert result["button"] is None and "gelöscht" in result["line"]
    assert result["error"] == "" and result["id"] == "probe" and result["selected"] is None
