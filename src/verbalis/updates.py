"""Updates: check GitHub for a newer release, download the installer, show what's new.

- `check()` asks the GitHub API for the latest release (one small request, only
  when enabled in the settings). Nothing about the user is sent.
- `download_installer()` fetches the update for this platform:
  Windows: Verbalis-X.Y.Z-setup.exe – the app starts it and closes, the installer
  replaces the program files.
  macOS: Verbalis-X.Y.Z-macos-arm64.zip – unpacked next to the running app; a small
  script waits until Verbalis has closed, swaps the app bundle and opens the new one.
  Both keep ~/.verbalis (settings, corrections, models, recordings).
- `changes_between()` reads CHANGELOG.md (bundled with the app) and returns the
  sections newer than the version the user had before – shown once after an update.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable

from . import __version__

REPO = "malaxy25/verbalis"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
SECTION = re.compile(r"^## (\d+(?:\.\d+)*)\b(.*)$")
ASSET_SUFFIX = {"win32": "-setup.exe", "darwin": "-macos-arm64.zip"}   # update file per platform


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
    suffix = ASSET_SUFFIX.get(sys.platform)
    installer = next((a for a in data.get("assets", [])
                      if suffix and a.get("name", "").lower().endswith(suffix)), None)
    return {
        "current": __version__,
        "latest": version,
        "available": is_newer(version),
        "notes": data.get("body") or "",
        "page": data.get("html_url") or RELEASES_PAGE,
        "installer_url": installer.get("browser_download_url") if installer else None,
        "installer_name": installer.get("name") if installer else None,
        "installer_size": installer.get("size") if installer else None,
        # GitHub computes a SHA-256 for every release asset – detects damaged or swapped downloads
        "installer_sha256": _sha256_of(installer.get("digest")) if installer else None,
        "installer_mb": round(installer.get("size", 0) / 1e6) if installer else None,
        "can_install": bool(installer) and is_installed() and (sys.platform == "win32" or app_bundle() is not None),
        "platform": sys.platform,
    }


def _sha256_of(digest: str | None) -> str | None:
    return digest.split(":", 1)[1].lower() if digest and digest.lower().startswith("sha256:") else None


def download_installer(url: str, target: Path, progress: Callable[[float], None] | None = None,
                       opener: Callable = urllib.request.urlopen, sha256: str | None = None,
                       size: int | None = None) -> Path:
    """Download the installer to `target`; progress(fraction 0..1).

    Checks size and SHA-256 (from the GitHub release) before the file is used; a
    mismatch deletes it. This catches damaged and swapped downloads. It does not
    protect against a compromised GitHub account – only code signing does.
    """
    import hashlib

    request = urllib.request.Request(url, headers={"User-Agent": f"Verbalis/{__version__}"})
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    hasher = hashlib.sha256()
    with opener(request, timeout=60) as response, tmp.open("wb") as f:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(1 << 20):
            f.write(chunk)
            hasher.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    problem = None
    if size and done != size:
        problem = f"unvollständig ({done:,} statt {size:,} Bytes)"
    elif sha256 and hasher.hexdigest() != sha256:
        problem = "die Prüfsumme stimmt nicht mit der von GitHub überein"
    if problem:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Das heruntergeladene Update ist nicht in Ordnung: {problem}. Es wurde nicht ausgeführt.")
    tmp.replace(target)
    return target


def expected_name(info: dict) -> bool:
    """The asset must be the Verbalis update for exactly the announced version and this platform."""
    name, version = info.get("installer_name") or "", info.get("latest") or ""
    suffix = ASSET_SUFFIX.get(sys.platform, "")
    return bool(version) and name == f"Verbalis-{version}{suffix}"


# ---------------------------------------------------------------- macOS: swap the app bundle

def app_bundle(executable: str | None = None) -> Path | None:
    """The running Verbalis.app (macOS), or None when not running from an app bundle."""
    for parent in Path(executable or sys.executable).resolve().parents:
        if parent.suffix == ".app":
            return parent
    return None


def unpack_mac_update(zip_path: Path, workdir: Path, extract: Callable | None = None) -> Path:
    """Unpack the downloaded zip and return the new Verbalis.app inside it.

    `ditto` keeps symlinks, permissions and the code signature of the bundle –
    Python's zipfile would lose them.
    """
    import shutil

    if workdir.exists():
        shutil.rmtree(workdir)   # leftovers of an earlier, interrupted update
    workdir.mkdir(parents=True)
    (extract or (lambda z, d: subprocess.run(["ditto", "-x", "-k", str(z), str(d)], check=True)))(zip_path, workdir)
    found = sorted(workdir.glob("*.app"))
    if not found:
        raise RuntimeError("Im heruntergeladenen Update wurde keine Verbalis.app gefunden.")
    return found[0]


def write_swap_script(old_app: Path, new_app: Path, pid: int, script: Path, reopen: str = "open") -> Path:
    """Shell script: wait for Verbalis (pid) to exit, replace the bundle, start the new version.

    The old app is moved aside first and only deleted once the new one is in place,
    so a failed swap can be rolled back.
    """
    old, new, backup = shlex.quote(str(old_app)), shlex.quote(str(new_app)), shlex.quote(str(old_app) + ".old")
    unpacked = shlex.quote(str(new_app.parent))
    script.write_text(f"""#!/bin/sh
# Written by Verbalis to install an update – deletes itself when done.
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
rm -rf {backup}
if mv {old} {backup} && mv {new} {old}; then
  rm -rf {backup}
  command -v xattr >/dev/null && xattr -dr com.apple.quarantine {old} 2>/dev/null
else
  [ -e {old} ] || mv {backup} {old}
fi
rm -rf {unpacked}
{reopen} {old}
rm -f "$0"
""", encoding="utf-8")
    script.chmod(0o755)
    return script


def start_swap(script: Path) -> None:
    """Run the swap script detached, so it survives Verbalis closing."""
    subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def can_write(folder: Path) -> bool:
    return os.access(folder, os.W_OK)


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
