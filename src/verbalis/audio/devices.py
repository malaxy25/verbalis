"""Find audio devices: the microphone and the loopback source of the speakers.

Loopback means: we record what is played on a speaker/headset – i.e. the
voices of the others in a Teams call.

- Windows: WASAPI loopback, every speaker has a loopback "microphone" with the
  same ID.
- Linux (PipeWire/PulseAudio): every output has a monitor source with the ID
  "<speaker-id>.monitor".
- macOS has no loopback. From macOS 14.2 the Swift helper records the system audio
  through a Core Audio tap (mac_tap.py) – the default, like loopback on Windows.
  On older Macs a virtual audio device (e.g. BlackHole) that Teams plays into can be
  recorded like a microphone; so on macOS the "speakers" choice lists input devices too.
"""

from __future__ import annotations

import sys
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


VIRTUAL_DEVICES = ("blackhole", "loopback", "soundflower", "vb-cable")
MAC_HINT = ("Für den Ton der anderen braucht dieser Mac macOS 14.2 oder neuer – oder ein virtuelles "
            "Audiogerät wie BlackHole, unter «Ton der anderen kommt über» gewählt. Anleitung im README.")


def _is_virtual(name: str) -> bool:
    return any(v in name.lower() for v in VIRTUAL_DEVICES)


NO_MICROPHONE = ("Es wurde kein Mikrofon gefunden. Headset oder Mikrofon anschliessen – und unter Windows "
                 "in den Einstellungen → Datenschutz und Sicherheit → Mikrofon den Zugriff für Desktop-Apps erlauben. "
                 "Danach «Geräte neu laden».")
NO_SPEAKERS = ("Es wurde kein Ausgabegerät gefunden. Lautsprecher oder Headset anschliessen und "
               "«Geräte neu laden».")


def _default(get, available: list):
    """The system's default device – or the first one, if Windows has none set.

    Windows answers «element not found» (0x80070490) when no default device
    exists, e.g. on a desktop PC without a microphone. That must not break the
    whole device list.
    """
    try:
        return get()
    except Exception:
        return available[0] if available else None


def device_names() -> dict:
    """Device names for the UI. Never fails because one kind of device is missing."""
    sc = soundcard_module()
    mic_list = sc.all_microphones()
    mics = [m.name for m in mic_list]
    default_mic = _default(sc.default_microphone, mic_list)
    problems = [] if mic_list else [NO_MICROPHONE]
    if sys.platform == "darwin":
        from . import mac_tap

        tap = mac_tap.available()
        virtual = [n for n in mics if _is_virtual(n)]
        default = mac_tap.SYSTEM_AUDIO if tap else (virtual[0] if virtual else "")
        return {"microphones": mics, "speakers": ([mac_tap.SYSTEM_AUDIO] if tap else []) + mics,
                "default_microphone": default_mic.name if default_mic else "", "default_speakers": default,
                "platform": "darwin", "virtual_device": tap or bool(virtual), "system_audio": tap,
                "problems": problems}
    speaker_list = sc.all_speakers()
    default_spk = _default(sc.default_speaker, speaker_list)
    if not speaker_list:
        problems.append(NO_SPEAKERS)
    return {
        "microphones": mics,
        "speakers": [s.name for s in speaker_list],
        "default_microphone": default_mic.name if default_mic else "",
        "default_speakers": default_spk.name if default_spk else "",
        "platform": sys.platform,
        "virtual_device": True,
        "problems": problems,
    }


def select(microphone: str | None = None, speakers: str | None = None) -> DeviceSelection:
    sc = soundcard_module()
    mic_list = sc.all_microphones()
    mic = _pick(mic_list, microphone, _default(sc.default_microphone, mic_list))
    if mic is None:
        raise ValueError(NO_MICROPHONE)
    if sys.platform == "darwin":
        from . import mac_tap

        if speakers in (None, "", mac_tap.SYSTEM_AUDIO):
            if mac_tap.available():
                tap = mac_tap.TapDevice()
                return DeviceSelection(microphone=mic, speakers=tap, loopback=tap)
            if speakers == mac_tap.SYSTEM_AUDIO:
                raise ValueError(MAC_HINT)
        inputs = sc.all_microphones()
        others = _pick(inputs, speakers, next((m for m in inputs if _is_virtual(m.name)), None))
        if others is None:
            raise ValueError(MAC_HINT)
        if others.name == mic.name:
            raise ValueError("Mikrofon und «Ton der anderen» sind dasselbe Gerät. Für den Ton der anderen "
                             "das virtuelle Audiogerät (z.B. BlackHole) wählen.")
        return DeviceSelection(microphone=mic, speakers=others, loopback=others)
    speaker_list = sc.all_speakers()
    spk = _pick(speaker_list, speakers, _default(sc.default_speaker, speaker_list))
    if spk is None:
        raise ValueError(NO_SPEAKERS)
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
