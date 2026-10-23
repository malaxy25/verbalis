"""Download pinned wheels from PyPI – for add-ons that don't fit into the installer.

Used for NVIDIA's CUDA libraries (cuda.py) and for MLX on Apple M chips (mlx.py). The
version is pinned in the code; the SHA-256 comes from PyPI over HTTPS and is checked
before a file is used. Nothing is installed with pip – the caller unpacks what it needs.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Callable

from .models import ModelError


def _get(url: str, opener: Callable = urllib.request.urlopen):
    from .. import __version__

    return opener(urllib.request.Request(url, headers={"User-Agent": f"Verbalis/{__version__}"}), timeout=60)


def wheel_info(package: str, version: str, choose: Callable[[list[str]], str | None],
               opener: Callable = urllib.request.urlopen) -> dict:
    """The PyPI file `choose` picks from the file names: {"filename", "url", "size", "sha256"}."""
    with _get(f"https://pypi.org/pypi/{package}/{version}/json", opener) as response:
        data = json.loads(response.read().decode("utf-8"))
    files = {f["filename"]: f for f in data.get("urls", []) if f["filename"].endswith(".whl")}
    name = choose(sorted(files))
    if name is None:
        raise ModelError(f"{package} {version} gibt es nicht für dieses System.")
    file = files[name]
    return {"filename": name, "url": file["url"], "size": file["size"], "sha256": file["digests"]["sha256"]}


def download(info: dict, folder: Path, progress: Callable[[float], None] | None = None,
             opener: Callable = urllib.request.urlopen) -> Path:
    """Download one wheel into `folder`; a wrong checksum deletes it and raises."""
    target = folder / info["filename"]
    hasher, done = hashlib.sha256(), 0
    with _get(info["url"], opener) as response, target.open("wb") as f:
        while chunk := response.read(1 << 20):
            f.write(chunk)
            hasher.update(chunk)
            done += len(chunk)
            if progress:
                progress(done / max(info["size"], 1))
    if hasher.hexdigest() != info["sha256"]:
        target.unlink(missing_ok=True)
        raise ModelError(f"{info['filename']}: die Prüfsumme stimmt nicht mit PyPI überein – nichts installiert.")
    return target
