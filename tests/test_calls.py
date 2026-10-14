"""Recognising calls: a call app uses the microphone → suggest recording (never record by itself)."""

from datetime import datetime, timedelta

from verbalis.audio.call_detect import call_apps
from test_service import make_service


def test_only_call_apps_count_and_verbalis_is_ignored():
    entries = [
        ("MSTeams_8wekyb3d8bbwe", 133, 0),                                        # new Teams, in use
        ("C:#Program Files (x86)#VB#Voicemeeter#voicemeeterpro.exe", 133, 0),    # mixer: always on
        ("C:#Users#a#AppData#Local#WisprFlow#app-1.6#Wispr Flow.exe", 133, 0),    # dictation
        ("C:#Python314#python.exe", 133, 0),                                     # Verbalis itself
        ("C:#Program Files#Zoom#bin#Zoom.exe", 133, 140),                        # Zoom, call over
        ("C:#Program Files#Google#Chrome#Application#chrome.exe", 133, 0),       # e.g. Google Meet
    ]
    assert call_apps(entries, own=[r"C:\Python314\python.exe"]) == ["Teams", "Browser"]
    assert call_apps([("C:#Python314#python.exe", 1, 0)], own=[r"C:\Python314\python.exe"]) == []


class Notifier:
    def __init__(self):
        self.shown, self.hidden = [], 0

    def show(self, title, text):
        self.shown.append((title, text))

    def hide(self):
        self.hidden += 1


def _service(apps):
    s = make_service(detect_calls=lambda: list(apps))
    s._stopping.set()          # the test drives the checks itself
    s.call_notifier = Notifier()
    return s


def test_call_is_suggested_once_and_forgotten_when_it_ends():
    apps = ["Teams"]
    s = _service(apps)
    s._check_call(lambda: list(apps))
    assert s.state()["call"] == {"app": "Teams", "planned": None}
    assert s.call_notifier.shown[0][0] == "Teams-Call erkannt – aufnehmen?"
    assert "Zustimmung" in s.call_notifier.shown[0][1]
    s._check_call(lambda: list(apps))
    assert len(s.call_notifier.shown) == 1                 # once per call

    s.dismiss_call()
    assert s.state()["call"] is None                       # «Nicht aufnehmen»
    s._check_call(lambda: [])
    assert s._call is None and s.call_notifier.hidden >= 1  # call over: the next one is suggested again


def test_no_notification_when_the_window_is_in_front_and_never_a_recording():
    s = _service(["Teams"])
    s.state(focused=True)
    s._check_call(lambda: ["Teams"])
    assert s.call_notifier.shown == [] and s.state()["call"]["app"] == "Teams"   # shown in the window
    assert s.recordings() == []                                                   # nothing recorded


def test_suggestion_offers_a_planned_recording_that_is_due():
    s = _service(["Teams"])
    soon = (datetime.now() + timedelta(minutes=10)).isoformat(timespec="minutes")
    later = (datetime.now() + timedelta(hours=3)).isoformat(timespec="minutes")
    pid = s.plan_recording({"start": soon, "title": "Weekly"})
    s.plan_recording({"start": later, "title": "Später"})
    s._check_call(lambda: ["Teams"])
    assert s.state()["call"]["planned"] == {"id": pid, "title": "Weekly"}
    assert "Weekly" in s.call_notifier.shown[0][1]


def test_switched_off_or_recording_means_no_suggestion():
    s = _service(["Teams"])
    s.save_settings({"call_detection": "off"})
    s._check_call(lambda: ["Teams"])
    assert s.state()["call"] is None
    s.save_settings({"call_detection": "on"})
    s.start_recording(consent=True)
    s._check_call(lambda: ["Teams"])
    assert s.state()["call"] is None
    s.stop_recording()


def test_asks_to_stop_the_recording_when_the_call_is_over():
    """0.7.26: the recognised Teams call ended – ask whether to stop the recording (never stop by itself)."""
    import time
    s = _service(["Teams"])
    s._check_call(lambda: ["Teams"])                       # call recognised, then recorded
    s.start_recording(consent=True)
    assert s._rec_info["call_app"] == "Teams"
    s._check_call(lambda: ["Teams"])
    assert s.state()["recording"]["call_over"] is None
    s._check_call(lambda: [])                              # Teams just released the microphone …
    assert s.state()["recording"]["call_over"] is None     # … but only for a moment so far
    s._rec_info["call_seen"] = time.monotonic() - 31
    s._check_call(lambda: [])
    assert s.state()["recording"]["call_over"] == "Teams"
    assert s.call_notifier.shown[-1][0] == "Der Teams-Call ist zu Ende – Aufnahme beenden?"
    assert s.state()["recording"] is not None              # still recording
    s.keep_recording()                                     # «Weiter aufnehmen»
    assert s.state()["recording"]["call_over"] is None
    s.stop_recording()


def test_no_question_without_a_call_at_the_start():
    import time
    s = _service([])
    s.start_recording(consent=True)                        # e.g. a meeting in the room
    s._rec_info["call_seen"] = time.monotonic() - 60
    s._check_call(lambda: [])
    assert s.state()["recording"]["call_over"] is None
    s.stop_recording()
