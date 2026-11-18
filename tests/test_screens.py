"""Screen snapshots during a recording (screens.py): which pictures are kept, their files, the Markdown links
and the way through the service. No real screen: pictures are numpy arrays."""


import numpy as np
import pytest

from verbalis import screens
from verbalis.screens import ChangeDetector, ScreenCapture, small
from verbalis.transcript import to_markdown
from verbalis.transcription.base import Segment

from test_service import FakeTranscriber, make_service, wait_until


def picture(value: int, h: int = 160, w: int = 240) -> np.ndarray:
    return np.full((h, w, 3), value, np.uint8)


def with_tile(base: int, tile: int, seed: int) -> np.ndarray:
    """A still picture with a small «video tile» that changes every time (1 % of the area)."""
    p = picture(base)
    rng = np.random.default_rng(seed)
    p[:16, :24] = rng.integers(0, 255, (16, 24, 3), dtype=np.uint8)
    p[:16, :24, 0] = tile
    return p


def test_first_picture_is_kept_once_the_screen_is_still():
    d = ChangeDetector()
    assert d.feed(small(picture(10)), 0) is None
    assert d.feed(small(picture(10)), 1) is None
    assert d.feed(small(picture(10)), 2) == 0
    assert d.feed(small(picture(10)), 3) is None   # the same picture is not kept twice


def test_new_slide_is_kept_with_the_time_the_change_began():
    d = ChangeDetector()
    for t in range(3):
        d.feed(small(picture(10)), t)
    assert d.feed(small(picture(200)), 10) is None
    assert d.feed(small(picture(200)), 11) is None
    assert d.feed(small(picture(200)), 12) == 10


def test_scrolling_keeps_only_where_it_stops():
    d = ChangeDetector()
    for t in range(3):
        d.feed(small(picture(10)), t)
    kept = [d.feed(small(picture(20 + 30 * t)), t) for t in range(3, 7)]   # moving: different every second
    assert kept == [None] * 4
    kept = [d.feed(small(picture(250)), t) for t in range(7, 10)]
    assert kept == [None, None, 3]


def test_small_video_tile_does_not_make_new_pictures():
    """Bug guard: moving video tiles in a Teams window must not fill the folder with nearly equal pictures."""
    d = ChangeDetector()
    kept = [d.feed(small(with_tile(10, 0, t)), t) for t in range(120)]
    assert sum(k is not None for k in kept) == 1


def test_new_slide_next_to_a_video_tile_is_kept_right_away():
    d = ChangeDetector()
    for t in range(40):
        d.feed(small(with_tile(10, 0, t)), t)
    kept = [d.feed(small(with_tile(200, 0, t)), t) for t in range(40, 44)]
    assert 40 in kept


def teams_call(slide: int, t: int) -> np.ndarray:
    """A shared screen (one grey level per slide) with a strip of four talking video tiles on the right –
    together 20 % of the window, far more than CHANGED_SHARE."""
    p = picture(slide, 200, 400)
    rng = np.random.default_rng(t)
    p[:, 320:] = rng.integers(0, 255, (200, 80, 3), dtype=np.uint8)
    return p


def test_teams_video_tiles_next_to_a_shared_screen_are_ignored():
    """The video of the people in a Teams call must not make pictures; each new slide makes exactly one, soon."""
    d = ChangeDetector()
    slides = [(0, 10), (60, 120), (75, 200), (140, 60)]   # (from second, grey level of the slide)
    kept = []
    for t in range(200):
        slide = [level for start, level in slides if start <= t][-1]
        if (at := d.feed(small(teams_call(slide, t)), t)) is not None:
            kept.append(at)
    assert len(kept) == 4
    for (start, _), at in zip(slides, kept):
        assert start <= at <= start + 1


def test_screen_that_never_rests_is_kept_at_most_every_max_wait():
    d = ChangeDetector()
    kept = [d.feed(small(picture((t * 70) % 256)), t) for t in range(95)]   # a full-screen video
    times = [k for k in kept if k is not None]
    assert 2 <= len(times) <= 4


def test_files_are_named_after_the_recording_time_and_listed_in_order(tmp_path):
    screens.save(tmp_path, 3725.4, picture(50))
    screens.save(tmp_path, 12, picture(90))
    screens.save(tmp_path, 12, picture(91))   # same second: not overwritten
    assert screens.listing(tmp_path) == [(12, "screens/00-00-12.png"), (12, "screens/00-00-12_1.png"),
                                         (3725, "screens/01-02-05.png")]
    assert (tmp_path / "screens" / ".thumbs" / "01-02-05.png").exists()
    assert (tmp_path / "screens" / "00-00-12.png").read_bytes()[:4] == b"\x89PNG"


def test_image_path_only_for_snapshots_of_the_recording(tmp_path):
    screens.save(tmp_path, 5, picture(50))
    assert screens.image_path(tmp_path, "screens/00-00-05.png", thumb=True).parent.name == ".thumbs"
    for bad in ("../meta.json", "screens/../meta.json", "me.flac", "screens/x.png"):
        with pytest.raises(RuntimeError):
            screens.image_path(tmp_path, bad)


def test_markdown_links_each_picture_before_the_paragraph_it_belongs_to():
    paragraphs = [Segment(0, 9, "Willkommen.", "Mike"), Segment(10, 30, "Hier Abschnitt zwei.", "Mike"),
                  Segment(31, 40, "Dazu eine Frage.", "Andrea")]
    md = to_markdown(paragraphs, "Konzept", {}, [(2, "screens/00-00-02.png"), (10, "screens/00-00-10.png"),
                                                 (50, "screens/00-00-50.png")])
    lines = [line for line in md.splitlines() if line]
    assert lines.index("**[00:10] Bildschirm:** ![Bildschirm 00:10](screens/00-00-10.png)") \
        == lines.index("**[00:10] Mike:** Hier Abschnitt zwei.") - 1
    assert lines.index("**[00:02] Bildschirm:** ![Bildschirm 00:02](screens/00-00-02.png)") \
        == lines.index("**[00:00] Mike:** Willkommen.") + 1
    assert lines[-1] == "**[00:50] Bildschirm:** ![Bildschirm 00:50](screens/00-00-50.png)"
    assert "Bildschirm" not in to_markdown(paragraphs, "Konzept", {})


def test_capture_skips_pauses_and_uses_recording_time(tmp_path):
    calls = {"n": 0}
    frames = iter([picture(10)] * 3 + [picture(200)] * 50)

    def position():   # paused for the first two samples, then the recording time is the sample number
        calls["n"] += 1
        return None if calls["n"] <= 2 else calls["n"]

    cap = ScreenCapture(tmp_path, "monitor:1", position, opener=lambda target: lambda: next(frames), interval_s=0.01)
    cap.start()
    assert wait_until(lambda: cap.count == 2)
    cap.stop()
    assert [t for t, _ in screens.listing(tmp_path)] == [3, 6]


def test_capture_of_a_missing_window_fails_before_the_recording(tmp_path):
    def opener(target):
        raise RuntimeError("Das Fenster «Teams» gibt es nicht mehr.")

    cap = ScreenCapture(tmp_path, "window:Teams", lambda: 0.0, opener=opener)
    with pytest.raises(RuntimeError, match="gibt es nicht mehr"):
        cap.start()


def fake_capture(pictures):
    def factory(folder, target, position):
        frames = iter(pictures)
        return ScreenCapture(folder, target, position, opener=lambda t: lambda: next(frames, pictures[-1]),
                             interval_s=0.01)
    return factory


def test_recording_with_snapshots_links_them_in_the_transcript(home):
    s = make_service(screen_factory=fake_capture([picture(10)] * 5 + [picture(200)] * 5))
    rid = s.start_recording("Mic", "", consent=True, screen="monitor:1")
    assert wait_until(lambda: (s.state()["recording"]["screens"] or {}).get("count") == 2, timeout=15)
    s.stop_recording()
    assert wait_until(lambda: s.recordings()[0]["status"] == "done", timeout=15)
    folder = home / "recordings" / rid
    t = s.transcript(rid)
    assert len(t["screens"]) == 2 and t["screens"][0]["file"].startswith("screens/")
    assert wait_until(lambda: "](screens_crop/" in (folder / "transcript.md").read_text(encoding="utf-8"))
    assert s.settings()["screen"] == "monitor:1"   # remembered for the next recording
    assert s.screen_image(rid, t["screens"][0]["file"], thumb=True).startswith("data:image/png;base64,")
    # an edit rewrites transcript.md – the pictures stay linked
    s.edit_transcript(rid, 0, "Neu geschrieben.")
    assert "](screens_crop/" in (folder / "transcript.md").read_text(encoding="utf-8")


def test_wrong_screen_choice_starts_no_recording(home):
    def factory(folder, target, position):
        def opener(t):
            raise RuntimeError("Das Fenster «Teams» gibt es nicht mehr.")
        return ScreenCapture(folder, target, position, opener=opener)

    s = make_service(screen_factory=factory, transcriber_factory=FakeTranscriber)
    with pytest.raises(RuntimeError, match="gibt es nicht mehr"):
        s.start_recording("Mic", "", consent=True, screen="window:Teams")
    assert s.state()["recording"] is None


def test_no_snapshot_time_before_the_recording_runs(home):
    """Bug 18.11.2026: the capture starts before the recorder (to report a closed window first); a picture taken in
    between got the computer's uptime as recording time – a file «124-26-38.png» in a 43-minute recording."""
    seen = {}

    class Probe:
        def __init__(self, folder, target, position):
            self.position = position
            self.count, self.problem = 0, None

        def start(self):
            seen["before"] = self.position()

        def stop(self):
            pass

    s = make_service(screen_factory=Probe)
    s.start_recording("Mic", "", consent=True, screen="monitor:1")
    probe = s._rec_info["screens"]
    assert seen["before"] is None
    assert 0 <= probe.position() < 60
    s.stop_recording()


def test_unknown_screen_setting_falls_back_to_none():
    from verbalis.settings import Settings

    assert Settings.from_dict({"screen": "irgendwas"}).screen == ""
    assert Settings.from_dict({"screen": "window:Teams"}).screen == "window:Teams"


def test_meeting_windows_are_listed_apart_with_calls_first():
    """Bug 18 Nov 2026: the Teams call window was hard to find among all windows (and Teams' main window looks
    alike) – meeting windows form their own group, running calls first."""
    from verbalis.screens import group_windows, meeting_kind

    titles = ["Verbalis", "Calendar | Tocco AG | a@b.ch | Microsoft Teams", "3CX (PWA)",
              "Interne Vorstellung: Release 3.16 | Tocco AG | a@b.ch | Microsoft Teams", "Posteingang – Outlook",
              "Meet – abc-defg-hij - Google Chrome", "Zoom Meeting", "Zoom Workplace"]
    g = group_windows(titles)
    assert [m["label"] for m in g["meetings"]] == [
        "Interne Vorstellung: Release 3.16 | Tocco AG | a@b.ch | Microsoft Teams",
        "Meet – abc-defg-hij - Google Chrome", "Zoom Meeting",
        "Calendar | Tocco AG | a@b.ch | Microsoft Teams", "3CX (PWA)", "Zoom Workplace"]
    assert [m["call"] for m in g["meetings"]] == [True, True, True, False, False, False]
    assert [w["label"] for w in g["windows"]] == ["Verbalis", "Posteingang – Outlook"]
    assert meeting_kind("Chat | Anna | Microsoft Teams") == "app"
    assert meeting_kind("Meeting | Microsoft Teams") == "call"
    assert meeting_kind("Meeting-Notizen.docx - Word") is None


# ------------------------------------------------------------------ preparing the pictures for an AI

def call_screen(slide: int, seed: int, h: int = 300, w: int = 480) -> np.ndarray:
    """A full-screen Teams call: a meeting bar on top, the shared content (a slide with some lines), video tiles on
    the right and the taskbar at the bottom – only the content differs much from picture to picture."""
    rng = np.random.default_rng(seed)
    p = np.full((h, w, 3), 230, np.uint8)
    p[:36] = 40                                          # meeting bar
    p[36:280, :390] = 255                                # shared content
    text = np.random.default_rng(slide)
    for y, width in zip(text.integers(0, 215, 12), text.integers(150, 370, 12)):   # lines of text
        p[50 + y:56 + y, 20:20 + width] = (slide * 37) % 200
    p[40:80, 400:470] = rng.integers(100, 110, (40, 70, 3))   # a tile, slightly noisy
    p[280:] = 20                                         # taskbar
    return p


def test_content_box_is_where_the_pictures_differ():
    """Bar, video tiles and taskbar of a Teams call are cut away without text recognition."""
    box = screens.content_box([screens._grey(call_screen(s, s)) for s in range(8)])
    top, bottom, left, right = box
    assert 36 / 300 - 0.03 <= top <= 55 / 300 and 0.85 <= bottom <= 280 / 300 + 0.02
    assert left <= 0.06 and 0.7 <= right <= 400 / 480   # the tiles start at 400 px
    assert screens.content_box([screens._grey(call_screen(s, s)) for s in range(2)]) is None   # too few to tell
    noise = [np.random.default_rng(s).integers(0, 255, (75, 120)).astype(np.int16) for s in range(5)]
    assert screens.content_box(noise) is None   # everything changes: nothing to cut


def test_short_and_repeated_pictures_are_not_chosen():
    a, b, c = (screens._grey(call_screen(n, n)) for n in range(3))
    #              0 a     20 b (4 s)  24 c    40 a again  60 b (3 s until the end)
    verdicts = screens.choose([0, 20, 24, 40, 60], [a, b, c, a.copy(), b], end_s=63)
    assert verdicts == ["", "short", "", "0", "short"]
    assert screens.choose([0], [a], end_s=None) == [""]   # end unknown: kept


def test_two_white_slides_with_different_text_are_not_the_same():
    """A coarse picture hash (as in the first script) took two mostly white slides for one – compared per pixel."""
    assert screens.choose([0, 30], [screens._grey(call_screen(1, 0)), screens._grey(call_screen(2, 0))], 60) == ["", ""]


def test_a_very_short_recording_keeps_its_longest_shown_picture():
    a, b = screens._grey(call_screen(1, 0)), screens._grey(call_screen(2, 0))
    assert screens.choose([0, 2], [a, b], end_s=8) == ["short", ""]


def test_png_written_by_save_is_read_back(tmp_path):
    p = call_screen(3, 3)
    path = screens.save(tmp_path, 1, p)
    assert np.array_equal(screens.read_png(path), p)


def test_prepare_cuts_chooses_and_the_transcript_links_the_chosen(tmp_path):
    for t, slide in [(0, 1), (30, 2), (45, 3), (60, 4), (90, 1)]:   # slide 1 again at 90
        screens.save(tmp_path, t, call_screen(slide, t))
    screens.save(tmp_path, 95, call_screen(5, 95))                   # shown 2 s until the end
    assert screens.prepare(tmp_path, end_s=97) is True
    assert screens.prepare(tmp_path, end_s=97) is False               # up to date
    entries = screens.for_transcript(tmp_path)
    assert [(t, note) for t, _, note in entries] == [(0, ""), (30, ""), (45, ""), (60, ""), (90, "gleich wie 00:00"),
                                                    (95, "nur kurz gezeigt")]
    assert entries[0][1] == "screens_crop/00-00-00.png" and entries[5][1] == "screens/00-01-35.png"
    cut = screens.read_png(tmp_path / "screens_crop" / "00-00-00.png")
    assert cut.shape[0] < 300 * 0.9 and cut.shape[1] < 480 * 0.9
    md = to_markdown([Segment(100, 110, "Fragen?", "Mike")], "T", {}, entries)
    assert "**[00:00] Bildschirm:** ![Bildschirm 00:00](screens_crop/00-00-00.png)" in md
    assert "**[01:30] Bildschirm:** gleich wie 00:00 (screens/00-01-30.png)" in md
    # a later picture (a recording continued): the old choice no longer counts until prepared again
    screens.save(tmp_path, 120, call_screen(6, 120))
    assert all(p.startswith("screens/") and not note for _, p, note in screens.for_transcript(tmp_path))
    assert screens.prepare(tmp_path, end_s=150) is True
