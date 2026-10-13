"""Two-track recorder: padding dropouts with silence, pausing without padding."""

import threading
import time
from contextlib import contextmanager

import numpy as np
import pytest
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
    def recorder(self, samplerate, blocksize=None):
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
    def recorder(self, samplerate, blocksize=None):
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


class UnreadableFormatDevice:
    """Like some Bluetooth/USB devices on Windows: soundcard asserts on the device format
    unless the channel count is given explicitly."""

    name = "Headset (Freisprechen)"

    def __init__(self, clock, stop, works_with_channels=True):
        self.clock, self.stop, self.works = clock, stop, works_with_channels
        self.asked = []

    def recorder(self, samplerate, blocksize=None, channels=None):
        self.asked.append(channels)
        if channels is None or not self.works:
            raise AssertionError()      # soundcard: assert blob.cbSize == 40
        device = self

        @contextmanager
        def ctx():
            class Rec:
                def record(self, numframes):
                    device.clock.t += numframes / samplerate
                    if device.clock.t >= 1.0:
                        device.stop.set()
                    return np.full((numframes, channels), 0.2, dtype=np.float32)
            yield Rec()
        return ctx()


def test_device_with_unreadable_format_records_with_fixed_channels(tmp_path):
    """Regression 0.7.12: «AssertionError» from soundcard stopped the recording at once."""
    clock, stop = FakeClock(), threading.Event()
    device = UnreadableFormatDevice(clock, stop)
    track = Track("others", device, tmp_path / "others.wav", stop, t0=0.0, samplerate=SR, clock=clock)
    track.run()
    assert track.status.error is None
    assert device.asked == [None, 2]                     # tried the normal way, then stereo
    data, sr = sf.read(tmp_path / "others.wav")
    assert abs(len(data) / sr - 1.0) < 0.15 and np.allclose(data, 0.2, atol=1e-3)


def test_device_that_cannot_record_explains_why(tmp_path):
    clock, stop = FakeClock(), threading.Event()
    device = UnreadableFormatDevice(clock, stop, works_with_channels=False)
    track = Track("me", device, tmp_path / "me.wav", stop, t0=0.0, samplerate=SR, clock=clock)
    track.run()
    assert isinstance(track.status.error, RuntimeError)
    assert "anderes Gerät" in str(track.status.error) and "Headset (Freisprechen)" in str(track.status.error)
    assert device.asked == [None, 1]                     # microphone retried in mono


def test_level_monitor_measures_without_writing(tmp_path, monkeypatch):
    """0.7.17: levels before recording – the meter tracks read the devices but create no file."""
    from verbalis.audio.recorder import LevelMonitor
    monkeypatch.chdir(tmp_path)

    class Endless:
        name = "Mic"

        @contextmanager
        def recorder(self, samplerate, blocksize=None):
            class Rec:
                def record(self, numframes):
                    time.sleep(0.01)
                    return np.full((numframes, 1), 0.1, dtype=np.float32)
            yield Rec()

    class Broken:
        name = "Kaputt"

        def recorder(self, samplerate, blocksize=None):
            raise OSError("Gerät belegt")

    monitor = LevelMonitor(Endless(), Broken(), samplerate=SR)
    monitor.start()
    deadline = time.monotonic() + 3
    while monitor.levels()["me"] == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    levels = monitor.levels()
    assert abs(levels["me"] - 0.1) < 1e-3 and levels["others"] == 0.0   # one broken device doesn't stop the other
    monitor.stop()
    assert not any(t.is_alive() for t in monitor.tracks)
    assert list(tmp_path.iterdir()) == []


class MacDevice:
    """Like soundcard on macOS: the block size is the hardware buffer and must be ≤ 512 frames."""
    name = "MacBook Air-Mikrofon"

    def __init__(self, clock, stop):
        self.clock, self.stop = clock, stop

    def recorder(self, samplerate, channels=None, blocksize=None):
        if blocksize is not None and not 15 <= blocksize <= 512:
            raise TypeError("blocksize must be between 15.0 and 512")
        device = self

        @contextmanager
        def ctx():
            class Rec:
                def record(self, numframes):
                    device.clock.t += numframes / samplerate
                    if device.clock.t >= 1.0:
                        device.stop.set()
                    return np.full((numframes, 1), 0.2, dtype=np.float32)
            yield Rec()
        return ctx()


def test_macos_records_without_a_block_size(tmp_path, monkeypatch):
    """0.7.20 bug on macOS: «blocksize must be between 15.0 and 512» – every recording failed at once."""
    from verbalis.audio import recorder
    monkeypatch.setattr(recorder.sys, "platform", "darwin")
    clock, stop = FakeClock(), threading.Event()
    track = Track("me", MacDevice(clock, stop), tmp_path / "me.wav", stop, t0=0.0, samplerate=SR, clock=clock)
    track.run()
    assert track.status.error is None
    data, sr = sf.read(tmp_path / "me.wav")
    assert abs(len(data) / sr - 1.0) < 0.15 and np.allclose(data, 0.2, atol=1e-3)


class CoreAudioLikeRecorder:
    """Like soundcard's macOS recorder: blocks arrive in `_queue` with `_record_event`; record() waits forever."""

    def __init__(self, blocks):
        import collections
        self._queue = collections.deque()
        self._record_event = threading.Event()
        self._pending = np.zeros((0, 1), dtype=np.float32)

        def feed():
            for n in blocks:
                time.sleep(0.01)
                self._queue.append(np.full((n, 1), 0.3, dtype=np.float32))
                self._record_event.set()
        threading.Thread(target=feed, daemon=True).start()

    def record(self, numframes=None):
        assert numframes is None              # Verbalis asks for what's there, after waiting itself
        while not self._queue:
            self._record_event.wait()          # soundcard: no time limit
            self._record_event.clear()
        return self._queue.popleft()


def test_reader_gives_exact_blocks_and_never_waits_forever(monkeypatch):
    """0.7.22 on macOS: devices that delivered nothing made the recording hang («stop_timeout»)."""
    from verbalis.audio import recorder
    monkeypatch.setattr(recorder, "READ_TIMEOUT_S", 0.3)
    reader = recorder._Reader(CoreAudioLikeRecorder([512] * 20), "MacBook Air-Mikrofon")
    blocks = [reader.read(1000) for _ in range(10)]
    assert all(b.shape == (1000, 1) for b in blocks)        # exact sizes from 512-frame chunks
    started = time.monotonic()
    with pytest.raises(recorder.NoAudioData, match="MacBook Air-Mikrofon"):
        reader.read(1000)                                     # only 240 frames left, then nothing
    assert time.monotonic() - started < 2


def test_silent_device_ends_the_track_instead_of_hanging(tmp_path, monkeypatch):
    from verbalis.audio import recorder
    monkeypatch.setattr(recorder, "READ_TIMEOUT_S", 0.3)

    class Silent:
        name = "Stummes Gerät"

        @contextmanager
        def recorder(self, samplerate, blocksize=None, channels=None):
            yield CoreAudioLikeRecorder([])

    stop = threading.Event()
    track = Track("me", Silent(), tmp_path / "me.wav", stop, t0=time.monotonic())
    track.start()
    track.join(3)
    assert not track.is_alive() and isinstance(track.status.error, recorder.NoAudioData)
    assert stop.is_set()                                      # the other track stops too


def test_measure_tells_a_working_from_a_silent_device(monkeypatch):
    """Diagnosis: which device delivers, how loud, and whether it can be closed."""
    from verbalis.audio import recorder
    monkeypatch.setattr(recorder, "READ_TIMEOUT_S", 0.3)

    class Device:
        def __init__(self, name, blocks):
            self.name, self.blocks = name, blocks

        @contextmanager
        def recorder(self, samplerate, blocksize=None, channels=None):
            yield CoreAudioLikeRecorder(self.blocks)

    good, silent = recorder.measure([("me", Device("Mikro", [512] * 400)), ("others", Device("Systemton", []))], 1.0)
    assert good["device"] == "Mikro" and good["first_data_s"] is not None and good["received_s"] > 0
    assert -20 < good["peak_db"] < -5 and not good["hangs"] and good["error"] is None
    assert silent["first_data_s"] is None and "keine Audiodaten" in silent["error"]
