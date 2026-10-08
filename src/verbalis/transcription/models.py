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
from pathlib import Path

# (model id, description shown in the UI – German)
RECOMMENDED: list[tuple[str, str]] = [
    ("Flix-AI/flix-swissgerman-full", "Schweizerdeutsch-Fine-Tune (large-v3), bestes Ergebnis im Test – konvertieren nötig"),
    ("large-v3", "Original von OpenAI, fast gleich gut, etwas schneller"),
    ("large-v3-turbo", "deutlich schneller, aber schwächer bei Dialekt"),
]
DEFAULT_MODEL = RECOMMENDED[0][0]

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

    if model in builtin_models() or "/" in model:
        return model  # faster-whisper downloads it

    raise ModelError(
        f"Unbekanntes Modell '{model}'. Erlaubt sind eingebaute Namen "
        f"({', '.join(builtin_models())}), Hugging-Face-IDs oder ein lokaler Ordner."
    )


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
