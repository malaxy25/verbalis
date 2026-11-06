"""Keeping the computer awake while recording and processing (awake.py, 0.7.45)."""

import logging

from verbalis import awake
from verbalis.settings import Settings
from test_service import make_service, wait_until


class FakeBackend:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def apply(self, system, display):
        if self.fail:
            raise OSError("kein Zugriff")
        self.calls.append((system, display))


def test_only_changes_reach_the_system():
    backend = FakeBackend()
    keep = awake.KeepAwake(backend)
    keep.set(False, False)                 # already so: nothing to do
    keep.set(True, False)
    keep.set(True, False)
    keep.set(False, True)                  # a screen kept on keeps the system on too
    keep.set(False, False)
    assert backend.calls == [(True, False), (True, True), (False, False)]


def test_a_failing_sleep_lock_never_disturbs_the_recording(caplog):
    """No sleep lock possible (e.g. a locked-down PC): logged once, the recording goes on."""
    keep = awake.KeepAwake(FakeBackend(fail=True))
    with caplog.at_level(logging.ERROR):
        keep.set(True, True)
        keep.set(True, False)
    assert keep.state == (False, False)
    assert len([r for r in caplog.records if "awake" in r.getMessage()]) == 1


def test_the_helper_process_ends_with_verbalis():
    """macOS and Linux: the helper that holds the lock watches Verbalis' process – a crash must not leave the
    computer unable to sleep."""
    assert awake.mac_command(True, False, 42) == ["/usr/bin/caffeinate", "-i", "-w", "42"]
    assert "-d" in awake.mac_command(True, True, 42)
    linux = awake.linux_command(True, False, 42)
    assert "--what=sleep" in linux and linux[-4:] == ["tail", "--pid=42", "-f", "/dev/null"]
    assert "--what=sleep:idle" in awake.linux_command(True, True, 42)


def test_no_backend_means_nothing_happens(monkeypatch):
    keep = awake.KeepAwake()                # default_backend is None in tests (conftest)
    keep.set(True, True)
    assert keep.state == (True, True)


class FakeKeepAwake:
    def __init__(self):
        self.state = (False, False)

    def set(self, system, display):
        self.state = (bool(system or display), bool(display))


def test_awake_while_recording_with_the_screen_on_by_default(monkeypatch):
    """5 Nov 2026: a 2:50 h meeting on site – the computer must not sleep and the screen should stay on,
    to click the names in «Wer spricht gerade?»."""
    assert Settings().keep_display_on == "on"
    monkeypatch.setattr("verbalis.service.Service.AWAKE_CHECK_S", 0.02)
    keep = FakeKeepAwake()
    s = make_service(auto_transcribe="off", keep_awake=keep)
    assert wait_until(lambda: keep.state == (False, False))
    s.start_recording(consent=True)
    assert wait_until(lambda: keep.state == (True, True))
    s.pause_recording()                                   # a break in the meeting: it goes on afterwards
    assert not wait_until(lambda: keep.state != (True, True), timeout=0.2)
    s.resume_recording()
    s.save_settings({"keep_display_on": "off"})
    assert wait_until(lambda: keep.state == (True, False))
    s.stop_recording()
    assert wait_until(lambda: keep.state == (False, False))   # waits for the number of people: may sleep


def test_awake_while_transcribing(monkeypatch):
    monkeypatch.setattr("verbalis.service.Service.AWAKE_CHECK_S", 0.02)
    keep = FakeKeepAwake()
    s = make_service(auto_transcribe="off", keep_awake=keep)
    rid = s.start_recording(consent=True)
    s.stop_recording()
    s._job = {"id": rid, "kind": "transcribe"}            # what the worker sets while it transcribes
    assert wait_until(lambda: keep.state == (True, False))
    s._job = None
    assert wait_until(lambda: keep.state == (False, False))


def test_invalid_screen_setting_falls_back_to_on():
    assert Settings.from_dict({"keep_display_on": "vielleicht"}).keep_display_on == "on"
