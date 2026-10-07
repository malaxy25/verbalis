import threading
from contextlib import contextmanager

import numpy as np
import soundfile as sf

from mitschrift.audio.recorder import Spur, fehlende_frames

SR = 48_000


def test_keine_luecke_bei_kleinem_jitter():
    # 1.05 s vergangen, 1.0 s geschrieben (inkl. Chunk) → unter Toleranz
    assert fehlende_frames(1.05, SR, geschrieben=int(0.9 * SR), chunk_laenge=int(0.1 * SR)) == 0


def test_luecke_wird_erkannt():
    # 2 s vergangen, aber erst 1 s geschrieben + 0.1 s Chunk → 0.9 s fehlen
    luecke = fehlende_frames(2.0, SR, geschrieben=SR, chunk_laenge=int(0.1 * SR))
    assert luecke == int(0.9 * SR)


class FakeGeraet:
    """Simuliert ein Gerät, das nach 5 Blöcken 1 s lang aussetzt."""

    def __init__(self, uhr, stopp, bloecke=10):
        self.uhr, self.stopp, self.bloecke = uhr, stopp, bloecke

    @contextmanager
    def recorder(self, samplerate, blocksize):
        geraet = self
        zaehler = {"n": 0}

        class Rec:
            def record(self, numframes):
                zaehler["n"] += 1
                geraet.uhr.t += numframes / samplerate
                if zaehler["n"] == 6:
                    geraet.uhr.t += 1.0  # Aussetzer
                if zaehler["n"] >= geraet.bloecke:
                    geraet.stopp.set()
                return np.full((numframes, 2), 0.1, dtype=np.float32)

        yield Rec()


class FakeUhr:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_spur_fuellt_aussetzer_auf(tmp_path):
    uhr, stopp = FakeUhr(), threading.Event()
    pfad = tmp_path / "test.wav"
    spur = Spur("test", FakeGeraet(uhr, stopp), pfad, stopp, t0=0.0, samplerate=SR, uhr=uhr)
    spur.run()  # synchron ausführen

    assert spur.status.fehler is None
    daten, sr = sf.read(pfad)
    # 10 Blöcke à 0.1 s + 1 s Aussetzer = 2 s
    assert abs(len(daten) / sr - 2.0) < 0.01
    assert abs(spur.status.aufgefuellt_frames / SR - 1.0) < 0.01
    # Die Stille liegt an der richtigen Stelle (nach 0.5 s)
    assert np.allclose(daten[int(0.6 * SR):int(1.4 * SR)], 0.0)
    assert np.allclose(daten[: int(0.4 * SR)], 0.1, atol=1e-3)
