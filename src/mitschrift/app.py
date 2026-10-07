"""Oberfläche: ein natives Fenster (pywebview) mit HTML-Oberfläche.

JavaScript ruft die Methoden von `Api` direkt auf (window.pywebview.api.…).
Jede Methode liefert {"ok": true, "daten": …} oder {"ok": false, "fehler": "…"},
damit die Oberfläche Fehler verständlich anzeigen kann.
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .dienst import Dienst

UI = Path(__file__).parent / "ui" / "index.html"


class Api:
    def __init__(self, dienst: Dienst):
        self._d = dienst  # Unterstrich: wird nicht an JavaScript weitergegeben

    def _rufe(self, fn, *args):
        try:
            return {"ok": True, "daten": fn(*args)}
        except Exception as e:
            return {"ok": False, "fehler": str(e) or repr(e)}

    def version(self):
        return {"ok": True, "daten": __version__}

    def zustand(self):
        return self._rufe(self._d.zustand)

    def einstellungen(self):
        return self._rufe(self._d.einstellungen)

    def einstellungen_speichern(self, daten):
        return self._rufe(self._d.einstellungen_speichern, daten)

    def geraete(self):
        return self._rufe(self._d.geraete)

    def modelle(self):
        return self._rufe(self._d.modelle)

    def aufnahme_starten(self, mikrofon, lautsprecher, einwilligung):
        return self._rufe(self._d.aufnahme_starten, mikrofon, lautsprecher, bool(einwilligung))

    def aufnahme_stoppen(self):
        return self._rufe(self._d.aufnahme_stoppen)

    def aufnahmen(self):
        return self._rufe(self._d.aufnahmen)

    def transkript(self, aufnahme_id):
        return self._rufe(self._d.transkript, aufnahme_id)

    def transkribieren(self, aufnahme_id):
        return self._rufe(self._d.transkribieren, aufnahme_id)

    def ordner_oeffnen(self, aufnahme_id=""):
        return self._rufe(self._d.ordner_oeffnen, aufnahme_id)


def starten() -> None:
    import webview

    dienst = Dienst()
    fenster = webview.create_window(
        "Mitschrift",
        html=UI.read_text(encoding="utf-8"),
        js_api=Api(dienst),
        width=1180,
        height=780,
        min_size=(860, 560),
        text_select=True,
        background_color="#EEF1F4",
    )
    fenster.events.closing += dienst.beenden  # laufende Aufnahme sauber speichern
    webview.start()
