import pytest

from mitschrift.korrekturen import Korrekturliste, vorschlaege


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MITSCHRIFT_HOME", str(tmp_path))


def test_ziel_ist_eindeutig_varianten_werden_gesammelt():
    k = Korrekturliste()
    assert k.hinzufuegen("Toko", "tocco")["art"] == "neu"
    assert k.hinzufuegen("Tokko", "Tocco")["art"] == "ergaenzt"      # gleiches Ziel, andere Schreibung
    assert k.hinzufuegen("toko", "tocco")["art"] == "bekannt"
    assert k.als_liste() == [{"ziel": "tocco", "varianten": ["Tokko", "Toko"]}]


def test_neuere_korrektur_ersetzt_alte():
    k = Korrekturliste()
    k.hinzufuegen("Toko", "Tokyo")
    info = k.hinzufuegen("Toko", "tocco")
    assert info["art"] == "ersetzt" and info["bisher"] == "Tokyo"
    assert k.ziel_von("Toko") == "tocco"
    assert "Tokyo" not in k.regeln  # leeres Ziel verschwindet


def test_anwenden_ganze_woerter_und_mehrwort_varianten():
    k = Korrekturliste()
    k.hinzufuegen("Toko", "tocco")
    k.hinzufuegen("Limet nah", "Limmat")
    k.hinzufuegen("Limetnah", "Limmat")
    text, n = k.anwenden("Release von TOKO, entlang der Limet  nah. Tokoyo bleibt, Limetnah nicht.")
    assert text == "Release von tocco, entlang der Limmat. Tokoyo bleibt, Limmat nicht."
    assert n == 3


def test_speichern_und_laden():
    k = Korrekturliste()
    k.hinzufuegen("Toko", "tocco")
    k.speichern()
    assert Korrekturliste.laden().ziel_von("toko") == "tocco"
    k.entfernen("tocco", "Toko")
    assert k.regeln == {}


def test_ignoriert_gleiche_woerter():
    assert Korrekturliste().hinzufuegen("tocco", "Tocco")["art"] == "ignoriert"


def test_vorschlaege_aus_bearbeitung():
    alt = "Wir haben über das Release von Toko geredet, mit dem Hund. Limet nah entlang."
    neu = "Wir haben über das Release von tocco geredet, mit dem Kunden. Limmat entlang."
    assert vorschlaege(alt, neu) == [("Toko", "tocco"), ("Hund", "Kunden"), ("Limet nah", "Limmat")]


def test_keine_vorschlaege_fuer_umformulierungen_und_einfuegungen():
    alt = "Am Nachmittag muss ich noch an die Post gehen."
    assert vorschlaege(alt, "Am Nachmittag muss ich noch an die Post gehen, das ist wichtig.") == []
    assert vorschlaege(alt, "Später erledige ich die Einkäufe für die ganze Familie.") == []
    assert vorschlaege("das ist gut", "Das ist gut") == []
