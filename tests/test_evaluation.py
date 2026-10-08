import pytest

from verbalis.evaluation import error_rate, normalize


def test_normalize_numbers_and_punctuation():
    assert normalize("Das Budget: 25'300 Franken!") == ["das", "budget", "25300", "franken"]
    assert normalize("Nummer 079 123 45 67.") == ["nummer", "0791234567"]
    assert normalize("Am 24. Oktober") == ["am", "24", "oktober"]
    assert normalize("Teams-Meeting, Straße") == ["teams", "meeting", "strasse"]


def test_identical():
    assert error_rate("Guten Tag zusammen.", "guten tag, zusammen").wer == 0


def test_error_kinds():
    r = error_rate("a b c d", "a x c d e")
    assert (r.substituted, r.missing, r.extra) == (1, 0, 1)
    assert r.wer == pytest.approx(0.5)
    r = error_rate("a b c d", "a d")
    assert (r.substituted, r.missing, r.extra) == (0, 2, 0)


def test_empty_hypothesis():
    assert error_rate("a b", "").wer == 1.0
