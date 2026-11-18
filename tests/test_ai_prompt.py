"""«Für KI kopieren»: the instructions in the settings and the text put on the clipboard."""

import json

import numpy as np
import pytest

from verbalis import screens
from verbalis.settings import DEFAULT_PROMPTS, Settings

from test_service import finished_recording, make_service


def test_default_instructions_until_own_ones_are_saved():
    assert Settings().prompts == DEFAULT_PROMPTS
    own = json.dumps([{"name": "Pendenzen", "text": "Liste alle Aufgaben."}, {"name": " ", "text": ""}])
    assert Settings.from_dict({"ai_prompts": own}).prompts == [{"name": "Pendenzen", "text": "Liste alle Aufgaben."}]
    assert Settings.from_dict({"ai_prompts": "kein json"}).prompts == DEFAULT_PROMPTS
    assert Settings.from_dict({"ai_prompts": json.dumps(DEFAULT_PROMPTS)}).ai_prompts == ""   # stays «default»


def test_copied_text_has_path_details_and_instruction(home):
    s = make_service()
    rid = finished_recording(s)
    s.update_details(rid, {"title": "Konzept SLRG", "project": "SLRG", "participants": {"others": ["Mike"]},
                           "notes": "Mike schickt die Folien nach."})
    s.save_settings({"ai_prompts": json.dumps([{"name": "Meeting", "text": "Lege es unter {projekt} ab."}])})
    text = s.ai_prompt(rid, 0)
    folder = home / "recordings" / rid
    assert text.startswith(f"Lies das Transkript {folder / 'transcript.md'}.\n")
    assert "Schnappschüsse" not in text   # no pictures in this recording
    assert "Aufnahme: Konzept SLRG (" in text and "Projekt: SLRG" in text and "Teilnehmende: Mike" in text
    assert "Dauer: " in text and "Notizen dazu:\nMike schickt die Folien nach.\n" in text   # notes not lost
    assert text.endswith("Lege es unter SLRG ab.\n")


def test_copied_text_mentions_the_snapshots_when_there_are_some(home):
    s = make_service()
    rid = finished_recording(s)
    screens.save(home / "recordings" / rid, 3, np.zeros((20, 30, 3), np.uint8))
    assert "Die Bildschirm-Schnappschüsse liegen im Ordner screens/ daneben" in s.ai_prompt(rid, 1)


def test_instruction_that_no_longer_exists_is_reported(home):
    s = make_service()
    rid = finished_recording(s)
    with pytest.raises(RuntimeError, match="gibt es nicht mehr"):
        s.ai_prompt(rid, 5)
