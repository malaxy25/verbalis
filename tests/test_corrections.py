"""Correction list: unique targets, variants, applying rules, suggestions from edits."""

from verbalis.corrections import CorrectionList, suggestions


def test_target_is_unique_variants_are_collected():
    c = CorrectionList()
    assert c.add("Toko", "tocco")["kind"] == "new"
    assert c.add("Tokko", "Tocco")["kind"] == "added"       # same target, different case
    assert c.add("toko", "tocco")["kind"] == "known"
    assert c.as_list() == [{"target": "tocco", "variants": ["Tokko", "Toko"]}]


def test_newer_correction_replaces_older():
    c = CorrectionList()
    c.add("Toko", "Tokyo")
    info = c.add("Toko", "tocco")
    assert info["kind"] == "replaces" and info["previous"] == "Tokyo"
    assert c.target_of("Toko") == "tocco"
    assert "Tokyo" not in c.rules  # empty target disappears


def test_apply_whole_words_and_multi_word_variants():
    c = CorrectionList()
    c.add("Toko", "tocco")
    c.add("Limet nah", "Limmat")
    c.add("Limetnah", "Limmat")
    text, n = c.apply("Release von TOKO, entlang der Limet  nah. Tokoyo bleibt, Limetnah nicht.")
    assert text == "Release von tocco, entlang der Limmat. Tokoyo bleibt, Limmat nicht."
    assert n == 3


def test_save_and_load():
    c = CorrectionList()
    c.add("Toko", "tocco")
    c.save()
    assert CorrectionList.load().target_of("toko") == "tocco"
    c.remove("tocco", "Toko")
    assert c.rules == {}


def test_ignores_identical_words():
    assert CorrectionList().add("tocco", "Tocco")["kind"] == "ignored"


def test_suggestions_from_edit():
    old = "Wir haben über das Release von Toko geredet, mit dem Hund. Limet nah entlang."
    new = "Wir haben über das Release von tocco geredet, mit dem Kunden. Limmat entlang."
    assert suggestions(old, new) == [("Toko", "tocco"), ("Hund", "Kunden"), ("Limet nah", "Limmat")]


def test_no_suggestions_for_rephrasing_and_insertions():
    old = "Am Nachmittag muss ich noch an die Post gehen."
    assert suggestions(old, "Am Nachmittag muss ich noch an die Post gehen, das ist wichtig.") == []
    assert suggestions(old, "Später erledige ich die Einkäufe für die ganze Familie.") == []
    assert suggestions("das ist gut", "Das ist gut") == []
