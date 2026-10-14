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


def _order(text: str) -> tuple:
    """Sort key: a test build «0.7.23.dev1» comes before the release 0.7.23 (so it gets that update)."""
    numbers = parse_version(text)
    dev = re.search(r"\.dev(\d+)$", (text or "").strip())
    return numbers + ((-1, int(dev.group(1))) if dev else (0, 0))


def is_newer(candidate: str, current: str = __version__) -> bool:
    if not parse_version(candidate) or not parse_version(current):
        return False
    return _order(candidate) > _order(current)


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


def translocated(bundle: Path) -> bool:
    """macOS runs an app started straight from «Downloads» from a read-only random copy
    (/private/var/folders/…/AppTranslocation/…) – it can't replace itself there."""
    return "AppTranslocation" in bundle.parts   # (/private/var/folders/… alone is just the temp folder)


# ---------------------------------------------------------------- macOS: install into «Programme»

def application_folders(home: Path | None = None) -> tuple[Path, Path]:
    """The shared «Programme» (/Applications) and the personal one (~/Applications)."""
    return Path("/Applications"), (home or Path.home()) / "Applications"


def install_place(bundle: Path, home: Path | None = None) -> str | None:
    """Why the app should be moved – or None if it already lies in a «Programme» folder.

    Elsewhere («Downloads», «Schreibtisch», «Dokumente», a disk image) macOS may run a read-only
    copy (App Translocation), the app can't update itself, and copies pile up («Verbalis 2»).
    """
    if translocated(bundle):
        return "Verbalis läuft aus einer schreibgeschützten Kopie (direkt aus «Downloads» gestartet)."
    if bundle.parent in application_folders(home):
        return None
    if str(bundle).startswith("/Volumes/"):
        return "Verbalis läuft direkt aus dem Installationsfenster (Disk-Image)."
    return f"Verbalis liegt in «{bundle.parent.name}», nicht im Ordner «Programme»."


def install_target(home: Path | None = None, writable: Callable[[Path], bool] | None = None) -> Path:
    """/Applications when this user may write there (administrator), else ~/Applications."""
    shared, personal = application_folders(home)
    writable = writable or (lambda folder: os.access(folder, os.W_OK))
    return shared if shared.exists() and writable(shared) else personal


def bundle_version(bundle: Path) -> str | None:
    import plistlib

    try:
        with open(bundle / "Contents" / "Info.plist", "rb") as f:
            return plistlib.load(f).get("CFBundleShortVersionString")
    except (OSError, ValueError):
        return None


def original_bundle(bundle: Path, home: Path | None = None) -> Path | None:
    """For a translocated copy: the Verbalis.app it was started from (same version), if it is findable."""
    if not translocated(bundle):
        return bundle
    version = bundle_version(bundle)
    home = home or Path.home()
    for folder in ("Downloads", "Desktop", "Documents"):
        candidate = home / folder / "Verbalis.app"
        if candidate.is_dir() and bundle_version(candidate) == version:
            return candidate
    return None


def move_to_applications(bundle: Path, home: Path | None = None, writable: Callable[[Path], bool] | None = None,
                         run: Callable = subprocess.run) -> tuple[Path, Path | None]:
    """Put Verbalis into «Programme». Returns (new place, copy left behind that the user may delete).

    Moves the app when it can (same disk: instant, no second copy); copies it from a disk image
    or a translocated copy whose original isn't found. An older Verbalis at the target is replaced.
    """
    import shutil

    target_folder = install_target(home, writable)
    target_folder.mkdir(parents=True, exist_ok=True)
    target = target_folder / "Verbalis.app"
    source = original_bundle(bundle, home)
    copy = source is None or str(source).startswith("/Volumes/")
    source = source or bundle
    if source.resolve() == target.resolve():
        return target, None
    old = target.with_name("Verbalis.app.old")
    if old.exists():
        shutil.rmtree(old)
    if target.exists():
        target.rename(old)
    try:
        if copy:
            run(["ditto", str(source), str(target)], check=True)
        else:
            shutil.move(str(source), str(target))
    except Exception:
        if old.exists() and not target.exists():
            old.rename(target)   # put the previous version back
        raise
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
    # downloaded files are «quarantined»: that is what makes macOS run a read-only copy
    run(["xattr", "-dr", "com.apple.quarantine", str(target)], check=False)
    left_behind = source if copy and not str(source).startswith("/Volumes/") and source != bundle else None
    return target, left_behind


def write_relaunch_script(app: Path, pid: int, script: Path) -> Path:
    """Shell script: wait until this Verbalis has quit, then start the one at its new place."""
    script.write_text(f"""#!/bin/sh
# Written by Verbalis after moving itself into «Programme» – deletes itself when done.
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
open {shlex.quote(str(app))}
rm -f "$0"
""", encoding="utf-8")
    script.chmod(0o755)
    return script


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
