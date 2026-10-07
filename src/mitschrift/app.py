"""Oberfläche: ein natives Fenster (pywebview) mit HTML-Oberfläche.

JavaScript ruft die Methoden von `Api` direkt auf (window.pywebview.api.…).
Jede Methode liefert {"ok": true, "daten": …} oder {"ok": false, "fehler": "…"},
damit die Oberfläche Fehler verständlich anzeigen kann.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path

from . import __version__
from .dienst import Dienst
from .transcription.modelle import mitschrift_home

UI = Path(__file__).parent / "ui" / "index.html"
ICON = Path(__file__).parent / "ui" / "mitschrift.ico"
log = logging.getLogger("mitschrift")
_MUTEX = None  # hält die Windows-Sperre gegen doppeltes Öffnen


class Api:
    def __init__(self, dienst: Dienst):
        self._d = dienst  # Unterstrich: wird nicht an JavaScript weitergegeben

    def _rufe(self, fn, *args):
        try:
            return {"ok": True, "daten": fn(*args)}
        except Exception as e:
            log.exception("Fehler in %s", getattr(fn, "__name__", fn))
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

    def pausieren(self):
        return self._rufe(self._d.pausieren)

    def fortsetzen(self):
        return self._rufe(self._d.fortsetzen)

    def transkript_bearbeiten(self, aufnahme_id, index, text):
        return self._rufe(self._d.transkript_bearbeiten, aufnahme_id, int(index), text)

    def korrekturen_merken(self, aufnahme_id, regeln):
        return self._rufe(self._d.korrekturen_merken, aufnahme_id, regeln)

    def korrekturen(self):
        return self._rufe(self._d.korrekturen)

    def korrektur_entfernen(self, ziel, variante=None):
        return self._rufe(self._d.korrektur_entfernen, ziel, variante)

    def audio_speicher(self):
        return self._rufe(self._d.audio_speicher)

    def audio_jetzt_loeschen(self, aufnahme_id):
        return self._rufe(self._d.audio_jetzt_loeschen, aufnahme_id)

    def ordner_oeffnen(self, aufnahme_id=""):
        return self._rufe(self._d.ordner_oeffnen, aufnahme_id)


STANDARD_GROESSE = (1180, 780)
MIN_GROESSE = (860, 560)


def fenstergroesse(gemerkt: str = "", bildschirm=None) -> tuple[int, int]:
    """Gemerkte oder Standardgrösse, aber nie grösser als der Bildschirm.

    Vom Bildschirm ziehen wir Platz für Taskleiste und Titelleiste ab. Alle
    Werte sind logische Pixel – bei 150 % Skalierung hat ein Full-HD-Bildschirm
    also 1280 × 720.
    """
    breite, hoehe = STANDARD_GROESSE
    try:
        b, h = (int(x) for x in gemerkt.lower().split("x"))
        breite, hoehe = b, h
    except ValueError:
        pass
    if bildschirm is not None:
        breite = min(breite, bildschirm.width - 40)
        hoehe = min(hoehe, bildschirm.height - 100)
    return max(breite, MIN_GROESSE[0]), max(hoehe, MIN_GROESSE[1])


def starten() -> None:
    import webview

    dienst = Dienst()
    try:
        bildschirm = webview.screens[0]
    except Exception:
        log.warning("Bildschirmgrösse unbekannt, nutze Standardgrösse", exc_info=True)
        bildschirm = None
    breite, hoehe = fenstergroesse(dienst.einstellungen()["fenster"], bildschirm)

    fenster = webview.create_window(
        "Mitschrift",
        html=UI.read_text(encoding="utf-8"),
        js_api=Api(dienst),
        width=breite,
        height=hoehe,
        min_size=MIN_GROESSE,
        text_select=True,
        background_color="#EEF1F4",
    )

    letzte_groesse: dict[str, str] = {}

    def groesse_merken(breite: int, hoehe: int) -> None:
        letzte_groesse["wert"] = f"{breite}x{hoehe}"

    def schliessen() -> None:
        if "wert" in letzte_groesse:
            dienst.einstellungen_speichern({"fenster": letzte_groesse["wert"]})
        dienst.beenden()  # laufende Aufnahme sauber speichern

    fenster.events.resized += groesse_merken
    fenster.events.closing += schliessen
    webview.start(icon=str(ICON))  # Icon wirkt unter Linux; unter Windows kommt es von der Verknüpfung


# ---------------------------------------------------------------- Start per Doppelklick

def protokoll_pfad() -> Path:
    return mitschrift_home() / "protokoll.txt"


class _AnsProtokoll:
    """Ersetzt stdout/stderr, wenn kein Konsolenfenster da ist (mitschrift-app.exe).

    Fortschrittsbalken (tqdm, z.B. beim Modelldownload) fragen isatty() und
    encoding ab – deshalb sind beide vorhanden.
    """

    encoding = "utf-8"

    def __init__(self, stufe: int):
        self.stufe = stufe

    def isatty(self) -> bool:
        return False

    def write(self, text: str) -> int:
        if text.strip():
            log.log(self.stufe, text.rstrip())
        return len(text)

    def flush(self) -> None:
        pass


def _protokoll_einrichten() -> None:
    pfad = protokoll_pfad()
    pfad.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(pfad, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    if sys.stdout is None or sys.stderr is None:  # ohne Konsole
        sys.stdout, sys.stderr = _AnsProtokoll(logging.INFO), _AnsProtokoll(logging.ERROR)
    sys.excepthook = lambda t, w, tb: log.critical("Unbehandelter Fehler", exc_info=(t, w, tb))
    threading.excepthook = lambda a: log.critical(
        "Unbehandelter Fehler im Thread %s", a.thread, exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def _schon_offen() -> bool:
    """Unter Windows verhindern, dass die App zweimal läuft (zwei Aufnahmen gleichzeitig)."""
    global _MUTEX
    if sys.platform != "win32":
        return False
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _MUTEX = kernel32.CreateMutexW(None, False, "Local\\Mitschrift-App")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def _hinweis(text: str) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "Mitschrift", 0x40)
    else:
        print(text)


def hauptprogramm() -> None:
    """Einstieg für mitschrift-app.exe und `mitschrift app`."""
    _protokoll_einrichten()
    log.info("Mitschrift %s startet", __version__)
    if _schon_offen():
        _hinweis("Mitschrift ist bereits geöffnet.")
        return
    try:
        starten()
    except Exception:
        log.exception("Start fehlgeschlagen")
        _hinweis(f"Mitschrift konnte nicht gestartet werden.\n\nDetails stehen im Protokoll:\n{protokoll_pfad()}")
    log.info("Mitschrift beendet")
