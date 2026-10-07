"""Gemeinsame Schnittstelle für alle Transkriptions-Backends.

Jedes Backend (faster-whisper, transformers, später evtl. Cloud) setzt
`Transcriber` um. Die App kennt nur diese Schnittstelle – so kann der User
in den Einstellungen ein anderes Modell wählen, ohne dass sich sonst etwas
ändert. Umsetzung folgt im nächsten Schritt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Segment:
    start: float          # Sekunden ab Aufnahmebeginn
    ende: float
    text: str
    sprecher: str | None = None   # "ich", "SPEAKER_00", später echter Name


class Transcriber(Protocol):
    name: str

    def transkribiere(self, wav: Path, sprache: str = "de") -> list[Segment]:
        ...
