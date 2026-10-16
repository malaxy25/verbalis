"""The recording list in the UI: groups open and close. Runs the list functions of index.html in Node.js."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = Path(__file__).parents[1] / "src" / "verbalis" / "ui" / "index.html"
NODE = shutil.which("node")


def functions(*names):
    source = INDEX.read_text(encoding="utf-8").replace("\r\n", "\n")
    found = []
    for name in names:
        match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", source, re.S | re.M)
        assert match, name
        found.append(match.group(0))
    return "\n".join(found)


STUBS = """
const list = { items: [], replaceChildren() { this.items = []; }, append(x) { this.items.push(x); } };
const $ = () => list;
function element(tag, attrs, ...children) { return { tag, attrs: attrs || {}, children }; }
function text(node) { return typeof node === "string" ? node : (node.children || []).filter(Boolean).map(text).join(""); }
const localStorage = { getItem() { throw new Error("not kept"); }, setItem() { throw new Error("not kept"); } };
const STATUS_TEXT = {}, STATE_SHORT = {}, STATE_TEXT = {};
function startDate(a) { return new Date(a.start); }
function shortDate(a) { return a.start; }
function timeText(s) { return String(s); }
function renderContent() {}
"""

SCRIPT = """
const now = new Date();
const today = new Date(now); today.setHours(9, 0, 0, 0);
const earlier = new Date(today); earlier.setDate(today.getDate() - ((today.getDay() + 6) % 7 === 0 ? 0 : 1));
const state = { recordings: [
  { id: "a", start: today.toISOString(), status: "done" },
  { id: "b", start: earlier.toISOString(), status: "done" },
], selected: "a" };
function heads() {
  return list.items.filter((li) => li.attrs.class === "group").map((li) => {
    const button = li.children[0];
    return [text(button).trim().replace(/\\d+$/, ""), button.attrs["aria-expanded"]];
  });
}
function click(label) {
  const li = list.items.find((x) => x.attrs.class === "group" && text(x.children[0]).includes(label));
  li.children[0].attrs.onclick();
}
const steps = [];
renderList(); steps.push(heads());
click("Diese Woche"); steps.push(heads());
click("Diese Woche"); steps.push(heads());
click("Heute"); steps.push(heads());
console.log(JSON.stringify({ steps, monday: (today.getDay() + 6) % 7 === 0 }));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_list_groups_open_and_close_again():
    """0.7.27: «Diese Woche» could be closed but not opened again (only a click on «Heute» did it),
    and «Heute» could not be closed while its recording was selected."""
    code = STUBS + functions("groupOf", "collapsedGroups", "toggleGroup", "renderList") + SCRIPT
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    result = json.loads(out)
    if result["monday"]:
        pytest.skip("on a Monday both recordings are «Heute»")
    steps = [[(label.strip("▸▾ "), open_) for label, open_ in step] for step in result["steps"]]
    assert steps[0] == [("Heute", "true"), ("Diese Woche", "true")]
    assert steps[1] == [("Heute", "true"), ("Diese Woche", "false")]   # closed
    assert steps[2] == [("Heute", "true"), ("Diese Woche", "true")]    # open again
    assert steps[3] == [("Heute", "false"), ("Diese Woche", "true")]   # the selected recording's group closes too
