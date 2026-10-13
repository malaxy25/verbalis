"""Merging both tracks into paragraphs and the Markdown output."""

import json

from verbalis.transcript import merge, to_markdown
from verbalis.transcription.base import Segment


def test_tracks_are_interleaved_by_time_and_paragraphs_formed():
    paragraphs = merge({
        "Andrea": [Segment(0.0, 2.0, "Grüezi zäme."), Segment(2.5, 4.0, "Wie gaht's?"), Segment(10.0, 11.0, "Super.")],
        "Gegenüber": [Segment(5.0, 8.0, "Guet, danke.")],
    })
    assert [(p.speaker, p.text) for p in paragraphs] == [
        ("Andrea", "Grüezi zäme. Wie gaht's?"),  # 0.5 s pause → same paragraph
        ("Gegenüber", "Guet, danke."),
        ("Andrea", "Super."),
    ]
    assert paragraphs[0].end == 4.0


def test_long_pause_starts_new_paragraph():
    assert len(merge({"Ich": [Segment(0, 1, "A"), Segment(5, 6, "B")]})) == 2


def test_markdown_format():
    md = to_markdown([Segment(65.0, 70.0, "Hallo", "Ich")], "Titel", {"Modell": "x"})
    assert "**[01:05] Ich:** Hallo" in md
    assert "- **Modell:** x" in md


def _words(start, text, step=0.4):
    """Word timestamps for a sentence spoken from `start`, one word every `step` seconds."""
    return [(start + i * step, start + (i + 1) * step, f" {w}") for i, w in enumerate(text.split())]


def _seg(start, text, step=0.4):
    words = _words(start, text, step)
    return Segment(words[0][0], words[-1][1], text, words=words)


def test_question_appears_where_it_was_asked():
    """0.7.18 reading flow: a long answer used to swallow a question asked in the middle – it came afterwards."""
    andrea = _seg(0.0, "Wir haben das Release geplant. Die Tests laufen seit Montag ohne Fehler durch. "
                       "Danach kommt die Dokumentation an die Reihe.")
    paragraphs = merge({"Andrea": [andrea], "Gegenüber": [_seg(4.5, "Welche Tests genau meinst du?")]})
    assert [(p.speaker, p.text.split()[0]) for p in paragraphs] == [
        ("Andrea", "Wir"), ("Gegenüber", "Welche"), ("Andrea", "Danach"),
    ]
    # the question came during the second sentence: the paragraph is split after that sentence
    assert paragraphs[0].text.endswith("ohne Fehler durch.") and paragraphs[2].text == (
        "Danach kommt die Dokumentation an die Reihe.")


def test_interjection_while_someone_speaks_is_an_aside():
    long = _seg(0.0, "Das Budget liegt bei fünfundzwanzigtausend Franken und reicht wenn wir den Umfang halten.")
    paragraphs = merge({"Gegenüber": [long], "Andrea": [_seg(2.0, "Ja genau.", 0.3)]})
    main = [p for p in paragraphs if not p.aside]
    asides = [p for p in paragraphs if p.aside]
    assert len(main) == 1 and main[0].speaker == "Gegenüber"           # the paragraph is not interrupted
    assert [(a.speaker, a.text) for a in asides] == [("Andrea", "Ja genau.")]


def test_short_answer_after_a_question_stays_a_paragraph():
    question = _seg(0.0, "Kommst du morgen auch an die Sitzung im Büro?")
    paragraphs = merge({"Gegenüber": [question], "Andrea": [_seg(4.2, "Ja.")]})
    assert [(p.speaker, p.aside) for p in paragraphs] == [("Gegenüber", False), ("Andrea", False)]


def test_aside_in_markdown_and_json(tmp_path):
    from verbalis.transcript import save
    paragraphs = [Segment(0.0, 5.0, "Lange Erklärung.", "Gegenüber"), Segment(2.0, 2.4, "mhm", "Andrea", aside=True)]
    md = save(tmp_path, "transcript", paragraphs, "Titel", {}).read_text(encoding="utf-8")
    assert "*[00:02] Andrea: mhm*" in md
    data = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert data["segments"][1]["aside"] is True and "aside" not in data["segments"][0]
