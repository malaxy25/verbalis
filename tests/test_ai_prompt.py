"""«Für KI kopieren»: the texts in the settings and the text put on the clipboard."""

import json

import numpy as np
import pytest

from verbalis import screens
from verbalis.service import fill_prompt
from verbalis.settings import DEFAULT_PROMPTS, Settings

from test_service import finished_recording, make_service

VALUES = {"transkript": "C:/r/transcript.md", "bilder": "", "titel": "Konzept", "datum": "18.11.2026, 14:00",
          "dauer": "", "projekt": "", "teilnehmende": "Mike", "notizen": ""}


def test_default_texts_until_own_ones_are_saved():
    assert Settings().prompts == DEFAULT_PROMPTS
    own = json.dumps([{"name": "Pendenzen", "text": "{transkript}: Liste alle Aufgaben."}, {"name": " ", "text": ""}])
    assert Settings.from_dict({"ai_prompts": own}).prompts == [{"name": "Pendenzen",
                                                                "text": "{transkript}: Liste alle Aufgaben."}]
    assert Settings.from_dict({"ai_prompts": "kein json"}).prompts == DEFAULT_PROMPTS
    assert Settings.from_dict({"ai_prompts": json.dumps(DEFAULT_PROMPTS)}).ai_prompts == ""   # stays «default»


def test_default_texts_show_every_placeholder():
    """What is copied must be visible in the settings: the defaults carry all placeholders themselves."""
    for p in DEFAULT_PROMPTS:
        for key in VALUES:
            assert "{" + key + "}" in p["text"], (p["name"], key)


def test_a_changed_default_keeps_its_id_so_it_can_be_put_back_alone():
    changed = [{**DEFAULT_PROMPTS[0], "text": "Eigen"}, DEFAULT_PROMPTS[1], {"id": "fremd", "name": "X", "text": "y"}]
    prompts = Settings.from_dict({"ai_prompts": json.dumps(changed)}).prompts
    assert [p.get("id") for p in prompts] == ["meeting", "training", None]   # unknown ids are dropped
    assert Settings.from_dict({"ai_prompts": json.dumps(changed)}).as_dict()["default_prompts"] == DEFAULT_PROMPTS


def test_texts_saved_before_the_visible_placeholders_get_them():
    """Entries saved with only the instruction (the details were added unseen) would lose title, project, notes."""
    old = json.dumps([{"name": "Meeting", "text": "Fasse zusammen. test"}, {"name": "Eigen", "text": "Liste Aufgaben."}])
    prompts = Settings.from_dict({"ai_prompts": old}).prompts
    assert prompts[0]["id"] == "meeting" and prompts[0]["text"].endswith("{notizen}\n\nFasse zusammen. test")
    assert "id" not in prompts[1] and prompts[1]["text"].startswith("Lies das Transkript {transkript}.")


def test_lines_with_only_empty_placeholders_are_left_out():
    text = fill_prompt(DEFAULT_PROMPTS[1]["text"], VALUES)
    assert text == ("Lies das Transkript C:/r/transcript.md.\n\nAufnahme: Konzept (18.11.2026, 14:00)\n"
                    "Teilnehmende: Mike\n\nFasse die Besprechung nach Themen zusammen.\n")


def test_path_goes_in_front_when_the_text_has_no_transkript_placeholder():
    assert fill_prompt("Fasse {titel} zusammen. {unbekannt}", VALUES) == \
        "Lies das Transkript C:/r/transcript.md.\n\nFasse Konzept zusammen. {unbekannt}\n"


def test_copied_text_has_path_details_and_notes(home):
    s = make_service()
    rid = finished_recording(s)
    s.update_details(rid, {"title": "Konzept SLRG", "project": "SLRG", "participants": {"others": ["Mike"]},
                           "notes": "Mike schickt die Folien nach."})
    text = s.ai_prompt(rid, 0)
    folder = home / "recordings" / rid
    assert text.startswith(f"Lies das Transkript {folder / 'transcript.md'}.\n")
    assert "Schnappschüsse" not in text   # no pictures in this recording
    assert "Aufnahme: Konzept SLRG (" in text and " Min.)" in text
    assert "Projekt: SLRG\nTeilnehmende: Mike\nNotizen: Mike schickt die Folien nach.\n" in text   # notes not lost
    assert text.endswith("lege es unter dem Projekt im Vault ab.\n")


def test_copied_text_mentions_the_snapshots_when_there_are_some(home):
    s = make_service()
    rid = finished_recording(s)
    screens.save(home / "recordings" / rid, 3, np.zeros((20, 30, 3), np.uint8))
    assert "Die Bildschirm-Schnappschüsse liegen im Ordner screens/ daneben" in s.ai_prompt(rid, 1)


def test_text_that_no_longer_exists_is_reported(home):
    s = make_service()
    rid = finished_recording(s)
    with pytest.raises(RuntimeError, match="gibt es nicht mehr"):
        s.ai_prompt(rid, 5)
