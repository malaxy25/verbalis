"""Komprimieren und Aufbewahren der Audiodateien."""

import json
from datetime import datetime, timedelta

import numpy as np
import pytest
import soundfile as sf

from mitschrift import ablauf
from mitschrift.dienst import MB, Dienst
from mitschrift.einstellungen import Einstellungen


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MITSCHRIFT_HOME", str(tmp_path))
    return tmp_path


def _wav(pfad, sekunden=3.0, sr=48000):
    t = np.arange(int(sekunden * sr)) / sr
    sf.write(pfad, (0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), sr)


def _aufnahme(basis, tage_alt: float, transkript=True, mb=0.5):
    start = datetime.now().astimezone() - timedelta(days=tage_alt)
    ordner = basis / start.strftime("%Y-%m-%d_%H%M%S")
    ordner.mkdir(parents=True)
    (ordner / "meta.json").write_text(json.dumps({"start": start.isoformat(timespec="seconds")}))
    for spur in ablauf.SPUREN:
        (ordner / f"{spur}.flac").write_bytes(b"x" * int(mb * MB / 2))
    if transkript:
        (ordner / "transkript.json").write_text('{"segmente": []}')
    return ordner


def test_komprimieren_wav_zu_flac(tmp_path):
    for spur in ablauf.SPUREN:
        _wav(tmp_path / f"{spur}.wav")
    vorher = ablauf.audio_bytes(tmp_path)
    assert ablauf.audio_komprimieren(tmp_path) == 2
    assert not (tmp_path / "ich.wav").exists()
    daten, sr = sf.read(tmp_path / "ich.flac")
    assert sr == 16000 and abs(len(daten) - 48000) < 10
    assert 0.35 < np.abs(daten[1000:-1000]).max() < 0.45     # Ton bleibt erhalten
    assert ablauf.audio_bytes(tmp_path) < vorher / 3
    assert ablauf.meta_lesen(tmp_path)["audio"]["samplerate"] == 16000
    assert ablauf.audio_datei(tmp_path, "ich").suffix == ".flac"


def test_audio_loeschen_behaelt_transkript(tmp_path):
    ordner = _aufnahme(tmp_path, 0, mb=1)
    assert ablauf.audio_loeschen(ordner, "Test") == MB
    assert not ablauf.hat_audio(ordner) and ablauf.ist_aufnahmeordner(ordner)
    assert (ordner / "transkript.json").exists()
    assert ablauf.meta_lesen(ordner)["audio_geloescht"]["grund"] == "Test"


def _dienst(**einstellungen):
    return Dienst(einstellungen=Einstellungen(**einstellungen), geraete_liste=lambda: {}, aufraeumen_beim_start=False)


def test_frist_in_tagen(home):
    basis = home / "aufnahmen"
    alt = _aufnahme(basis, 4)
    neu = _aufnahme(basis, 1)
    ohne_transkript = _aufnahme(basis, 10, transkript=False)
    d = _dienst(audio_tage="3")
    assert d.aufraeumen() == [alt.name]
    assert ablauf.hat_audio(neu) and ablauf.hat_audio(ohne_transkript)   # Schutz ohne Transkript
    eintrag = {a["id"]: a for a in d.aufnahmen()}
    assert eintrag[alt.name]["audio"] is False
    assert eintrag[neu.name]["audio_loeschen"][:10] == (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")


def test_null_tage_und_unbegrenzt(home):
    basis = home / "aufnahmen"
    a = _aufnahme(basis, 0.01)
    assert _dienst(audio_tage="").aufraeumen() == []
    assert _dienst(audio_tage="0").aufraeumen() == [a.name]


def test_speichergrenze_loescht_aelteste_zuerst(home):
    basis = home / "aufnahmen"
    a = _aufnahme(basis, 2.0, mb=4)
    b = _aufnahme(basis, 1.5, mb=4)
    c = _aufnahme(basis, 1.0, mb=4)
    d = _dienst(audio_tage="", audio_max_mb="9")
    assert d.audio_speicher() == {"audio_mb": 12.0}
    assert d.aufraeumen() == [a.name]
    assert d.audio_speicher() == {"audio_mb": 8.0}
    assert ablauf.hat_audio(b) and ablauf.hat_audio(c)


def test_ohne_audio_nicht_neu_transkribieren(home):
    ordner = _aufnahme(home / "aufnahmen", 0)
    d = _dienst()
    d.audio_jetzt_loeschen(ordner.name)
    with pytest.raises(RuntimeError, match="gelöscht"):
        d.transkribieren(ordner.name)


def test_einstellungen_pruefen_eingaben():
    e = Einstellungen.aus_dict({"audio_tage": "abc", "audio_max_mb": "-5"})
    assert (e.tage, e.max_mb) == (3, None)
    assert Einstellungen.aus_dict({"audio_tage": "", "audio_max_mb": "500"}).max_mb == 500
