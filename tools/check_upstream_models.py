"""Compare the originals of our converted models with their latest version on Hugging Face.

Reads UPSTREAM_REVISIONS from src/verbalis/transcription/models.py (without
importing Verbalis) and asks the Hugging Face API for the latest revision of
each original. Prints a Markdown report and exits with 1 if anything changed –
used by .github/workflows/model-check.yml to open an issue.

    python tools/check_upstream_models.py
"""

from __future__ import annotations

import ast
import fnmatch
import json
import sys
import urllib.request
from pathlib import Path

MODELS_PY = Path(__file__).resolve().parents[1] / "src" / "verbalis" / "transcription" / "models.py"
API = "https://huggingface.co/api/models/"
DOCS = ("*.md", ".gitattributes", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg")  # changes here don't count


def pinned_revisions(path: Path = MODELS_PY) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "UPSTREAM_REVISIONS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("UPSTREAM_REVISIONS not found in models.py")


def fetch(repo: str, revision: str | None = None) -> dict:
    """Revision info with content ids of all files (Hugging Face API, no login needed)."""
    url = API + repo + (f"/revision/{revision}" if revision else "") + "?blobs=true"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    files = {s["rfilename"]: s.get("blobId") for s in data.get("siblings", [])
             if not any(fnmatch.fnmatch(s["rfilename"], d) for d in DOCS)}
    return {"revision": data["sha"], "changed": data.get("lastModified", "")[:10], "files": files}


def report(pinned: dict[str, str], fetch=fetch) -> list[str]:
    """One line per model whose files (not just its documentation) changed since our revision."""
    lines = []
    for repo, revision in pinned.items():
        now = fetch(repo)
        if now["revision"] == revision or now["files"] == fetch(repo, revision)["files"]:
            continue
        lines.append(f"- **{repo}**: ours from `{revision[:7]}`, latest `{now['revision'][:7]}` "
                     f"({now['changed']}) – https://huggingface.co/{repo}")
    return lines


def main() -> int:
    lines = report(pinned_revisions())
    if not lines:
        print("All converted models are up to date.")
        return 0
    print("\n".join(lines))
    return 1


if __name__ == "__main__":
    sys.exit(main())
