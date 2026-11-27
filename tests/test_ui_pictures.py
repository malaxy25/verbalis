"""The panel «Bilder» in the UI: choosing pictures. Runs picturesPanel of index.html in Node.js."""

import json
import re
import subprocess

import pytest

from test_ui_list import INDEX, NODE, functions

pytestmark = pytest.mark.skipif(NODE is None, reason="needs Node.js")


def constant(name):
    source = INDEX.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(rf"^const {name} = .*?^\];\n", source, re.S | re.M)
    assert match, name
    return match.group(0)


STUBS = """
function element(tag, attrs, ...children) {
  const node = { tag, attrs: attrs || {}, children, listeners: {}, scrollTop: 0,
    addEventListener(kind, f) { (this.listeners[kind] ||= []).push(f); },
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k]; },
    replaceChildren(...c) { this.children = c; },
    scrollTo() { this.scrollTop = 0; },
    querySelector(selector) { return find(this, selector.slice(1)); } };
  return node;
}
function find(node, cls) {
  for (const c of node.children || []) {
    if (!c || typeof c !== "object") continue;
    if (String(c.attrs.class || "").split(" ").includes(cls)) return c;
    const deeper = find(c, cls);
    if (deeper) return deeper;
  }
  return null;
}
function fire(node, kind, event = {}) { for (const f of node.listeners[kind] || []) f({ preventDefault() {}, ...event }); }
function lazyImage() { return element("img", {}); }
function timeText(s) { return String(s); }
function showMessage(m) { console.error(m); }
const state = {};
"""


def test_clicking_a_picture_keeps_the_scroll_position_and_shift_chooses_a_range():
    """27 Nov 2026: with many pictures, every click on one jumped the list back to the first picture (the whole grid was
    built anew). Now a click only marks the tile. Shift+click chooses every picture from the last clicked one – and
    un-chooses them if that one was just un-chosen."""
    script = STUBS + constant("PICTURE_FILTERS") + functions("pictureState", "picturesPanel") + """
const t = { pictures: Array.from({ length: 8 }, (_, i) => ({ t: i * 10, source: `s${i}.png`, used: i % 2 === 0, reason: i % 2 ? "short" : "" })) };
const panel = picturesPanel({ id: "x" }, t, {});
const body = panel.children[1];
const grid = body.querySelector(".pictures-grid");
grid.scrollTop = 300;
const tiles = grid.children;
const pressed = () => tiles.map((tile) => tile.attrs["aria-pressed"] === "true" ? 1 : 0).join("");
fire(tiles[1], "click");
fire(tiles[5], "click", { shiftKey: true });
const range = pressed();
const count = body.querySelector(".pictures-actions").children[0].children[0];
fire(tiles[3], "click");                            // off – the new start of a range
fire(tiles[4], "keydown", { key: " ", shiftKey: true });
console.log(JSON.stringify([body.querySelector(".pictures-grid") === grid, grid.scrollTop, range, count, pressed()]));
"""
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    same_grid, scrolled, range_, count, after = json.loads(out)
    assert same_grid and scrolled == 300
    assert range_ == "01111100" and count == "5 Bilder gewählt"
    assert after == "01100100"
