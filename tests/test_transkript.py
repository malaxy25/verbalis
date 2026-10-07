from mitschrift.transcription.base import Segment
from mitschrift.transkript import als_markdown, zusammenfuehren


def test_spuren_werden_nach_zeit_verschraenkt_und_absaetze_gebildet():
    absaetze = zusammenfuehren({
        "Andrea": [Segment(0.0, 2.0, "Grüezi zäme."), Segment(2.5, 4.0, "Wie gaht's?"), Segment(10.0, 11.0, "Super.")],
        "Gegenüber": [Segment(5.0, 8.0, "Guet, danke.")],
    })
    assert [(a.sprecher, a.text) for a in absaetze] == [
        ("Andrea", "Grüezi zäme. Wie gaht's?"),  # Pause 0.5 s → gleicher Absatz
        ("Gegenüber", "Guet, danke."),
        ("Andrea", "Super."),
    ]
    assert absaetze[0].ende == 4.0


def test_lange_pause_beginnt_neuen_absatz():
    absaetze = zusammenfuehren({"Ich": [Segment(0, 1, "A"), Segment(5, 6, "B")]})
    assert len(absaetze) == 2


def test_markdown_format():
    md = als_markdown([Segment(65.0, 70.0, "Hallo", "Ich")], "Titel", {"Modell": "x"})
    assert "**[01:05] Ich:** Hallo" in md
    assert "- **Modell:** x" in md
