"""Ablauf der App ohne Fenster: Aufnahme → Warteschlange → Transkript."""

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from mitschrift.audio.recorder import SpurStatus
from mitschrift.dienst import Dienst
from mitschrift.einstellungen import Einstellungen
from mitschrift.transcription.base import Segment


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MITSCHRIFT_HOME", str(tmp_path))
    return tmp_path


class FakeRecorder:
    samplerate = 48000

    def __init__(self, mikrofon, loopback, ordner: Path):
        self.ordner = ordner
        self.stopp = threading.Event()
        self.fehler = []
        self.t0 = 0.0

    def start(self):
        self.ordner.mkdir(parents=True)
        self.t0 = time.monotonic() - 5  # tut so, als liefe sie schon 5 s
        for name in ("ich", "gegenueber"):
            sf.write(self.ordner / f"{name}.wav", np.zeros(48000, dtype=np.float32), 48000)

    def stoppen(self):
        self.stopp.set()

    @property
    def laeuft(self):
        return not self.stopp.is_set()

    def status(self):
        return [SpurStatus(n, self.ordner / f"{n}.wav", 48000 * 5, 0, 0.1) for n in ("ich", "gegenueber")]


class FakeTranscriber:
    def __init__(self, modell, fehler=False):
        self.modell, self.fehler = modell, fehler
        self.beam_size, self.stichworte = 5, None

    def transkribiere(self, audio, sprache="de", fortschritt=None):
        if self.fehler:
            raise RuntimeError("Modell kaputt")
        if fortschritt:
            fortschritt(0.5, 1.0)
        return [Segment(0.0, 1.0, f"Hallo von {self.modell}")]


def geraete(mikrofon, lautsprecher):
    return SimpleNamespace(mikrofon=SimpleNamespace(name="Mic"), loopback=SimpleNamespace(name="Lautsprecher"))


def dienst(**kwargs):
    e = Einstellungen(name="Andrea", modell="test-modell")
    kwargs.setdefault("transcriber_fabrik", FakeTranscriber)
    return Dienst(einstellungen=e, recorder_fabrik=FakeRecorder, geraete_ermitteln=geraete,
                  geraete_liste=lambda: {}, **kwargs)


def warten_bis(bedingung, timeout=5.0):
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.02)
    return False


def test_ohne_zustimmung_keine_aufnahme():
    d = dienst()
    with pytest.raises(RuntimeError, match="zugestimmt"):
        d.aufnahme_starten(einwilligung=False)


def test_aufnahme_bis_transkript():
    d = dienst()
    aid = d.aufnahme_starten("Mic", "", einwilligung=True)
    z = d.zustand()
    assert z["aufnahme"]["id"] == aid and z["aufnahme"]["dauer_s"] >= 5
    assert d.aufnahmen()[0]["status"] == "aufnahme"

    with pytest.raises(RuntimeError, match="bereits"):
        d.aufnahme_starten(einwilligung=True)

    assert d.aufnahme_stoppen() == aid
    assert warten_bis(lambda: d.aufnahmen()[0]["status"] == "fertig")

    t = d.transkript(aid)
    assert t["spuren"] == {"ich": "Andrea", "gegenueber": "Gegenüber"}
    assert [s["sprecher"] for s in t["segmente"]] == ["Andrea", "Gegenüber"]
    assert "Hallo von test-modell" in t["markdown"]
    assert d.aufnahmen()[0]["dauer_s"] >= 5
    # gewählte Geräte werden gemerkt
    assert Einstellungen.laden().mikrofon == "Mic"


def test_fehler_wird_angezeigt_und_wiederholbar():
    kaputt = {"ja": True}
    d = dienst(transcriber_fabrik=lambda m: FakeTranscriber(m, fehler=kaputt["ja"]))
    aid = d.aufnahme_starten(einwilligung=True)
    d.aufnahme_stoppen()
    assert warten_bis(lambda: d.aufnahmen()[0]["status"] == "fehler")
    assert "Modell kaputt" in d.aufnahmen()[0]["fehler"]

    kaputt["ja"] = False
    d._transcriber = None  # neues Modell erzwingen
    d.transkribieren(aid)
    assert warten_bis(lambda: d.aufnahmen()[0]["status"] == "fertig")


def test_modell_wird_wiederverwendet():
    erstellt = []
    d = dienst(transcriber_fabrik=lambda m: erstellt.append(m) or FakeTranscriber(m))
    for _ in range(2):
        d.aufnahme_starten(einwilligung=True)
        d.aufnahme_stoppen()
        time.sleep(1.1)  # neue Ordner-ID (Sekunden im Namen)
    assert warten_bis(lambda: all(a["status"] == "fertig" for a in d.aufnahmen()))
    assert erstellt == ["test-modell"]


def test_ungueltige_id_wird_abgelehnt():
    d = dienst()
    for boese in ("../etc", "a/b", "", "..\\x"):
        with pytest.raises(ValueError):
            d.transkript(boese)


def test_einstellungen_speichern_und_laden():
    d = dienst()
    neu = d.einstellungen_speichern({"name": "  Andrea F. ", "qualitaet": "schnell", "unbekannt": "x"})
    assert neu["name"] == "Andrea F." and neu["qualitaet"] == "schnell"
    e = Einstellungen.laden()
    assert e.name == "Andrea F." and e.beam_size == 1
    assert Einstellungen.aus_dict({"qualitaet": "turbo", "name": ""}).qualitaet == "genau"
