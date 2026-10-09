"""Open the user interface in a normal browser, with a fake backend.

    python tools/ui_preview.py
    # then open tools/ui-preview/preview.html, e.g. preview.html#recording

The real app connects the HTML to Python through pywebview. Here
tools/ui-preview/mock.js stands in for that: it answers every API call with
sample data, so the UI can be checked and clicked through without recording or
transcribing. Scenarios (after #): transcript, recording, paused, news, notice,
empty, dev. Keep mock.js in step when the API changes.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src" / "verbalis" / "ui" / "index.html"
FOLDER = ROOT / "tools" / "ui-preview"


def main() -> None:
    mock = (FOLDER / "mock.js").read_text(encoding="utf-8")
    html = UI.read_text(encoding="utf-8")
    inject = "<script>window.__scenario = location.hash.slice(1) || 'transcript';\n" + mock + "</script>"
    out = FOLDER / "preview.html"
    out.write_text(html.replace("<head>", "<head>" + inject, 1), encoding="utf-8")
    print(f"Written: {out}")


if __name__ == "__main__":
    main()
