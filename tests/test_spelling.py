"""Spell checking with a tiny test dictionary (no download)."""

import pytest

from verbalis.spelling import Speller

AFF = "SET UTF-8\nTRY esianrtolcdugmphbfwkvzüäöyjqxESIANRTOLCDUGMPHBFWKVZÜÄÖ\n"
WORDS = ["Mittwoch", "Budget", "Strasse", "gross", "Release", "Termin", "geregnet", "das", "ist"]


@pytest.fixture
def speller(tmp_path):
    folder = tmp_path / "dict"
    folder.mkdir()
    (folder / "de_CH_frami.aff").write_text(AFF, encoding="utf-8")
    (folder / "de_CH_frami.dic").write_text(f"{len(WORDS)}\n" + "\n".join(WORDS) + "\n", encoding="utf-8")
    s = Speller(folder=folder, download=False)
    s.load_now()
    assert s.status == "ready"
    return s


def test_check_finds_misspelled_words(speller):
    result = speller.check(["Mitwoch", "Budget", "Budjet", "Strasse", "CEO", "x", "Release-Termin"])
    assert result == {"status": "ready", "error": None, "misspelled": ["Budjet", "Mitwoch"]}


def test_extra_and_personal_words_count_as_correct(speller):
    assert speller.check(["tocco"], extra=["Tocco"])["misspelled"] == []
    assert speller.check(["Grüezi"])["misspelled"] == ["Grüezi"]
    speller.add_word("Grüezi")
    speller.add_word("grüezi")          # no duplicate
    assert speller.check(["Grüezi"])["misspelled"] == []
    assert speller.personal_words() == {"grüezi"}


def test_suggestions(speller):
    assert speller.suggest("Mitwoch")[0] == "Mittwoch"
    assert "geregnet" in speller.suggest("geregent")


def test_missing_dictionary_without_download(tmp_path):
    s = Speller(folder=tmp_path / "nothing", download=False)
    s.load_now()
    assert s.status == "error" and "Wörterbuch" in s.error
    assert s.check(["Wort"])["status"] == "error"
    assert s.suggest("Wort") == []


def test_outdated_revision_triggers_new_download(tmp_path, monkeypatch):
    from verbalis import spelling

    folder = tmp_path / "dict"
    folder.mkdir()
    (folder / "de_CH_frami.aff").write_text(AFF, encoding="utf-8")
    (folder / "de_CH_frami.dic").write_text("1\nBudget\n", encoding="utf-8")
    (folder / "revision.txt").write_text("old", encoding="utf-8")
    downloaded = []

    def fake_download(self, target):
        downloaded.append(target)
        (target / "revision.txt").write_text(spelling.DICTIONARY_REVISION, encoding="utf-8")

    monkeypatch.setattr(spelling.Speller, "_download", fake_download)
    s = spelling.Speller(folder=folder)
    s.load_now()
    assert downloaded == [folder] and s.status == "ready"
    s2 = spelling.Speller(folder=folder)
    s2.load_now()
    assert downloaded == [folder]          # current revision → no second download
