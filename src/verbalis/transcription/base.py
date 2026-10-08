"""Common interface for all transcription backends.

Every backend (faster-whisper, later maybe transformers or a cloud service)
implements `Transcriber`. The app only knows this interface, so users can pick
a different model in the settings without anything else changing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np


@dataclass
class Segment:
    start: float              # seconds since the start of the recording
    end: float
    text: str
    speaker: str | None = None   # display name, e.g. "Andrea"


class Transcriber(Protocol):
    name: str

    def transcribe(
        self,
        audio: np.ndarray,  # mono float32, 16 kHz
        language: str = "de",
        progress: Callable[[float, float], None] | None = None,
    ) -> list[Segment]:
        ...
