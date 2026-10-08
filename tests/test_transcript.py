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
