"""Generate the test catalogue in docs/TESTING.md from the tests themselves.

    python tools/test_catalog.py           # update docs/TESTING.md
    python tools/test_catalog.py --check   # exit 1 if it is out of date (used in CI)

Each test file becomes a section (its module docstring as introduction), each
test a line (its docstring's first line, or its name made readable). So the
catalogue can't drift from the code: CI fails until it is regenerated.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
DOC = ROOT / "docs" / "TESTING.md"
START, END = "<!-- catalog:start -->", "<!-- catalog:end -->"


def _readable(name: str) -> str:
    text = name.removeprefix("test_").replace("_", " ")
    return text[:1].upper() + text[1:]


def catalogue() -> str:
    sections, total = [], 0
    for path in sorted(TESTS.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        tests = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        if not tests:
            continue
        total += len(tests)
        intro = (ast.get_docstring(tree) or "").strip().splitlines()
        lines = [f"### `{path.name}` ({len(tests)})", ""]
        if intro:
            lines += [intro[0], ""]
        for t in tests:
            doc = (ast.get_docstring(t) or "").strip().splitlines()
            lines.append(f"- **{_readable(t.name)}**" + (f" – {doc[0]}" if doc else ""))
        sections.append("\n".join(lines))
    return f"{total} tests in {len(sections)} files.\n\n" + "\n\n".join(sections) + "\n"


def updated(text: str) -> str:
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    return f"{before}{START}\n{catalogue()}{END}{after}"


def main() -> int:
    current = DOC.read_text(encoding="utf-8")
    new = updated(current)
    if "--check" in sys.argv:
        if new != current:
            print("docs/TESTING.md is out of date – run: python tools/test_catalog.py")
            return 1
        print("docs/TESTING.md is up to date.")
        return 0
    DOC.write_text(new, encoding="utf-8")
    print(f"docs/TESTING.md updated ({catalogue().split(' ', 1)[0]} tests).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
