"""Windows: record from devices whose format the soundcard library can't handle.

soundcard (mediafoundation.py) opens a WASAPI stream by taking the device's own
«mix format» and changing it to 32-bit float. It asserts that this mix format is
a WAVEFORMATEXTENSIBLE with float data – with offsets that are off by four bytes
(its struct isn't packed like Windows' WAVEFORMATEX), which is why its comment
calls the expected values «found empirically». Devices that report a plain format,
e.g. the Jabra Link 380 dongle in hands-free mode (16-bit PCM), fail that assertion
and can't be recorded at all.

This module wraps `_AudioClient.__init__`: if soundcard fails that way, the stream
is initialised with a format built here byte for byte (packed, 40 bytes, float32)
and the same stream flags soundcard uses – including AUTOCONVERTPCM, so Windows
converts sample rate, sample format and channels. Devices that work with soundcard
are untouched: the own path only runs after soundcard's assertion failed.
"""

from __future__ import annotations

import collections.abc
import logging
import struct

log = logging.getLogger(__name__)

# KSDATAFORMAT_SUBTYPE_IEEE_FLOAT {00000003-0000-0010-8000-00AA00389B71} as stored in memory
SUBTYPE_IEEE_FLOAT = struct.pack("<IHH8B", 0x00000003, 0x0000, 0x0010, 0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71)
WAVE_FORMAT_EXTENSIBLE = 0xFFFE
# Same as soundcard: resample | autoconvert PCM | better sample rate conversion | no persist
STREAM_FLAGS = 0x00100000 | 0x80000000 | 0x08000000 | 0x00080000
LOOPBACK = 0x00020000


def float_format(channels: int, samplerate: int) -> bytes:
    """WAVEFORMATEXTENSIBLE for 32-bit float, packed exactly like Windows expects (40 bytes)."""
    block_align = channels * 4
    mask = {1: 0x4, 2: 0x3}.get(channels, (1 << channels) - 1)   # mono: front centre, stereo: left|right
    head = struct.pack("<HHIIHHH", WAVE_FORMAT_EXTENSIBLE, channels, samplerate, samplerate * block_align,
                       block_align, 32, 22)                          # WAVEFORMATEX, cbSize = 22
    return head + struct.pack("<HI", 32, mask) + SUBTYPE_IEEE_FLOAT   # wValidBitsPerSample, dwChannelMask


def _init_with_own_format(mf, client, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode=False):
    """The part of soundcard's _AudioClient.__init__ after the failed assertion, with our format."""
    client._ptr = ptr
    if isinstance(channels, int):
        client.channelmap = list(range(channels))
    elif isinstance(channels, collections.abc.Iterable):
        client.channelmap = list(channels)
    else:
        raise TypeError("channels must be iterable or integer")
    if list(range(len(set(client.channelmap)))) != sorted(set(client.channelmap)):   # same check as soundcard
        raise TypeError("Due to limitations of WASAPI, channel maps on Windows must be a combination of range(0, x).")
    if blocksize is None:
        blocksize = client.deviceperiod[0] * samplerate
    count = len(set(client.channelmap))

    buffer = mf._ffi.new("char[]", float_format(count, int(samplerate)))   # stays alive during the call
    sharemode = mf._ole32.AUDCLNT_SHAREMODE_EXCLUSIVE if exclusive_mode else mf._ole32.AUDCLNT_SHAREMODE_SHARED
    flags = STREAM_FLAGS | (LOOPBACK if isloopback else 0)
    duration = int(blocksize / samplerate * 10_000_000)   # 100-ns units
    hr = ptr[0][0].lpVtbl.Initialize(ptr[0], sharemode, flags, duration, 0,
                                     mf._ffi.cast("WAVEFORMATEXTENSIBLE *", buffer), mf._ffi.NULL)
    mf._com.check_error(hr)
    client.samplerate = samplerate
    client._idle_start_time = None


def install(mf) -> bool:
    """Wrap soundcard's _AudioClient.__init__ once. `mf` is soundcard.mediafoundation."""
    original = mf._AudioClient.__init__
    if getattr(original, "_verbalis_fix", False):
        return False

    def __init__(self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode=False):
        try:
            return original(self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode)
        except AssertionError:
            log.warning("Device format not supported by soundcard – opening it with an own float32 format",
                        exc_info=True)
        _init_with_own_format(mf, self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode)

    __init__._verbalis_fix = True
    mf._AudioClient.__init__ = __init__
    return True
