"""Die Logik hinter der Oberfläche – unabhängig vom Fenster.

Die Oberfläche fragt regelmässig `zustand()` ab und ruft Aktionen auf.
Transkriptionen laufen nacheinander in einem Hintergrund-Thread, damit
Aufnahme und Bedienung nie blockieren. Das geladene Modell bleibt im
Speicher, solange sich die Einstellung nicht ändert (Laden dauert ~15 s).
"""

from __future__ import annotations

import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import ablauf
from .einstellungen import Einstellungen

GUELTIGE_ID = re.compile(r"^[\w\-]+$")


def _db(rms: float) -> float:
    return round(max(20 * math.log10(rms), -90.0), 1) if rms > 1e-9 else -90.0


def ordner_oeffnen(pfad: Path) -> None:
    if sys.platform == "win32":
        os.startfile(pfad)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(pfad)])
    else:
        subprocess.Popen(["xdg-open", str(pfad)])


class Dienst:
    def __init__(
        self,
        einstellungen: Einstellungen | None = None,
        recorder_fabrik: Callable | None = None,
        transcriber_fabrik: Callable | None = None,
        geraete_ermitteln: Callable | None = None,
        geraete_liste: Callable | None = None,
    ):
        self._lock = threading.RLock()
        self._e = einstellungen or Einstellungen.laden()
        self._recorder_fabrik = recorder_fabrik or self._standard_recorder
        self._transcriber_fabrik = transcriber_fabrik or self._standard_transcriber
        self._geraete_ermitteln = geraete_ermitteln or self._standard_ermitteln
        self._geraete_liste = geraete_liste or self._standard_liste

        self._rec = None
        self._rec_info: dict = {}
        self._aufnahme_fehler: str | None = None

        self._warteschlange: queue.Queue[str | None] = queue.Queue()
        self._wartend: list[str] = []
        self._job: dict | None = None
        self._fehler: dict[str, str] = {}
        self._transcriber = None
        self._transcriber_modell: str | None = None

        self._worker = threading.Thread(target=self._arbeiten, name="transkription", daemon=True)
        self._worker.start()

    # ------------------------------------------------------------ Standard-Bausteine

    @staticmethod
    def _standard_recorder(mikrofon, loopback, ordner):
        from .audio.recorder import ZweiSpurRecorder

        return ZweiSpurRecorder(mikrofon, loopback, ordner)

    @staticmethod
    def _standard_transcriber(modell: str):
        from .transcription.faster import FasterWhisperTranscriber

        return FasterWhisperTranscriber(modell)

    @staticmethod
    def _standard_ermitteln(mikrofon, lautsprecher):
        from .audio.devices import ermittle

        return ermittle(mikrofon, lautsprecher)

    @staticmethod
    def _standard_liste():
        from .audio.devices import liste

        return liste()

    # ------------------------------------------------------------ Einstellungen & Geräte

    def einstellungen(self) -> dict:
        return self._e.als_dict()

    def einstellungen_speichern(self, daten: dict) -> dict:
        with self._lock:
            neu = Einstellungen.aus_dict({**self._e.als_dict(), **daten})
            neu.speichern()
            self._e = neu
        return self._e.als_dict()

    def geraete(self) -> dict:
        return self._geraete_liste()

    def modelle(self) -> list[dict]:
        from .transcription.modelle import EMPFOHLEN, eingebaute_modelle, konvertierte_modelle

        konvertiert = set(konvertierte_modelle())
        eingebaut = set(eingebaute_modelle())
        ergebnis = []
        for modell, beschreibung in EMPFOHLEN:
            if modell in konvertiert:
                status = "bereit"
            elif modell in eingebaut:
                status = "wird beim ersten Gebrauch heruntergeladen"
            else:
                status = f"noch nicht konvertiert – im Terminal: mitschrift modell-konvertieren {modell}"
            ergebnis.append({"id": modell, "beschreibung": beschreibung, "status": status})
        for modell in sorted(konvertiert - {m for m, _ in EMPFOHLEN}):
            ergebnis.append({"id": modell, "beschreibung": "selbst konvertiert", "status": "bereit"})
        return ergebnis

    # ------------------------------------------------------------ Aufnahme

    def aufnahme_starten(self, mikrofon: str = "", lautsprecher: str = "", einwilligung: bool = False) -> str:
        with self._lock:
            if self._rec is not None:
                raise RuntimeError("Es läuft bereits eine Aufnahme.")
            if not einwilligung:
                raise RuntimeError("Bitte zuerst bestätigen, dass alle Teilnehmenden der Aufnahme zugestimmt haben.")

            geraete = self._geraete_ermitteln(mikrofon or None, lautsprecher or None)
            start = datetime.now().astimezone()
            ordner = self._e.ordner / start.strftime("%Y-%m-%d_%H%M%S")
            rec = self._recorder_fabrik(geraete.mikrofon, geraete.loopback, ordner)
            rec.start()

            self._rec = rec
            self._aufnahme_fehler = None
            self._rec_info = {
                "id": ordner.name,
                "ordner": ordner,
                "start": start,
                "einwilligung": datetime.now().astimezone().isoformat(timespec="seconds"),
                "geraete": {"ich": geraete.mikrofon.name, "gegenueber": geraete.loopback.name},
            }
            # Gewählte Geräte für das nächste Mal merken
            if (mikrofon, lautsprecher) != (self._e.mikrofon, self._e.lautsprecher):
                self.einstellungen_speichern({"mikrofon": mikrofon, "lautsprecher": lautsprecher})
            return ordner.name

    def aufnahme_stoppen(self) -> str | None:
        with self._lock:
            rec, info = self._rec, self._rec_info
            if rec is None:
                return None
            rec.stoppen()
            self._rec, self._rec_info = None, {}

        fehler = [repr(f) for f in rec.fehler]
        if fehler:
            self._aufnahme_fehler = "Die Aufnahme wurde wegen eines Gerätefehlers abgebrochen: " + "; ".join(fehler)
        dauer = time.monotonic() - rec.t0
        ablauf.meta_schreiben(info["ordner"], info["start"], dauer, rec.samplerate,
                              info["einwilligung"], info["geraete"], rec.status())
        if dauer >= 1:
            self.transkribieren(info["id"])
        return info["id"]

    # ------------------------------------------------------------ Transkription

    def transkribieren(self, aufnahme_id: str) -> None:
        self._pfad(aufnahme_id)  # prüft die ID
        with self._lock:
            if aufnahme_id in self._wartend or (self._job and self._job["id"] == aufnahme_id):
                return
            self._fehler.pop(aufnahme_id, None)
            self._wartend.append(aufnahme_id)
        self._warteschlange.put(aufnahme_id)

    def _modell_holen(self, modell: str):
        if self._transcriber is None or self._transcriber_modell != modell:
            self._transcriber = None  # alten Speicher zuerst freigeben
            self._transcriber = self._transcriber_fabrik(modell)
            self._transcriber_modell = modell
        return self._transcriber

    def _arbeiten(self) -> None:
        while True:
            aufnahme_id = self._warteschlange.get()
            if aufnahme_id is None:
                return
            with self._lock:
                if aufnahme_id in self._wartend:
                    self._wartend.remove(aufnahme_id)
                e = self._e
                self._job = {"id": aufnahme_id, "phase": f"Modell {e.modell} wird geladen", "anteil": 0.0}
            try:
                tr = self._modell_holen(e.modell)
                tr.beam_size = e.beam_size
                tr.stichworte = e.stichworte or None
                namen = {"ich": e.name, "gegenueber": e.gegenueber}
                reihenfolge = list(namen.values())

                def fortschritt(name: str, anteil: float):
                    index = reihenfolge.index(name) if name in reihenfolge else 0
                    with self._lock:
                        if self._job:
                            self._job["phase"] = f"Spur «{name}» wird transkribiert"
                            self._job["anteil"] = (index + anteil) / len(reihenfolge)

                ablauf.transkript_erstellen(self._pfad(aufnahme_id), tr, e.modell, namen, fortschritt)
            except Exception as ex:  # Fehler pro Aufnahme anzeigen, Worker läuft weiter
                with self._lock:
                    self._fehler[aufnahme_id] = str(ex) or repr(ex)
            finally:
                with self._lock:
                    self._job = None

    # ------------------------------------------------------------ Verlauf

    def _pfad(self, aufnahme_id: str) -> Path:
        if not GUELTIGE_ID.match(aufnahme_id or ""):
            raise ValueError(f"Ungültige Aufnahme: {aufnahme_id!r}")
        return self._e.ordner / aufnahme_id

    def _status(self, aufnahme_id: str, ordner: Path) -> str:
        if self._rec_info.get("id") == aufnahme_id:
            return "aufnahme"
        if self._job and self._job["id"] == aufnahme_id:
            return "laeuft"
        if aufnahme_id in self._wartend:
            return "wartet"
        if aufnahme_id in self._fehler:
            return "fehler"
        return "fertig" if (ordner / "transkript.json").exists() else "ohne"

    def aufnahmen(self) -> list[dict]:
        basis = self._e.ordner
        if not basis.exists():
            return []
        ergebnis = []
        with self._lock:
            for ordner in sorted(basis.iterdir(), reverse=True):
                if not ordner.is_dir() or not GUELTIGE_ID.match(ordner.name):
                    continue
                aufnahme = self._rec_info.get("id") == ordner.name
                if not aufnahme and not ablauf.ist_aufnahmeordner(ordner):
                    continue
                meta = ablauf.meta_lesen(ordner)
                ergebnis.append({
                    "id": ordner.name,
                    "start": meta.get("start") or ordner.name,
                    "dauer_s": meta.get("dauer_s"),
                    "status": self._status(ordner.name, ordner),
                    "fehler": self._fehler.get(ordner.name),
                })
        return ergebnis

    def transkript(self, aufnahme_id: str) -> dict | None:
        ordner = self._pfad(aufnahme_id)
        try:
            daten = json.loads((ordner / "transkript.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        md = ordner / "transkript.md"
        daten["markdown"] = md.read_text(encoding="utf-8") if md.exists() else ""
        return daten

    def ordner_oeffnen(self, aufnahme_id: str = "") -> None:
        pfad = self._pfad(aufnahme_id) if aufnahme_id else self._e.ordner
        pfad.mkdir(parents=True, exist_ok=True)
        ordner_oeffnen(pfad)

    # ------------------------------------------------------------ Abfrage für die Oberfläche

    def zustand(self) -> dict:
        with self._lock:
            rec, info = self._rec, self._rec_info
            aufnahme = None
            if rec is not None:
                if not rec.laeuft:  # Spur hat wegen eines Fehlers gestoppt
                    pass
                else:
                    ich, gegenueber = rec.status()
                    aufnahme = {
                        "id": info["id"],
                        "dauer_s": round(time.monotonic() - rec.t0, 1),
                        "pegel": {"ich": _db(ich.pegel_rms), "gegenueber": _db(gegenueber.pegel_rms)},
                    }
            job = dict(self._job) if self._job else None
            wartend = list(self._wartend)
        if rec is not None and aufnahme is None:
            self.aufnahme_stoppen()
        return {"aufnahme": aufnahme, "job": job, "wartend": wartend, "aufnahme_fehler": self._aufnahme_fehler}

    def beenden(self) -> None:
        """Beim Schliessen des Fensters: laufende Aufnahme sauber speichern."""
        if self._rec is not None:
            rec, info = self._rec, self._rec_info
            rec.stoppen()
            self._rec, self._rec_info = None, {}
            ablauf.meta_schreiben(info["ordner"], info["start"], time.monotonic() - rec.t0, rec.samplerate,
                                  info["einwilligung"], info["geraete"], rec.status())
        self._warteschlange.put(None)
