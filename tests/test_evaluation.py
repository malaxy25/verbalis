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


def _transcript(folder, edited=True):
    import json
    data = {"tracks": {"me": "Andrea", "others": "Gegenüber"}, "edited": edited, "segments": [
        {"start": 1.0, "end": 3.0, "text": "Guten Tag zusammen", "speaker": "Andrea"},
        {"start": 4.0, "end": 6.0, "text": "Hallo Andrea", "speaker": "Gegenüber"},
        {"start": 200.0, "end": 205.0, "text": "Später gesagt", "speaker": "Andrea"},
    ]}
    (folder / "transcript.json").write_text(json.dumps(data), encoding="utf-8")


def test_reference_from_corrected_transcript(tmp_path):
    from verbalis.evaluation import load_reference
    _transcript(tmp_path)
    ref = load_reference("transcript", tmp_path, until_s=180)
    assert ref.text == "Guten Tag zusammen Hallo Andrea"          # the paragraph at 200 s is cut off
    assert ref.tracks == {"me": "Guten Tag zusammen", "others": "Hallo Andrea"} and ref.edited is True
    assert load_reference("transcript", tmp_path).tracks["me"] == "Guten Tag zusammen Später gesagt"


def test_reference_from_text_file(tmp_path):
    from verbalis.evaluation import load_reference
    (tmp_path / "ref.txt").write_text("Guten Tag", encoding="utf-8")
    ref = load_reference(str(tmp_path / "ref.txt"), tmp_path)
    assert (ref.text, ref.tracks, ref.edited) == ("Guten Tag", None, None)
