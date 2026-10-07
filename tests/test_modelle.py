import json

import pytest

from mitschrift.transcription import modelle


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MITSCHRIFT_HOME", str(tmp_path))
    return tmp_path


def test_eingebaute_und_hf_ids_werden_durchgereicht():
    assert modelle.aufloesen("large-v3-turbo") == "large-v3-turbo"
    assert modelle.aufloesen("Systran/faster-whisper-large-v3") == "Systran/faster-whisper-large-v3"


def test_konvertiertes_modell_wird_bevorzugt(home):
    ziel = home / "modelle" / "Flix-AI__flix-swissgerman-full"
    ziel.mkdir(parents=True)
    (ziel / "model.bin").write_bytes(b"x")
    (ziel / "mitschrift.json").write_text(json.dumps({"quelle": "Flix-AI/flix-swissgerman-full"}))
    assert modelle.aufloesen("Flix-AI/flix-swissgerman-full") == str(ziel)
    assert modelle.konvertierte_modelle() == ["Flix-AI/flix-swissgerman-full"]


def test_lokaler_ordner_ohne_model_bin(tmp_path):
    with pytest.raises(modelle.ModellFehler):
        modelle.aufloesen(str(tmp_path))


def test_unbekannter_name():
    with pytest.raises(modelle.ModellFehler):
        modelle.aufloesen("gibtsnicht")


def test_mel_baender_bestimmen_basismodell():
    assert modelle._basismodell_fuer(128) == "openai/whisper-large-v3"
    assert modelle._basismodell_fuer(80) == "openai/whisper-large-v2"
