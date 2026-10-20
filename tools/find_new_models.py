"""Look for new Swiss German speech recognition models on Hugging Face.

Searches the Hugging Face API (no login needed) with a few Swiss German search terms and
the publishers of Swiss German speech data, keeps the speech recognition models and lists
those not yet in tools/known-models.txt. Prints a Markdown report and exits with 1 if there
are new ones – used by .github/workflows/model-check.yml to open an issue.

After looking at a reported model (and measuring it with `verbalis compare` if it is
promising), add it to tools/known-models.txt so it is not reported again.

    python tools/find_new_models.py            # report
    python tools/find_new_models.py --add-all  # mark everything found as known
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

KNOWN = Path(__file__).resolve().parent / "known-models.txt"
API = "https://huggingface.co/api/models?"
SEARCHES = ["swiss-german", "swiss german", "swissgerman", "swiss_german", "schweizerdeutsch", "stt4sg"]
FILTERS = ["gsw"]                     # the language tag for Swiss German
AUTHORS = ["i4ds"]                    # FHNW – Swiss Parliaments Corpus, STT4SG (gcoli is trained on their data)
ASR = "automatic-speech-recognition"


def fetch(params: dict) -> list[dict]:
    url = API + urllib.parse.urlencode({**params, "limit": 200})
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def candidates(fetch=fetch) -> dict[str, dict]:
    """Repo id → model info of every speech recognition model found."""
    found: dict[str, dict] = {}
    queries = ([{"search": s} for s in SEARCHES] + [{"filter": f} for f in FILTERS]
               + [{"author": a} for a in AUTHORS])
    for query in queries:
        for model in fetch(query):
            tags = model.get("tags") or []
            if model.get("pipeline_tag") == ASR or ASR in tags or "whisper" in tags:
                found[model["id"]] = model
    return found


def known(path: Path = KNOWN) -> set[str]:
    if not path.exists():
        return set()
    return {line.split("#")[0].strip() for line in path.read_text(encoding="utf-8").splitlines()} - {""}


def line(model: dict) -> str:
    tags = model.get("tags") or []
    licence = next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), "?")
    base = next((t.split(":", 1)[1] for t in tags if t.startswith("base_model:") and t.count(":") == 1), "")
    return (f"- **{model['id']}** – created {model.get('createdAt', '')[:10]}, {model.get('downloads', 0)} downloads, "
            f"licence {licence}" + (f", based on {base}" if base else "") + f" – https://huggingface.co/{model['id']}")


def report(found: dict[str, dict], seen: set[str]) -> list[str]:
    """New models, most downloaded first."""
    new = [m for repo, m in found.items() if repo not in seen]
    return [line(m) for m in sorted(new, key=lambda m: -(m.get("downloads") or 0))]


def main(argv: list[str]) -> int:
    found = candidates()
    if "--add-all" in argv:
        missing = sorted(set(found) - known())
        with KNOWN.open("a", encoding="utf-8") as f:
            f.writelines(f"{repo}\n" for repo in missing)
        print(f"{len(missing)} models added to {KNOWN.name}.")
        return 0
    lines = report(found, known())
    if not lines:
        print("No new Swiss German speech recognition models.")
        return 0
    print("\n".join(lines))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
