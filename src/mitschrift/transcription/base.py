"""Gemeinsame Schnittstelle für alle Transkriptions-Backends.

Jedes Backend (faster-whisper, transformers, später evtl. Cloud) setzt
`Transcriber` um. Die App kennt nur diese Schnittstelle – so kann der User
in den Einstellungen ein anderes Modell wählen, ohne dass sich sonst etwas
ändert. Erste Umsetzung: faster.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np


@dataclass
class Segment:
    start: float          # Sekunden ab Aufnahmebeginn
    ende: float
    text: str
    sprecher: str | None = None   # "ich", "SPEAKER_00", später echter Name


class Transcriber(Protocol):
    name: str

    def transkribiere(
        self,
        audio: np.ndarray,  # Mono float32, 16 kHz
        sprache: str = "de",
        fortschritt: Callable[[float, float], None] | None = None,
    ) -> list[Segment]:
        ...
