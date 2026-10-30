"""Merging both tracks into paragraphs and the Markdown output."""

import json

from verbalis.transcript import apply_marks, clean_text, merge, segment_dict, split_times, to_markdown
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


def test_asides_switched_off_are_paragraphs():
    """«Kurze Einwürfe am Rand zeigen» off: an interjection is a normal paragraph where it was said."""
    long = _seg(0.0, "Das Budget liegt bei fünfundzwanzigtausend Franken und reicht wenn wir den Umfang halten.")
    paragraphs = merge({"Gegenüber": [long], "Andrea": [_seg(2.0, "Ja genau.", 0.3)]}, asides=False)
    assert [(p.speaker, p.aside) for p in paragraphs] == [("Gegenüber", False), ("Andrea", False)]


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


def test_paragraphs_keep_their_word_timestamps():
    """0.7.32: the words are saved, so a paragraph split by hand gets the time of its second part."""
    paragraphs = merge({"Andrea": [_seg(0.0, "Wir starten am Montag."), _seg(2.0, "Das passt gut.")]})
    assert len(paragraphs) == 1 and [w[2].strip() for w in paragraphs[0].words] == [
        "Wir", "starten", "am", "Montag.", "Das", "passt", "gut."]
    assert segment_dict(paragraphs[0])["words"] == paragraphs[0].words


def test_split_time_comes_from_the_words_also_after_a_correction():
    words = _words(10.0, "Ich komme morgen. Jo das passt mir.", step=1.0)   # «Ja» was heard as «Jo»
    first_end, second_start, first, second = split_times(
        10.0, 17.0, words, "Ich komme morgen.", "Ja, das passt mir.")
    assert (first_end, second_start) == (13.0, 13.0)
    assert [w[2].strip() for w in first] == ["Ich", "komme", "morgen."] and len(second) == 4


def test_split_time_without_words_is_estimated_from_the_text():
    first_end, second_start, first, second = split_times(0.0, 10.0, None, "a" * 30, "b" * 10)
    assert first_end == second_start == 7.5 and first is None and second is None


def test_line_breaks_are_kept():
    assert clean_text("  Erste   Zeile \n\n  zweite Zeile ") == "Erste Zeile\nzweite Zeile"
    md = to_markdown([Segment(0.0, 2.0, "Erste Zeile\nzweite Zeile", "Ich")], "Titel", {})
    assert "**[00:00] Ich:** Erste Zeile  \nzweite Zeile" in md


def marked_transcript():
    """Teams call: diarization split Basil into two speakers, Sandra is a third one."""
    def seg(start, end, sid, name, track="others"):
        return {"start": start, "end": end, "text": "…", "track": track, "speaker_id": sid, "speaker": name}

    return {"tracks": {"me": "Andrea", "others": "Gegenüber"},
            "speakers": {"me-1": {"name": "Andrea", "track": "me"},
                         "others-1": {"name": "Gegenüber 1", "track": "others"},
                         "others-2": {"name": "Gegenüber 2", "track": "others"},
                         "others-3": {"name": "Gegenüber 3", "track": "others"}},
            "segments": [seg(0, 10, "me-1", "Andrea", "me"), seg(10, 30, "others-1", "Gegenüber 1"),
                         seg(30, 50, "others-2", "Gegenüber 2"), seg(50, 70, "others-3", "Gegenüber 3"),
                         seg(80, 90, "others-1", "Gegenüber 1")]}


def test_speaker_marks_name_speakers_and_join_a_split_person():
    """0.7.41: «Wer spricht gerade?» – a mark names the speaker talking then; one person split into two
    speakers by diarization (both marked «Basil») becomes one speaker."""
    data = marked_transcript()
    marks = [{"t": 12.0, "name": "Basil", "track": "others"}, {"t": 33.5, "name": "Basil", "track": "others"},
             {"t": 75.0, "name": "Sandra", "track": "others"}]     # 5 s after Sandra stopped: the nearest paragraph
    changed, doubts = apply_marks(data, marks)
    assert changed and doubts == [] and "mark_doubts" not in data
    assert {sid: s["name"] for sid, s in data["speakers"].items()} ==         {"me-1": "Andrea", "others-1": "Basil", "others-3": "Sandra"}
    assert [s["speaker"] for s in data["segments"]] == ["Andrea", "Basil", "Basil", "Sandra", "Basil"]
    assert [s["speaker_id"] for s in data["segments"]][1:3] == ["others-1", "others-1"]
    assert apply_marks(data, marks) == (False, [])     # applying again changes nothing


def test_speaker_marks_keep_names_typed_by_hand_and_report_two_people_on_one_voice():
    data = marked_transcript()
    data["speakers"]["others-2"]["name"] = "Peter"            # named in the speaker box
    marks = [{"t": 40.0, "name": "Basil", "track": "others"},
             {"t": 15.0, "name": "Sandra", "track": "others"}, {"t": 20.0, "name": "Tom", "track": "others"},
             {"t": 200.0, "name": "Eva", "track": "others"},      # nobody talks near it: ignored
             {"t": 25.0, "name": "Hans", "track": "me"}]          # no microphone paragraph near 25 s: ignored
    changed, doubts = apply_marks(data, marks)
    assert data["speakers"]["others-2"]["name"] == "Peter"
    assert data["speakers"]["others-1"]["name"] == "Sandra"      # a tie: the first mark wins
    assert doubts == [{"t": 20.0, "name": "Tom", "heard": "Sandra"}] == data["mark_doubts"]
    assert data["speakers"]["me-1"]["name"] == "Andrea"


def test_one_stray_speaker_mark_is_no_doubt_but_a_repeated_one_is():
    """0.7.43: 5 marks «Maurice» and one «Lara» a moment too late on the same voice gave the alarming notice
    «klingen für Verbalis gleich» although Lara had her own speaker. Now only unclear cases are doubts – with the
    moment to listen to – and they are stored in the transcript instead of a global notice."""
    def run(extra):
        data = marked_transcript()
        marks = [{"t": 12.0, "name": "Lara", "track": "others"},
                 *({"t": t, "name": "Maurice", "track": "others"} for t in (31, 35, 40, 45, 48)), *extra]
        return data, apply_marks(data, marks)[1]

    data, doubts = run([{"t": 42.0, "name": "Lara", "track": "others"}])     # 1 of 6: a stray mark
    assert doubts == [] and data["speakers"]["others-2"]["name"] == "Maurice"
    data, doubts = run([{"t": 42.0, "name": "Lara", "track": "others"}, {"t": 46.0, "name": "Lara", "track": "others"}])
    assert doubts == [{"t": 42.0, "name": "Lara", "heard": "Maurice"}, {"t": 46.0, "name": "Lara", "heard": "Maurice"}]
    data = marked_transcript()       # the losing name has no speaker of its own: diarization joined two people
    marks = [*({"t": t, "name": "Maurice", "track": "others"} for t in (31, 35, 40, 45, 48)),
             {"t": 42.0, "name": "Eva", "track": "others"}]
    assert apply_marks(data, marks)[1] == [{"t": 42.0, "name": "Eva", "heard": "Maurice"}]
