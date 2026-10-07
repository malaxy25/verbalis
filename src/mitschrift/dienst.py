"""Die Logik hinter der Oberfläche – unabhängig vom Fenster.

Die Oberfläche fragt regelmässig `zustand()` ab und ruft Aktionen auf.
Transkriptionen laufen nacheinander in einem Hintergrund-Thread, damit
Aufnahme und Bedienung nie blockieren. Das geladene Modell bleibt im
Speicher, solange sich die Einstellung nicht ändert (Laden dauert ~15 s).

Pausieren: Der Thread hält nach jedem fertigen Textabschnitt an, solange
manuell pausiert ist oder eine Aufnahme läuft (sonst konkurrieren beide um
die CPU, was Aussetzer in der Aufnahme verursachen kann).
"""

from __future__ import annotations

import json
import logging
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
from .korrekturen import Korrekturliste, vorschlaege
from .transcription.base import Segment
from .transkript import als_markdown
from .transcription.modelle import mitschrift_home

GUELTIGE_ID = re.compile(r"^[\w\-]+$")
log = logging.getLogger(__name__)


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
        self._pause_manuell = False

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

    # ------------------------------------------------------------ Pause

    def _pausengrund(self) -> str | None:
        if self._pause_manuell:
            return "manuell"
        if self._rec is not None:
            return "aufnahme"
        return None

    def pausieren(self) -> None:
        with self._lock:
            self._pause_manuell = True

    def fortsetzen(self) -> None:
        with self._lock:
            self._pause_manuell = False

    def _warten_falls_pausiert(self) -> None:
        """Im Worker-Thread aufrufen: blockiert, solange pausiert ist."""
        beginn = None
        while True:
            with self._lock:
                if self._pausengrund() is None:
                    if beginn is not None and self._job:
                        self._job["pausiert_s"] += time.monotonic() - beginn
                        self._job["pause_seit"] = None
                    return
                if beginn is None:
                    beginn = time.monotonic()
                    if self._job:
                        self._job["pause_seit"] = beginn
            time.sleep(0.1)

    # ------------------------------------------------------------ Restdauer

    @staticmethod
    def _statistik_pfad() -> Path:
        return mitschrift_home() / "statistik.json"

    def _faktor(self, schluessel: str) -> float | None:
        try:
            return json.loads(self._statistik_pfad().read_text(encoding="utf-8"))["echtzeitfaktor"].get(schluessel)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    def _faktor_merken(self, schluessel: str, faktor: float) -> None:
        pfad = self._statistik_pfad()
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            daten = {}
        faktoren = daten.setdefault("echtzeitfaktor", {})
        alt = faktoren.get(schluessel)
        faktoren[schluessel] = round(faktor if alt is None else (alt + faktor) / 2, 3)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps(daten, indent=2), encoding="utf-8")

    def _restdauer(self, job: dict) -> float | None:
        if job["start"] is None:
            return None
        jetzt = job["pause_seit"] or time.monotonic()
        aktiv = max(jetzt - job["start"] - job["pausiert_s"], 0.0)
        anteil = job["anteil"]
        if anteil >= 0.1 and aktiv >= 10:
            return aktiv * (1 - anteil) / anteil
        if job["faktor"] and job["dauer_s"]:
            rest = job["faktor"] * job["dauer_s"] - aktiv
            return rest if rest > 0 else None
        return None

    # ------------------------------------------------------------ Worker

    def _arbeiten(self) -> None:
        while True:
            aufnahme_id = self._warteschlange.get()
            if aufnahme_id is None:
                return
            self._warten_falls_pausiert()
            with self._lock:
                if aufnahme_id in self._wartend:
                    self._wartend.remove(aufnahme_id)
                e = self._e
                schluessel = f"{e.modell}|beam{e.beam_size}"
                self._job = {
                    "id": aufnahme_id, "phase": f"Modell {e.modell} wird geladen", "anteil": 0.0,
                    "start": None, "pausiert_s": 0.0, "pause_seit": None,
                    "dauer_s": ablauf.meta_lesen(self._pfad(aufnahme_id)).get("dauer_s"),
                    "faktor": self._faktor(schluessel),
                }
            try:
                tr = self._modell_holen(e.modell)
                tr.beam_size = e.beam_size
                korrekturen = Korrekturliste.laden()
                tr.stichworte = self._stichworte(e.stichworte, korrekturen) or None
                namen = {"ich": e.name, "gegenueber": e.gegenueber}
                reihenfolge = list(namen.values())
                with self._lock:
                    self._job["start"] = time.monotonic()
                    self._job["phase"] = "Transkription beginnt"

                def fortschritt(name: str, anteil: float):
                    index = reihenfolge.index(name) if name in reihenfolge else 0
                    with self._lock:
                        if self._job:
                            self._job["phase"] = f"Spur «{name}» wird transkribiert"
                            self._job["anteil"] = (index + anteil) / len(reihenfolge)
                    self._warten_falls_pausiert()

                def pausenzeit() -> float:
                    with self._lock:
                        return self._job["pausiert_s"] if self._job else 0.0

                _, rechenzeit, dauer = ablauf.transkript_erstellen(
                    self._pfad(aufnahme_id), tr, e.modell, namen, fortschritt, pausenzeit, korrekturen)
                if dauer > 0 and rechenzeit > 0:
                    self._faktor_merken(schluessel, rechenzeit / dauer)
            except Exception as ex:  # Fehler pro Aufnahme anzeigen, Worker läuft weiter
                log.exception("Transkription von %s fehlgeschlagen", aufnahme_id)
                with self._lock:
                    self._fehler[aufnahme_id] = str(ex) or repr(ex)
            finally:
                with self._lock:
                    self._job = None

    # ------------------------------------------------------------ Korrekturen

    @staticmethod
    def _stichworte(eigene: str, korrekturen: Korrekturliste) -> str:
        """Eigene Stichworte plus alle Korrektur-Ziele, ohne Doppelte."""
        woerter: list[str] = []
        for w in [*eigene.split(","), *korrekturen.ziele()]:
            w = w.strip()
            if w and w.lower() not in (x.lower() for x in woerter):
                woerter.append(w)
        return ", ".join(woerter)

    def _transkript_schreiben(self, ordner: Path, daten: dict) -> None:
        daten.pop("markdown", None)
        (ordner / "transkript.json").write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")
        absaetze = [Segment(s["start"], s["ende"], s["text"], s.get("sprecher")) for s in daten["segmente"]]
        (ordner / "transkript.md").write_text(
            als_markdown(absaetze, daten.get("titel") or f"Transkript {ordner.name}", daten.get("kopf", {})),
            encoding="utf-8")

    def transkript_bearbeiten(self, aufnahme_id: str, index: int, text: str) -> dict:
        """Einen Absatz ändern. Gibt Vorschläge für die Korrekturliste zurück."""
        ordner = self._pfad(aufnahme_id)
        daten = json.loads((ordner / "transkript.json").read_text(encoding="utf-8"))
        segmente = daten["segmente"]
        if not 0 <= index < len(segmente):
            raise ValueError("Diesen Absatz gibt es nicht (mehr).")
        text = " ".join(text.split())
        if not text:
            raise ValueError("Ein Absatz darf nicht leer sein.")
        alt = segmente[index]["text"]
        if text == alt:
            return {"vorschlaege": []}

        original = ordner / "transkript_original.json"
        if not original.exists():  # unbearbeitete Fassung einmalig sichern
            original.write_text((ordner / "transkript.json").read_text(encoding="utf-8"), encoding="utf-8")
        segmente[index]["text"] = text
        daten["bearbeitet"] = True
        self._transkript_schreiben(ordner, daten)

        liste = Korrekturliste.laden()
        vorschlag_liste = [liste.einordnen(v, z) for v, z in vorschlaege(alt, text)]
        return {"vorschlaege": [v for v in vorschlag_liste if v["art"] != "bekannt"]}

    def korrekturen_merken(self, aufnahme_id: str, regeln: list[dict]) -> dict:
        """Ausgewählte Vorschläge speichern und gleich im ganzen Transkript anwenden."""
        liste = Korrekturliste.laden()
        neu = Korrekturliste()
        for r in regeln:
            info = liste.hinzufuegen(r["variante"], r["ziel"])
            if info["art"] != "ignoriert":
                neu.hinzufuegen(r["variante"], info["ziel"])
        liste.speichern()

        ersetzt = 0
        if aufnahme_id:
            ordner = self._pfad(aufnahme_id)
            daten = json.loads((ordner / "transkript.json").read_text(encoding="utf-8"))
            for s in daten["segmente"]:
                s["text"], n = neu.anwenden(s["text"])
                ersetzt += n
            if ersetzt:
                daten["bearbeitet"] = True
                self._transkript_schreiben(ordner, daten)
        return {"gemerkt": sum(len(v) for v in neu.regeln.values()), "ersetzt": ersetzt}

    def korrekturen(self) -> list[dict]:
        return Korrekturliste.laden().als_liste()

    def korrektur_entfernen(self, ziel: str, variante: str | None = None) -> list[dict]:
        liste = Korrekturliste.laden()
        liste.entfernen(ziel, variante)
        liste.speichern()
        return liste.als_liste()

    # ------------------------------------------------------------ Verlauf

    def _pfad(self, aufnahme_id: str) -> Path:
        if not GUELTIGE_ID.match(aufnahme_id or ""):
            raise ValueError(f"Ungültige Aufnahme: {aufnahme_id!r}")
        return self._e.ordner / aufnahme_id

    def _status(self, aufnahme_id: str, ordner: Path) -> str:
        if self._rec_info.get("id") == aufnahme_id:
            return "aufnahme"
        if self._job and self._job["id"] == aufnahme_id:
            return "pausiert" if self._pausengrund() and self._job["start"] is not None else "laeuft"
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
            job = None
            if self._job:
                rest = self._restdauer(self._job)
                job = {"id": self._job["id"], "phase": self._job["phase"], "anteil": self._job["anteil"],
                       "rest_s": round(rest) if rest is not None else None}
            wartend = list(self._wartend)
            pause = self._pausengrund()
        if rec is not None and aufnahme is None:
            self.aufnahme_stoppen()
        return {"aufnahme": aufnahme, "job": job, "wartend": wartend, "pause": pause,
                "aufnahme_fehler": self._aufnahme_fehler}

    def beenden(self) -> None:
        """Beim Schliessen des Fensters: laufende Aufnahme sauber speichern."""
        if self._rec is not None:
            rec, info = self._rec, self._rec_info
            rec.stoppen()
            self._rec, self._rec_info = None, {}
            ablauf.meta_schreiben(info["ordner"], info["start"], time.monotonic() - rec.t0, rec.samplerate,
                                  info["einwilligung"], info["geraete"], rec.status())
        self._warteschlange.put(None)
