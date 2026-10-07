"""Zwei-Spur-Aufnahme: Mikrofon ("ich") und Loopback ("gegenueber").

Jede Spur läuft in einem eigenen Thread und schreibt direkt in eine
WAV-Datei (Mono, 16 bit). So geht auch bei langen Calls kein RAM verloren
und bei einem Absturz ist das Bisherige noch auf der Platte.

Synchronität: Beide Spuren beziehen sich auf denselben Startzeitpunkt t0.
Liefert ein Gerät eine Weile keine Daten (z.B. Treiberaussetzer), füllen
wir die Lücke mit Stille auf. Dadurch bleiben die Zeitstempel beider Spuren
vergleichbar – wichtig, um später die Transkripte zusammenzuführen.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf

SAMPLERATE = 48_000
BLOCK_SEKUNDEN = 0.1
LUECKEN_TOLERANZ_SEKUNDEN = 0.25


def fehlende_frames(
    vergangen_s: float,
    samplerate: int,
    geschrieben: int,
    chunk_laenge: int,
    toleranz_s: float = LUECKEN_TOLERANZ_SEKUNDEN,
) -> int:
    """Wie viele Frames Stille vor dem aktuellen Chunk fehlen.

    Der Chunk endet "jetzt". Was zwischen dem bisher Geschriebenen und dem
    Beginn des Chunks fehlt, ist eine Lücke. Kleine Abweichungen (Jitter)
    ignorieren wir, damit wir nicht ständig Mini-Stille einfügen.
    """
    erwartet = int(vergangen_s * samplerate)
    luecke = erwartet - geschrieben - chunk_laenge
    return luecke if luecke > toleranz_s * samplerate else 0


def _com_initialisieren() -> None:
    """Unter Windows braucht jeder Audio-Thread eine COM-Initialisierung."""
    if sys.platform == "win32":
        import ctypes

        # COINIT_MULTITHREADED = 0; Fehler "schon initialisiert" ist egal.
        ctypes.windll.ole32.CoInitializeEx(None, 0)


@dataclass
class SpurStatus:
    name: str
    pfad: Path
    geschrieben_frames: int = 0
    aufgefuellt_frames: int = 0
    pegel_rms: float = 0.0
    fehler: BaseException | None = None


class Spur(threading.Thread):
    def __init__(
        self,
        name: str,
        geraet: Any,
        pfad: Path,
        stopp: threading.Event,
        t0: float,
        samplerate: int = SAMPLERATE,
        uhr: Callable[[], float] = time.monotonic,
    ):
        super().__init__(name=f"spur-{name}", daemon=True)
        self.geraet = geraet
        self.stopp = stopp
        self.t0 = t0
        self.samplerate = samplerate
        self.uhr = uhr
        self.status = SpurStatus(name=name, pfad=pfad)

    def run(self) -> None:
        try:
            _com_initialisieren()
            self._aufnehmen()
        except BaseException as e:  # Fehler an den Hauptthread melden
            self.status.fehler = e
            self.stopp.set()

    def _aufnehmen(self) -> None:
        block = int(self.samplerate * BLOCK_SEKUNDEN)
        s = self.status
        with sf.SoundFile(
            s.pfad, "w", samplerate=self.samplerate, channels=1, subtype="PCM_16"
        ) as datei, self.geraet.recorder(samplerate=self.samplerate, blocksize=block) as rec:
            while not self.stopp.is_set():
                daten = rec.record(numframes=block)
                mono = daten.mean(axis=1) if daten.ndim == 2 else daten
                mono = mono.astype(np.float32, copy=False)

                luecke = fehlende_frames(
                    self.uhr() - self.t0, self.samplerate, s.geschrieben_frames, len(mono)
                )
                if luecke:
                    datei.write(np.zeros(luecke, dtype=np.float32))
                    s.geschrieben_frames += luecke
                    s.aufgefuellt_frames += luecke

                datei.write(mono)
                s.geschrieben_frames += len(mono)
                s.pegel_rms = float(np.sqrt(np.mean(mono**2))) if len(mono) else 0.0


@dataclass
class ZweiSpurRecorder:
    """Startet und stoppt Mikrofon- und Loopback-Spur gemeinsam."""

    mikrofon: Any
    loopback: Any
    ordner: Path
    samplerate: int = SAMPLERATE
    stopp: threading.Event = field(default_factory=threading.Event)
    spuren: list[Spur] = field(default_factory=list)
    t0: float = 0.0

    def start(self) -> None:
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.t0 = time.monotonic()
        self.spuren = [
            Spur("ich", self.mikrofon, self.ordner / "ich.wav", self.stopp, self.t0, self.samplerate),
            Spur("gegenueber", self.loopback, self.ordner / "gegenueber.wav", self.stopp, self.t0, self.samplerate),
        ]
        for spur in self.spuren:
            spur.start()

    def stoppen(self, timeout: float = 5.0) -> None:
        self.stopp.set()
        for spur in self.spuren:
            spur.join(timeout)

    @property
    def laeuft(self) -> bool:
        return not self.stopp.is_set()

    @property
    def fehler(self) -> list[BaseException]:
        return [s.status.fehler for s in self.spuren if s.status.fehler]

    def status(self) -> list[SpurStatus]:
        return [s.status for s in self.spuren]
