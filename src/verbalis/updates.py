"""Updates: check GitHub for a newer release, download the installer, show what's new.

- `check()` asks the GitHub API for the latest release (one small request, only
  when enabled in the settings). Nothing about the user is sent.
- `download_installer()` fetches Verbalis-X.Y.Z-setup.exe; the app then starts it
  and closes, the installer replaces the program files and keeps ~/.verbalis.
- `changes_between()` reads CHANGELOG.md (bundled with the app) and returns the
  sections newer than the version the user had before – shown once after an update.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Callable

from . import __version__

REPO = "malaxy25/verbalis"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
SECTION = re.compile(r"^## (\d+(?:\.\d+)*)\b(.*)$")


def parse_version(text: str) -> tuple[int, ...]:
    """'v0.7.4' / '0.7.4' → (0, 7, 4); anything unparsable → ()."""
    m = re.match(r"^v?(\d+(?:\.\d+)*)", (text or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return bool(a) and bool(b) and a > b


def is_installed() -> bool:
    """Running from the installer (bundled with PyInstaller) rather than from a git checkout?"""
    return bool(getattr(sys, "frozen", False))


# ---------------------------------------------------------------- check

def check(timeout: float = 8.0, opener: Callable = urllib.request.urlopen) -> dict:
    """Latest release on GitHub. Raises on network errors (the caller logs and ignores them)."""
    request = urllib.request.Request(LATEST_API, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"Verbalis/{__version__}"})
    with opener(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    version = ".".join(map(str, parse_version(data.get("tag_name", ""))))
    installer = next((a for a in data.get("assets", [])
                      if a.get("name", "").lower().endswith("-setup.exe")), None)
    return {
        "current": __version__,
        "latest": version,
        "available": is_newer(version),
        "notes": data.get("body") or "",
        "page": data.get("html_url") or RELEASES_PAGE,
        "installer_url": installer.get("browser_download_url") if installer else None,
        "installer_mb": round(installer.get("size", 0) / 1e6) if installer else None,
        "can_install": bool(installer) and is_installed() and sys.platform == "win32",
    }


def download_installer(url: str, target: Path, progress: Callable[[float], None] | None = None,
                       opener: Callable = urllib.request.urlopen) -> Path:
    """Download the installer to `target`; progress(fraction 0..1)."""
    request = urllib.request.Request(url, headers={"User-Agent": f"Verbalis/{__version__}"})
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    with opener(request, timeout=60) as response, tmp.open("wb") as f:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    tmp.replace(target)
    return target


# ---------------------------------------------------------------- what's new

def changelog_path() -> Path | None:
    """CHANGELOG.md next to the package: repo root in a checkout, bundle root when installed."""
    here = Path(__file__).resolve()
    candidates = [here.parents[2] / "CHANGELOG.md", here.parents[1] / "CHANGELOG.md"]
    if getattr(sys, "_MEIPASS", None):
        candidates.insert(0, Path(sys._MEIPASS) / "CHANGELOG.md")
    return next((p for p in candidates if p.exists()), None)


def changelog_sections(text: str) -> list[dict]:
    """[{version, title, body}] in file order (newest first)."""
    sections: list[dict] = []
    for line in text.splitlines():
        m = SECTION.match(line)
        if m:
            sections.append({"version": m.group(1), "title": line[3:].strip(), "body": ""})
        elif sections:
            sections[-1]["body"] += line + "\n"
    for s in sections:
        s["body"] = s["body"].strip()
    return sections


def changes_between(old: str, new: str = __version__, text: str | None = None) -> list[dict]:
    """Changelog sections with old < version <= new, newest first."""
    if text is None:
        path = changelog_path()
        if path is None:
            return []
        text = path.read_text(encoding="utf-8")
    low, high = parse_version(old), parse_version(new)
    return [s for s in changelog_sections(text) if low < parse_version(s["version"]) <= high]
