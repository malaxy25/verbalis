"""Release build: write packaging/feedback.json from the GitHub secrets (see src/verbalis/feedback.py).

Without the secrets nothing is written – the app then offers only the e-mail way.
"""

import json
import os
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[2] / "packaging" / "feedback.json"


def main() -> int:
    url = os.environ.get("VERBALIS_FEEDBACK_URL", "").strip()
    token = os.environ.get("VERBALIS_FEEDBACK_TOKEN", "").strip()
    if not url:
        print("No VERBALIS_FEEDBACK_URL – «Problem melden» will offer e-mail only")
        TARGET.unlink(missing_ok=True)
        return 0
    if not url.startswith("https://script.google.com/"):
        print("VERBALIS_FEEDBACK_URL must be an Apps Script web app (https://script.google.com/…)")
        return 1
    TARGET.write_text(json.dumps({"url": url, "token": token}), encoding="utf-8")
    print(f"Wrote {TARGET.name} (token {'set' if token else 'missing'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
