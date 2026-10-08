"""Find, resolve and convert models.

faster-whisper needs models in CTranslate2 format. There are three sources:

1. Built-in names such as "large-v3-turbo" – faster-whisper downloads them itself.
2. Hugging Face repos already in CTranslate2 format – same.
3. Regular Hugging Face Whisper models (e.g. Swiss German fine-tunes) – converted
   once with `verbalis convert-model` into ~/.verbalis/models/ and usable under
   their ID afterwards.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

# (model id, description shown in the UI – German)
RECOMMENDED: list[tuple[str, str]] = [
    ("Flix-AI/flix-swissgerman-full", "Schweizerdeutsch-Fine-Tune (large-v3), bestes Ergebnis im Test"),
    ("large-v3", "Original von OpenAI, fast gleich gut, etwas schneller"),
    ("large-v3-turbo", "Deutlich schneller, aber schwächer bei Dialekt"),
]
DEFAULT_MODEL = RECOMMENDED[0][0]
# Readable names for the model tiles in the settings (the id is shown below)
DISPLAY_NAMES = {
    "Flix-AI/flix-swissgerman-full": "Flix Schweizerdeutsch",
    "large-v3": "Whisper large-v3",
    "large-v3-turbo": "Whisper large-v3 turbo",
}

# Models that only exist in Transformers format upstream are provided ready for
# faster-whisper (CTranslate2) in our own Hugging Face repo, so nobody has to
# convert them. Flix is Apache 2.0, redistribution with attribution is allowed.
DOWNLOAD_REPO = {
    "Flix-AI/flix-swissgerman-full": "malaxy/flix-swissgerman-ct2",
}
# Revision of the original our converted copy was made from. A monthly GitHub
# Action (.github/workflows/model-check.yml) compares it with the original and
# opens an issue when Flix-AI publishes a newer version.
UPSTREAM_REVISIONS = {
    "Flix-AI/flix-swissgerman-full": "a9c347a904af5d31b28c537ac732e0618aed6136",
}
HF_PAGE = "https://huggingface.co/"
# Approximate download size in GB (float16 CTranslate2), shown before downloading
SIZE_GB = {
    "Flix-AI/flix-swissgerman-full": 3.1,
    "large-v3": 3.1,
    "large-v3-turbo": 1.6,
}
# Same files faster-whisper downloads
FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]

WEIGHT_FILES = (
    "model.safetensors",
    "model.safetensors.index.json",
    "pytorch_model.bin",
    "pytorch_model.bin.index.json",
)
EXTRA_FILES = ("tokenizer.json", "preprocessor_config.json")


class ModelError(RuntimeError):
    pass


def verbalis_home() -> Path:
    return Path(os.environ.get("VERBALIS_HOME", Path.home() / ".verbalis"))


def models_dir() -> Path:
    return verbalis_home() / "models"


def slug(model: str) -> str:
    return model.replace("/", "__").replace("\\", "__").strip("_.")


def builtin_models() -> list[str]:
    from faster_whisper.utils import available_models

    return list(available_models())


def resolve(model: str) -> str:
    """Model name → something WhisperModel() can load."""
    path = Path(model).expanduser()
    if path.is_dir():
        if not (path / "model.bin").exists():
            raise ModelError(f"{path} enthält kein model.bin – ist das ein CTranslate2-Modell?")
        return str(path)

    converted = models_dir() / slug(model)
    if (converted / "model.bin").exists():
        return str(converted)

    if model in DOWNLOAD_REPO:
        return DOWNLOAD_REPO[model]  # ready-converted copy, faster-whisper downloads it

    if model in builtin_models() or "/" in model:
        return model  # faster-whisper downloads it

    raise ModelError(
        f"Unbekanntes Modell '{model}'. Erlaubt sind eingebaute Namen "
        f"({', '.join(builtin_models())}), Hugging-Face-IDs oder ein lokaler Ordner."
    )


def repo_for(model: str) -> str | None:
    """Hugging Face repo a model is downloaded from, or None if it is local only."""
    if Path(model).expanduser().is_dir() or (models_dir() / slug(model) / "model.bin").exists():
        return None
    if model in DOWNLOAD_REPO:
        return DOWNLOAD_REPO[model]
    try:
        from faster_whisper.utils import _MODELS  # built-in names → repos
    except ImportError:
        _MODELS = {}
    if model in _MODELS:
        return _MODELS[model]
    return model if "/" in model else None


def is_local(model: str) -> bool:
    """Is the model already on this computer (no download needed)?"""
    repo = repo_for(model)
    if repo is None:
        return Path(model).expanduser().is_dir() or (models_dir() / slug(model) / "model.bin").exists()
    from huggingface_hub import try_to_load_from_cache

    return isinstance(try_to_load_from_cache(repo, "model.bin"), str)


def _cache_folder(repo: str) -> Path:
    from huggingface_hub import constants

    return Path(constants.HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))


def _folder_bytes(folder: Path) -> int:
    total = 0
    for f in folder.rglob("*"):
        try:
            if f.is_file() and not f.is_symlink():
                total += f.stat().st_size
        except FileNotFoundError:  # files move while downloading
            pass
    return total


def download(model: str, progress=None) -> None:
    """Download a model into the Hugging Face cache; progress(bytes_done) every half second.

    Runs the download in a thread and measures the cache folder, because
    huggingface_hub reports no byte progress we could pass on.
    """
    import threading

    from huggingface_hub import snapshot_download

    repo = repo_for(model)
    if repo is None:
        return
    folder = _cache_folder(repo)
    start = _folder_bytes(folder) if folder.exists() else 0
    result: dict = {}

    def run():
        try:
            snapshot_download(repo, allow_patterns=FILES)
        except Exception as e:  # reported below in the calling thread
            result["error"] = e

    worker = threading.Thread(target=run, name="model-download", daemon=True)
    worker.start()
    while worker.is_alive():
        worker.join(0.5)
        if progress and folder.exists():
            progress(max(_folder_bytes(folder) - start, 0))
    if "error" in result:
        raise ModelError(
            f"Das Modell konnte nicht heruntergeladen werden ({repo}). Internetverbindung prüfen. "
            f"Details: {result['error']}") from result["error"]


def page_url(model: str) -> str | None:
    """Web page of the model on Hugging Face (the download repo, or the original if converted locally)."""
    repo = repo_for(model)
    if repo:
        return HF_PAGE + repo
    return HF_PAGE + model if "/" in model and not Path(model).expanduser().is_dir() else None


def local_revision(model: str) -> dict | None:
    """Which revision of a downloaded model is on this computer, and since when."""
    repo = repo_for(model)
    if repo is None:
        return None
    folder = _cache_folder(repo)
    try:
        sha = (folder / "refs" / "main").read_text(encoding="utf-8").strip()
        snapshot = folder / "snapshots" / sha
        loaded = datetime.fromtimestamp(snapshot.stat().st_mtime).astimezone()
    except (FileNotFoundError, OSError):
        return None
    return {"revision": sha, "loaded": loaded.isoformat(timespec="minutes")}


def remote_revision(model: str, timeout: float = 6.0) -> dict | None:
    """Latest revision on Hugging Face, or None (offline, unknown repo, …)."""
    repo = repo_for(model)
    if repo is None:
        return None
    from huggingface_hub import HfApi

    info = HfApi().model_info(repo, timeout=timeout)
    changed = info.last_modified.astimezone().isoformat(timespec="minutes") if info.last_modified else None
    return {"revision": info.sha, "changed": changed}


def _model_files(info) -> dict[str, str]:
    """{file name: content id} for the files Verbalis downloads – README & co. don't count."""
    import fnmatch

    return {s.rfilename: s.blob_id for s in (info.siblings or [])
            if any(fnmatch.fnmatch(s.rfilename, pattern) for pattern in FILES)}


def check_update(model: str, timeout: float = 6.0) -> dict | None:
    """Is there a newer version of the *model files* than the one on this computer?

    A new revision on Hugging Face alone isn't enough: changing only the model
    card also creates one. So the content ids of the downloaded files are
    compared between our revision and the latest. Returns None if nothing to do.
    """
    repo = repo_for(model)
    local = local_revision(model)
    if repo is None or local is None:
        return None
    from huggingface_hub import HfApi

    api = HfApi()
    latest = api.model_info(repo, timeout=timeout, files_metadata=True)
    if latest.sha == local["revision"]:
        return None
    ours = api.model_info(repo, revision=local["revision"], timeout=timeout, files_metadata=True)
    if _model_files(latest) == _model_files(ours):
        return None   # only documentation changed
    changed = latest.last_modified.astimezone().isoformat(timespec="minutes") if latest.last_modified else None
    return {"revision": latest.sha, "changed": changed}


def converted_models() -> list[str]:
    directory = models_dir()
    if not directory.exists():
        return []
    result = []
    for d in sorted(directory.iterdir()):
        info = d / "verbalis.json"
        if (d / "model.bin").exists():
            result.append(json.loads(info.read_text())["source"] if info.exists() else d.name)
    return result


def _base_model_for(num_mel_bins: int) -> str:
    # v3 and v3-turbo use 128 mel bins, older models 80.
    return "openai/whisper-large-v3" if num_mel_bins == 128 else "openai/whisper-large-v2"


def check_repo(model_id: str, files: set[str]) -> None:
    """Before the long download: does the repo contain a complete model at all?"""
    if any(f in files for f in WEIGHT_FILES) and "config.json" in files:
        return
    if "adapter_config.json" in files:
        raise ModelError(
            f"'{model_id}' ist nur ein LoRA-Adapter, kein vollständiges Modell. "
            "Bitte die vollständige Variante verwenden (z.B. Flix-AI/flix-swissgerman-full statt …-lora)."
        )
    if "model.bin" in files:
        raise ModelError(
            f"'{model_id}' ist bereits im CTranslate2-Format und kann direkt mit --model genutzt werden."
        )
    raise ModelError(
        f"'{model_id}' enthält keine Modellgewichte. Möglicherweise wurde das Modell vom Autor "
        "zurückgezogen – auf der Hugging-Face-Seite nachsehen."
    )


def convert(model_id: str, quantization: str = "float16", force: bool = False) -> Path:
    """Convert a Hugging Face Whisper model to CTranslate2 format.

    float16 is a compact storage format; int8 (CPU) or float16 (GPU) can still
    be chosen when loading.
    """
    try:
        from ctranslate2.converters import TransformersConverter
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError as e:
        raise ModelError(
            'Für die Konvertierung fehlen Pakete. Installiere: pip install -e ".[convert]"'
        ) from e

    target = models_dir() / slug(model_id)
    if (target / "model.bin").exists() and not force:
        return target

    files = set(list_repo_files(model_id))
    check_repo(model_id, files)

    source_config = json.loads(Path(hf_hub_download(model_id, "config.json")).read_text())
    present = [f for f in EXTRA_FILES if f in files]

    target.parent.mkdir(parents=True, exist_ok=True)
    TransformersConverter(model_id, copy_files=present or None, low_cpu_mem_usage=True).convert(
        str(target), quantization=quantization, force=True
    )

    # If the fine-tune lacks tokenizer or preprocessor config, take them from the
    # base model. The mel bins must match, otherwise the output is garbage.
    missing = [f for f in EXTRA_FILES if not (target / f).exists()]
    if missing:
        base = _base_model_for(int(source_config.get("num_mel_bins", 80)))
        for f in missing:
            shutil.copy(hf_hub_download(base, f), target / f)

    (target / "verbalis.json").write_text(json.dumps({"source": model_id, "quantization": quantization}, indent=2))
    return target
