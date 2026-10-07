import pytest

from mitschrift.auswertung import fehlerquote, normalisieren


def test_normalisieren_zahlen_und_satzzeichen():
    assert normalisieren("Das Budget: 25'300 Franken!") == ["das", "budget", "25300", "franken"]
    assert normalisieren("Nummer 079 123 45 67.") == ["nummer", "0791234567"]
    assert normalisieren("Am 24. Oktober") == ["am", "24", "oktober"]
    assert normalisieren("Teams-Meeting, Straße") == ["teams", "meeting", "strasse"]


def test_identisch():
    assert fehlerquote("Guten Tag zusammen.", "guten tag, zusammen").wer == 0


def test_fehlerarten():
    q = fehlerquote("a b c d", "a x c d e")
    assert (q.ersetzt, q.fehlend, q.zusaetzlich) == (1, 0, 1)
    assert q.wer == pytest.approx(0.5)
    q = fehlerquote("a b c d", "a d")
    assert (q.ersetzt, q.fehlend, q.zusaetzlich) == (0, 2, 0)


def test_leere_hypothese():
    assert fehlerquote("a b", "").wer == 1.0
