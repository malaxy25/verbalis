"""Modelle finden, auflösen und konvertieren.

faster-whisper braucht Modelle im CTranslate2-Format. Es gibt drei Quellen:

1. Eingebaute Namen wie "large-v3-turbo" – lädt faster-whisper selbst herunter.
2. Hugging-Face-Repos, die schon im CTranslate2-Format sind – ebenso.
3. Normale Hugging-Face-Whisper-Modelle (z.B. Schweizerdeutsch-Fine-Tunes) –
   die konvertieren wir einmalig mit `mitschrift modell-konvertieren` nach
   ~/.mitschrift/modelle/. Danach sind sie unter ihrer ID nutzbar.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

EMPFOHLEN: list[tuple[str, str]] = [
    ("Flix-AI/flix-swissgerman-full", "Schweizerdeutsch-Fine-Tune (large-v3), bestes Ergebnis im Test – konvertieren nötig"),
    ("large-v3", "Original von OpenAI, fast gleich gut, etwas schneller"),
    ("large-v3-turbo", "deutlich schneller, aber schwächer bei Dialekt"),
]
STANDARD_MODELL = EMPFOHLEN[0][0]

GEWICHTSDATEIEN = (
    "model.safetensors",
    "model.safetensors.index.json",
    "pytorch_model.bin",
    "pytorch_model.bin.index.json",
)

ZUSATZDATEIEN = ("tokenizer.json", "preprocessor_config.json")


class ModellFehler(RuntimeError):
    pass


def mitschrift_home() -> Path:
    return Path(os.environ.get("MITSCHRIFT_HOME", Path.home() / ".mitschrift"))


def modell_ordner() -> Path:
    return mitschrift_home() / "modelle"


def slug(modell: str) -> str:
    return modell.replace("/", "__").replace("\\", "__").strip("_.")


def eingebaute_modelle() -> list[str]:
    from faster_whisper.utils import available_models

    return list(available_models())


def aufloesen(modell: str) -> str:
    """Modellname → etwas, das WhisperModel() laden kann."""
    pfad = Path(modell).expanduser()
    if pfad.is_dir():
        if not (pfad / "model.bin").exists():
            raise ModellFehler(f"{pfad} enthält kein model.bin – ist das ein CTranslate2-Modell?")
        return str(pfad)

    konvertiert = modell_ordner() / slug(modell)
    if (konvertiert / "model.bin").exists():
        return str(konvertiert)

    if modell in eingebaute_modelle() or "/" in modell:
        return modell  # faster-whisper lädt selbst herunter

    raise ModellFehler(
        f"Unbekanntes Modell '{modell}'. Erlaubt sind eingebaute Namen "
        f"({', '.join(eingebaute_modelle())}), Hugging-Face-IDs oder ein lokaler Ordner."
    )


def konvertierte_modelle() -> list[str]:
    ordner = modell_ordner()
    if not ordner.exists():
        return []
    ergebnis = []
    for d in sorted(ordner.iterdir()):
        info = d / "mitschrift.json"
        if (d / "model.bin").exists():
            ergebnis.append(json.loads(info.read_text())["quelle"] if info.exists() else d.name)
    return ergebnis


def _basismodell_fuer(num_mel_bins: int) -> str:
    # v3 und v3-turbo nutzen 128 Mel-Bänder, ältere Modelle 80.
    return "openai/whisper-large-v3" if num_mel_bins == 128 else "openai/whisper-large-v2"


def pruefe_repo(modell_id: str, dateien: set[str]) -> None:
    """Vor dem langen Download prüfen, ob das Repo überhaupt ein ganzes Modell enthält."""
    if any(f in dateien for f in GEWICHTSDATEIEN) and "config.json" in dateien:
        return
    if "adapter_config.json" in dateien:
        raise ModellFehler(
            f"'{modell_id}' ist nur ein LoRA-Adapter, kein vollständiges Modell. "
            "Bitte die vollständige Variante verwenden (z.B. Flix-AI/flix-swissgerman-full statt …-lora)."
        )
    if "model.bin" in dateien:
        raise ModellFehler(
            f"'{modell_id}' ist bereits im CTranslate2-Format und kann direkt mit --modell genutzt werden."
        )
    raise ModellFehler(
        f"'{modell_id}' enthält keine Modellgewichte. Möglicherweise wurde das Modell vom Autor "
        "zurückgezogen – auf der Hugging-Face-Seite nachsehen."
    )


def konvertieren(modell_id: str, quantisierung: str = "float16", erzwingen: bool = False) -> Path:
    """Hugging-Face-Whisper-Modell ins CTranslate2-Format umwandeln.

    float16 als Speicherformat ist kompakt; beim Laden kann trotzdem int8
    (CPU) oder float16 (GPU) gewählt werden.
    """
    try:
        from ctranslate2.converters import TransformersConverter
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError as e:
        raise ModellFehler(
            'Für die Konvertierung fehlen Pakete. Installiere: pip install -e ".[konvertieren]"'
        ) from e

    ziel = modell_ordner() / slug(modell_id)
    if (ziel / "model.bin").exists() and not erzwingen:
        return ziel

    dateien = set(list_repo_files(modell_id))
    pruefe_repo(modell_id, dateien)

    quell_config = json.loads(Path(hf_hub_download(modell_id, "config.json")).read_text())
    vorhanden = [f for f in ZUSATZDATEIEN if f in dateien]

    ziel.parent.mkdir(parents=True, exist_ok=True)
    TransformersConverter(modell_id, copy_files=vorhanden or None, low_cpu_mem_usage=True).convert(
        str(ziel), quantization=quantisierung, force=True
    )

    # Fehlen Tokenizer oder Preprocessor-Config im Fine-Tune, nehmen wir sie
    # vom Basismodell. Die Mel-Bänder müssen stimmen, sonst kommt Unsinn raus.
    fehlend = [f for f in ZUSATZDATEIEN if not (ziel / f).exists()]
    if fehlend:
        basis = _basismodell_fuer(int(quell_config.get("num_mel_bins", 80)))
        for f in fehlend:
            shutil.copy(hf_hub_download(basis, f), ziel / f)

    (ziel / "mitschrift.json").write_text(
        json.dumps({"quelle": modell_id, "quantisierung": quantisierung}, indent=2)
    )
    return ziel
