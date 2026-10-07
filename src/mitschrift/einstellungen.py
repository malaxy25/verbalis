"""Einstellungen, gespeichert in ~/.mitschrift/einstellungen.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .transcription.modelle import STANDARD_MODELL, mitschrift_home

QUALITAET_BEAM = {"genau": 5, "schnell": 1}


@dataclass
class Einstellungen:
    name: str = "Ich"
    gegenueber: str = "Gegenüber"
    modell: str = STANDARD_MODELL
    qualitaet: str = "genau"          # "genau" (beam 5) oder "schnell" (beam 1)
    stichworte: str = ""
    aufnahme_ordner: str = ""         # leer = ~/.mitschrift/aufnahmen
    mikrofon: str = ""                # leer = Systemstandard
    lautsprecher: str = ""

    @property
    def ordner(self) -> Path:
        return Path(self.aufnahme_ordner).expanduser() if self.aufnahme_ordner else mitschrift_home() / "aufnahmen"

    @property
    def beam_size(self) -> int:
        return QUALITAET_BEAM.get(self.qualitaet, 5)

    @classmethod
    def pfad(cls) -> Path:
        return mitschrift_home() / "einstellungen.json"

    @classmethod
    def laden(cls) -> "Einstellungen":
        try:
            daten = json.loads(cls.pfad().read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()
        return cls.aus_dict(daten)

    @classmethod
    def aus_dict(cls, daten: dict) -> "Einstellungen":
        bekannt = {f.name for f in fields(cls)}
        werte = {k: str(v).strip() for k, v in daten.items() if k in bekannt and v is not None}
        e = cls(**werte)
        if e.qualitaet not in QUALITAET_BEAM:
            e.qualitaet = "genau"
        e.name = e.name or "Ich"
        e.gegenueber = e.gegenueber or "Gegenüber"
        e.modell = e.modell or STANDARD_MODELL
        return e

    def speichern(self) -> None:
        self.pfad().parent.mkdir(parents=True, exist_ok=True)
        self.pfad().write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def als_dict(self) -> dict:
        return {**asdict(self), "ordner": str(self.ordner)}
