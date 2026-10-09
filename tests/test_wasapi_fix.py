"""Windows workaround for devices soundcard can't open (e.g. Jabra Link 380) – with a fake WASAPI."""

import struct
from types import SimpleNamespace as NS

import pytest

from verbalis.audio import wasapi_fix


def test_float_format_is_packed_like_windows_expects():
    data = wasapi_fix.float_format(1, 48_000)
    assert len(data) == 40                                   # sizeof(WAVEFORMATEXTENSIBLE)
    tag, ch, rate, avg, align, bits, cb = struct.unpack_from("<HHIIHHH", data, 0)
    valid, mask = struct.unpack_from("<HI", data, 18)       # right after the 18-byte WAVEFORMATEX
    assert (tag, ch, rate, avg, align, bits, cb) == (0xFFFE, 1, 48_000, 192_000, 4, 32, 22)
    assert (valid, mask) == (32, 0x4)
    assert data[24:] == bytes.fromhex("0300000000001000800000aa00389b71")   # IEEE float GUID
    assert struct.unpack_from("<I", wasapi_fix.float_format(2, 48_000), 20)[0] == 0x3


class FakeWasapi:
    """Just enough of soundcard.mediafoundation for the wrapper."""

    def __init__(self, soundcard_fails):
        self.calls = []
        outer = self

        class AudioClient:
            def __init__(self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode=False):
                if soundcard_fails:
                    raise AssertionError()               # soundcard: assert wFormatTag == 0xFFFE
                self.opened_by = "soundcard"

        def initialize(this, sharemode, flags, duration, period, fmt, guid):
            outer.calls.append({"flags": flags, "duration": duration, "format": fmt})
            return 0

        self._AudioClient = AudioClient
        self._ffi = NS(new=lambda kind, data: bytes(data), cast=lambda kind, buf: buf, NULL=None)
        self._ole32 = NS(AUDCLNT_SHAREMODE_SHARED=0, AUDCLNT_SHAREMODE_EXCLUSIVE=1)
        self._com = NS(check_error=lambda hr: None if hr == 0 else (_ for _ in ()).throw(OSError(hr)))
        self.ptr = [[NS(lpVtbl=NS(Initialize=initialize))]]


def test_devices_that_work_are_left_to_soundcard():
    mf = FakeWasapi(soundcard_fails=False)
    assert wasapi_fix.install(mf) is True
    client = mf._AudioClient(mf.ptr, 48_000, 1, 4_800, False)
    assert client.opened_by == "soundcard" and mf.calls == []


def test_unsupported_device_is_opened_with_own_format():
    """Regression 0.7.13: «Mikrofon (Jabra Link 380)» failed soundcard's format assertion."""
    mf = FakeWasapi(soundcard_fails=True)
    wasapi_fix.install(mf)
    client = mf._AudioClient(mf.ptr, 48_000, 1, 4_800, False)
    assert client.channelmap == [0] and client.samplerate == 48_000
    call = mf.calls[0]
    assert call["format"] == wasapi_fix.float_format(1, 48_000)
    assert call["flags"] & 0x80000000                     # AUTOCONVERTPCM: Windows converts the format
    assert not call["flags"] & wasapi_fix.LOOPBACK
    assert call["duration"] == 1_000_000                   # 0.1 s in 100-ns units


def test_loopback_flag_and_stereo_for_system_audio():
    mf = FakeWasapi(soundcard_fails=True)
    wasapi_fix.install(mf)
    mf._AudioClient(mf.ptr, 48_000, 2, 4_800, True)
    assert mf.calls[0]["flags"] & wasapi_fix.LOOPBACK
    assert struct.unpack_from("<H", mf.calls[0]["format"], 2)[0] == 2


def test_install_only_once():
    mf = FakeWasapi(soundcard_fails=True)
    assert wasapi_fix.install(mf) is True
    assert wasapi_fix.install(mf) is False                 # no double wrapping
    with pytest.raises(TypeError):
        mf._AudioClient(mf.ptr, 48_000, "x", 4_800, False)  # same argument checks as soundcard
