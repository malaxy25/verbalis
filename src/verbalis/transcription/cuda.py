"""Nvidia GPU (CUDA) for faster-whisper on Windows and Linux – experimental.

CTranslate2's wheels can run on Nvidia GPUs but need cuBLAS 12 and cuDNN 9, which are not
part of the installer (about 1.3 GB). `verbalis gpu --install` downloads NVIDIA's own wheels
from PyPI (pinned versions, SHA-256 from PyPI checked) and keeps only the libraries, in
~/.verbalis/cuda. A development environment can instead `pip install nvidia-cublas-cu12
nvidia-cudnn-cu12`; those are found too.

CTranslate2 looks the libraries up by file name when it first needs them. `prepare()` loads
them into the process beforehand, so that lookup finds them – no PATH or LD_LIBRARY_PATH needed.
Device "auto" uses the GPU only when an Nvidia GPU is there and every library loads;
FasterWhisperTranscriber falls back to the CPU on any GPU error.
"""

from __future__ import annotations

import ctypes
import importlib.util
import json
import logging
import os
import platform
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .models import ModelError, verbalis_home

log = logging.getLogger(__name__)

# CTranslate2 4.6.3+ is built for CUDA 12.8 and cuDNN 9
PACKAGES = [("nvidia-cublas-cu12", "12.8.4.1"), ("nvidia-cudnn-cu12", "9.10.2.21")]
COMPUTE_TYPE = "int8_float16"   # needs little graphics memory (T500: 2–4 GB), about as fast as float16

WINDOWS = sys.platform == "win32"
# in loading order: cuBLAS first (cuDNN needs it), then cuDNN; the cuDNN parts may depend on each other
LIBRARY_PATTERNS = (
    [r"cublasLt64_12\.dll", r"cublas64_12\.dll", r"cudnn64_9\.dll", r"cudnn_.*64_9\.dll"] if WINDOWS else
    [r"libcublasLt\.so\.12", r"libcublas\.so\.12", r"libcudnn\.so\.9", r"libcudnn_.*\.so\.9"]
)
REQUIRED = LIBRARY_PATTERNS[:3]

_state: dict = {}            # result of prepare(): {"problem": str | None, "loaded": [...]}
_handles: list = []          # keep the loaded libraries alive


def cuda_dir() -> Path:
    return verbalis_home() / "cuda"


def wheel_matches(filename: str, system: str = sys.platform, machine: str | None = None) -> bool:
    """The NVIDIA wheel for this system: win_amd64 or manylinux x86_64."""
    machine = (machine or platform.machine()).lower()
    if system == "win32":
        return filename.endswith("-win_amd64.whl")
    if system.startswith("linux") and machine in ("x86_64", "amd64"):
        return "manylinux" in filename and filename.endswith("_x86_64.whl")
    return False


def library_dirs() -> list[Path]:
    """Where the libraries may be: our download, then pip packages in this environment."""
    dirs = [cuda_dir()]
    for package in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(package)
        except (ImportError, ValueError):
            spec = None
        for location in (spec.submodule_search_locations or []) if spec else []:
            dirs.append(Path(location) / ("bin" if WINDOWS else "lib"))
    return [d for d in dirs if d.is_dir()]


def find_libraries(dirs: list[Path]) -> list[Path]:
    """The library files in loading order (first folder wins per file name)."""
    found: dict[str, Path] = {}
    for pattern in LIBRARY_PATTERNS:
        for folder in dirs:
            for path in sorted(folder.iterdir()):
                if re.fullmatch(pattern, path.name) and path.name not in found:
                    found[path.name] = path
    return list(found.values())


def missing(libraries: list[Path]) -> list[str]:
    names = [p.name for p in libraries]
    return [pattern.replace("\\", "") for pattern in REQUIRED if not any(re.fullmatch(pattern, n) for n in names)]


def gpu_count() -> int:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count()
    except Exception:
        log.exception("Could not ask CTranslate2 for CUDA devices")
        return 0


def _load(path: Path):
    return ctypes.WinDLL(str(path)) if WINDOWS else ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)


def prepare() -> str | None:
    """Make CUDA usable in this process. None = ready, otherwise the reason (German, for the user)."""
    if "problem" in _state:
        return _state["problem"]
    _state["problem"] = problem = _prepare()
    if problem:
        log.info("Nvidia GPU not used: %s", problem)
    return problem


def _prepare() -> str | None:
    if not (WINDOWS or sys.platform.startswith("linux")):
        return "Nvidia-Grafikkarten werden nur unter Windows und Linux unterstützt."
    if gpu_count() == 0:
        return "Keine Nvidia-Grafikkarte gefunden (oder kein aktueller Nvidia-Treiber)."
    dirs = library_dirs()
    libraries = find_libraries(dirs)
    if missing(libraries):
        return ("Die Nvidia-Bibliotheken (cuBLAS, cuDNN) fehlen noch – einmalig laden: Einstellungen → Diagnose "
                "→ «Nvidia-Bibliotheken laden» oder verbalis gpu --install")
    if WINDOWS:
        for folder in dirs:
            os.add_dll_directory(str(folder))
        os.environ["PATH"] = os.pathsep.join([str(d) for d in dirs] + [os.environ.get("PATH", "")])
    pending, errors = list(libraries), {}
    while pending:             # a library whose dependency isn't loaded yet gets another round
        progress = False
        for path in list(pending):
            try:
                _handles.append(_load(path))
            except OSError as e:
                errors[path.name] = str(e)
                continue
            pending.remove(path)
            errors.pop(path.name, None)
            progress = True
        if not progress:
            break
    required = [p for p in pending if any(re.fullmatch(r, p.name) for r in REQUIRED)]
    if required:
        return f"Nvidia-Bibliothek {required[0].name} lässt sich nicht laden: {errors.get(required[0].name)}"
    for path in pending:
        log.warning("Optional CUDA library %s not loaded: %s", path.name, errors.get(path.name))
    _state["loaded"] = [str(p) for p in libraries if p not in pending]
    log.info("CUDA libraries loaded from %s", ", ".join(str(d) for d in dirs))
    return None


def choose(device: str) -> tuple[str, str]:
    """(device, compute type) for «auto», «cuda» or «cpu»."""
    if device == "cpu":
        return "cpu", "int8"
    problem = prepare()
    if problem is None:
        return "cuda", COMPUTE_TYPE
    if device == "cuda":
        raise ModelError(problem)
    return "cpu", "int8"


# ---------------------------------------------------------------- download


def install(progress: Callable[[str, float], None] | None = None,
            opener: Callable = urllib.request.urlopen) -> Path:
    """Download cuBLAS and cuDNN once into ~/.verbalis/cuda (only the libraries are kept)."""
    from . import wheels

    target = cuda_dir()
    partial = target.with_name("cuda.partial")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    try:
        for package, version in PACKAGES:
            info = wheels.wheel_info(package, version, lambda names: next((n for n in names if wheel_matches(n)), None),
                                     opener)
            wheel = wheels.download(info, partial, (lambda f, p=package: progress(p, f)) if progress else None, opener)
            with zipfile.ZipFile(wheel) as archive:
                for member in archive.namelist():
                    name = member.rsplit("/", 1)[-1]
                    in_library_folder = re.match(r"nvidia/[^/]+/(bin|lib)/[^/]+$", member)
                    if in_library_folder and any(re.fullmatch(p, name) for p in LIBRARY_PATTERNS):
                        with archive.open(member) as source, (partial / name).open("wb") as out:
                            shutil.copyfileobj(source, out)
            wheel.unlink()
        (partial / "versions.json").write_text(json.dumps(dict(PACKAGES), indent=2), encoding="utf-8")
        if missing(find_libraries([partial])):
            raise ModelError("Die Nvidia-Pakete enthalten nicht die erwarteten Bibliotheken – nichts installiert.")
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    shutil.rmtree(target, ignore_errors=True)
    partial.replace(target)
    _state.clear()
    return target


def status() -> dict:
    """For `verbalis gpu`: what is there and whether Verbalis would use the GPU."""
    libraries = find_libraries(library_dirs())
    return {"gpus": gpu_count(), "libraries": [str(p) for p in libraries], "missing": missing(libraries),
            "problem": prepare()}
