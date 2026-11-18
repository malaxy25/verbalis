"""Folding the recording list to a narrow rail (Ctrl/Cmd+B). Runs setSidebar of index.html in Node.js."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from verbalis.settings import Settings

INDEX = Path(__file__).parents[1] / "src" / "verbalis" / "ui" / "index.html"
NODE = shutil.which("node")


def function(name):
    source = INDEX.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(rf"^function {name}\(.*?^}}\n", source, re.S | re.M)
    assert match, name
    return match.group(0)


STUBS = """
const classes = new Set();
const document = { body: { classList: { toggle(c, on) { on ? classes.add(c) : classes.delete(c); } } } };
const toggle = { attrs: {}, title: "", setAttribute(k, v) { this.attrs[k] = v; } };
const $ = () => toggle;
const SHORTCUT = "Ctrl+B";
const saved = [];
function call(name, data) { saved.push(data); return Promise.resolve({ ...state.settings, ...data }); }
const state = { settings: { sidebar: "open" } };
"""

SCRIPT = """
const steps = [];
const snap = () => steps.push([classes.has("sidebar-collapsed"), toggle.attrs["aria-expanded"], toggle.title, saved.length]);
setSidebar(true); snap();
setSidebar(true); snap();          // already closed: not saved again
setSidebar(false, false); snap();  // opened for the search in all recordings: not remembered
console.log(JSON.stringify(steps));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_list_folds_and_remembers_only_on_purpose():
    code = STUBS + function("setSidebar") + SCRIPT
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    steps = json.loads(out)
    assert steps[0] == [True, "false", "Liste aufklappen (Ctrl+B)", 1]
    assert steps[1][3] == 1
    assert steps[2] == [False, "true", "Liste zuklappen (Ctrl+B)", 1]


def test_sidebar_setting_is_open_or_closed():
    assert Settings().sidebar == "open"
    assert Settings.from_dict({"sidebar": "closed"}).sidebar == "closed"
    assert Settings.from_dict({"sidebar": "weg"}).sidebar == "open"
