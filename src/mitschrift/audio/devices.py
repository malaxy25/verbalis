"""Audiogeräte finden: Mikrofon und die Loopback-Quelle des Lautsprechers.

Loopback heisst: wir nehmen auf, was über einen Lautsprecher/Kopfhörer
ausgegeben wird – also die Stimmen der anderen im Teams-Call.

- Windows: WASAPI-Loopback, jeder Lautsprecher hat ein Loopback-"Mikrofon"
  mit derselben ID.
- Linux (PipeWire/PulseAudio): jede Ausgabe hat eine Monitor-Quelle
  mit der ID "<lautsprecher-id>.monitor".
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any


def soundcard_modul():
    """soundcard erst bei Bedarf importieren (unter Linux braucht es libpulse)."""
    import soundcard as sc

    # Windows meldet bei kurzen Aussetzern oft "data discontinuity" – harmlos.
    warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)
    return sc


@dataclass
class GeraeteAuswahl:
    mikrofon: Any
    lautsprecher: Any
    loopback: Any


def _waehle(kandidaten: list, auswahl: str | None, standard):
    """Gerät per Index ("2") oder Namensteil ("jabra") wählen, sonst Standard."""
    if not auswahl:
        return standard
    if auswahl.isdigit():
        index = int(auswahl)
        if not 0 <= index < len(kandidaten):
            raise ValueError(f"Kein Gerät mit Index {index}.")
        return kandidaten[index]
    exakt = [k for k in kandidaten if k.name == auswahl]
    if exakt:
        return exakt[0]
    treffer = [k for k in kandidaten if auswahl.lower() in k.name.lower()]
    if not treffer:
        raise ValueError(f"Kein Gerät gefunden, das '{auswahl}' im Namen enthält.")
    return treffer[0]


def loopback_fuer(sc, lautsprecher):
    """Die Loopback-/Monitor-Quelle zu einem Lautsprecher finden."""
    passende_ids = {lautsprecher.id, f"{lautsprecher.id}.monitor"}
    for mic in sc.all_microphones(include_loopback=True):
        if mic.isloopback and mic.id in passende_ids:
            return mic
    # Rückfall: soundcard sucht unscharf nach dem Namen.
    return sc.get_microphone(id=str(lautsprecher.name), include_loopback=True)


def liste() -> dict:
    """Gerätenamen für die Oberfläche."""
    sc = soundcard_modul()
    return {
        "mikrofone": [m.name for m in sc.all_microphones()],
        "lautsprecher": [s.name for s in sc.all_speakers()],
        "standard_mikrofon": sc.default_microphone().name,
        "standard_lautsprecher": sc.default_speaker().name,
    }


def ermittle(mikrofon: str | None = None, lautsprecher: str | None = None) -> GeraeteAuswahl:
    sc = soundcard_modul()
    mic = _waehle(sc.all_microphones(), mikrofon, sc.default_microphone())
    spk = _waehle(sc.all_speakers(), lautsprecher, sc.default_speaker())
    return GeraeteAuswahl(mikrofon=mic, lautsprecher=spk, loopback=loopback_fuer(sc, spk))


def liste_ausgeben() -> None:
    sc = soundcard_modul()
    std_mic = sc.default_microphone().name
    std_spk = sc.default_speaker().name

    print("Mikrofone (--mikrofon):")
    for i, m in enumerate(sc.all_microphones()):
        print(f"  [{i}] {m.name}{'   ← Standard' if m.name == std_mic else ''}")

    print("\nLautsprecher (--lautsprecher, davon wird der Loopback aufgenommen):")
    for i, s in enumerate(sc.all_speakers()):
        print(f"  [{i}] {s.name}{'   ← Standard' if s.name == std_spk else ''}")

    print(
        "\nTipp: Wähle als Lautsprecher das Gerät, auf dem Teams den Ton ausgibt"
        "\n(Teams → Einstellungen → Geräte → Lautsprecher)."
    )
