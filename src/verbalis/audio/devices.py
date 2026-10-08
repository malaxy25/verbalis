"""Find audio devices: the microphone and the loopback source of the speakers.

Loopback means: we record what is played on a speaker/headset – i.e. the
voices of the others in a Teams call.

- Windows: WASAPI loopback, every speaker has a loopback "microphone" with the
  same ID.
- Linux (PipeWire/PulseAudio): every output has a monitor source with the ID
  "<speaker-id>.monitor".
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any


def soundcard_module():
    """Import soundcard lazily (on Linux it needs libpulse)."""
    import soundcard as sc

    # Windows often reports "data discontinuity" on short glitches – harmless.
    warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)
    return sc


@dataclass
class DeviceSelection:
    microphone: Any
    speakers: Any
    loopback: Any


def _pick(candidates: list, choice: str | None, default):
    """Pick a device by index ("2") or name part ("jabra"), else the default."""
    if not choice:
        return default
    if choice.isdigit():
        index = int(choice)
        if not 0 <= index < len(candidates):
            raise ValueError(f"Kein Gerät mit Index {index}.")
        return candidates[index]
    exact = [c for c in candidates if c.name == choice]
    if exact:
        return exact[0]
    matches = [c for c in candidates if choice.lower() in c.name.lower()]
    if not matches:
        raise ValueError(f"Kein Gerät gefunden, das '{choice}' im Namen enthält.")
    return matches[0]


def loopback_for(sc, speakers):
    """Find the loopback/monitor source of a speaker."""
    ids = {speakers.id, f"{speakers.id}.monitor"}
    for mic in sc.all_microphones(include_loopback=True):
        if mic.isloopback and mic.id in ids:
            return mic
    # Fallback: soundcard matches the name fuzzily.
    return sc.get_microphone(id=str(speakers.name), include_loopback=True)


def device_names() -> dict:
    """Device names for the UI."""
    sc = soundcard_module()
    return {
        "microphones": [m.name for m in sc.all_microphones()],
        "speakers": [s.name for s in sc.all_speakers()],
        "default_microphone": sc.default_microphone().name,
        "default_speakers": sc.default_speaker().name,
    }


def select(microphone: str | None = None, speakers: str | None = None) -> DeviceSelection:
    sc = soundcard_module()
    mic = _pick(sc.all_microphones(), microphone, sc.default_microphone())
    spk = _pick(sc.all_speakers(), speakers, sc.default_speaker())
    return DeviceSelection(microphone=mic, speakers=spk, loopback=loopback_for(sc, spk))


def print_devices() -> None:  # CLI output (German)
    sc = soundcard_module()
    default_mic = sc.default_microphone().name
    default_spk = sc.default_speaker().name

    print("Mikrofone (--microphone):")
    for i, m in enumerate(sc.all_microphones()):
        print(f"  [{i}] {m.name}{'   ← Standard' if m.name == default_mic else ''}")

    print("\nLautsprecher (--speakers, davon wird der Loopback aufgenommen):")
    for i, s in enumerate(sc.all_speakers()):
        print(f"  [{i}] {s.name}{'   ← Standard' if s.name == default_spk else ''}")

    print(
        "\nTipp: Wähle als Lautsprecher das Gerät, auf dem Teams den Ton ausgibt"
        "\n(Teams → Einstellungen → Geräte → Lautsprecher)."
    )
