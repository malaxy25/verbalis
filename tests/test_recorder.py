"""Two-track recorder: padding dropouts with silence, pausing without padding."""

import threading
from contextlib import contextmanager

import numpy as np
import soundfile as sf

from verbalis.audio.recorder import Track, missing_frames

SR = 48_000


def test_no_gap_for_small_jitter():
    # 1.05 s elapsed, 1.0 s written (incl. chunk) → below tolerance
    assert missing_frames(1.05, SR, written=int(0.9 * SR), chunk_length=int(0.1 * SR)) == 0


def test_gap_is_detected():
    # 2 s elapsed, but only 1 s written + 0.1 s chunk → 0.9 s missing
    assert missing_frames(2.0, SR, written=SR, chunk_length=int(0.1 * SR)) == int(0.9 * SR)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeDevice:
    """Simulates a device that drops out for 1 s after 5 blocks."""

    def __init__(self, clock, stop, blocks=10):
        self.clock, self.stop, self.blocks = clock, stop, blocks

    @contextmanager
    def recorder(self, samplerate, blocksize):
        device, count = self, {"n": 0}

        class Rec:
            def record(self, numframes):
                count["n"] += 1
                device.clock.t += numframes / samplerate
                if count["n"] == 6:
                    device.clock.t += 1.0  # dropout
                if count["n"] >= device.blocks:
                    device.stop.set()
                return np.full((numframes, 2), 0.1, dtype=np.float32)

        yield Rec()


def test_track_pads_dropout(tmp_path):
    clock, stop = FakeClock(), threading.Event()
    path = tmp_path / "test.wav"
    track = Track("test", FakeDevice(clock, stop), path, stop, t0=0.0, samplerate=SR, clock=clock)
    track.run()  # run synchronously

    assert track.status.error is None
    data, sr = sf.read(path)
    assert abs(len(data) / sr - 2.0) < 0.01             # 10 blocks à 0.1 s + 1 s dropout
    assert abs(track.status.padded_frames / SR - 1.0) < 0.01
    assert np.allclose(data[int(0.6 * SR):int(1.4 * SR)], 0.0)   # silence in the right place
    assert np.allclose(data[: int(0.4 * SR)], 0.1, atol=1e-3)


class PausingDevice(FakeDevice):
    """1 s of audio, then 2 s paused (device keeps delivering), then 1 s of audio."""

    @contextmanager
    def recorder(self, samplerate, blocksize):
        device, count = self, {"n": 0}

        class Rec:
            def record(self, numframes):
                count["n"] += 1
                device.clock.t += numframes / samplerate
                device.state["paused"] = 10 < count["n"] <= 30   # blocks 11–30 = 2 s pause
                if count["n"] >= 40:
                    device.stop.set()
                return np.full((numframes, 1), 0.2, dtype=np.float32)

        yield Rec()


def test_pause_writes_nothing_and_pads_no_silence(tmp_path):
    clock, stop, state = FakeClock(), threading.Event(), {"paused": False}
    device = PausingDevice(clock, stop)
    device.state = state

    def paused_time():  # 2 s once the pause has passed, in between the running pause
        return min(max(clock.t - 1.1, 0.0), 2.0) if clock.t > 1.1 else 0.0

    track = Track("me", device, tmp_path / "me.wav", stop, t0=0.0, samplerate=SR, clock=clock,
                  paused=lambda: state["paused"], paused_time=paused_time)
    track.run()
    data, sr = sf.read(tmp_path / "me.wav")
    assert abs(len(data) / sr - 2.0) < 0.15           # 4 s wall time, 2 s paused → 2 s audio
    assert track.status.padded_frames == 0            # the pause is not padded with silence
    assert np.allclose(data, 0.2, atol=1e-3)
