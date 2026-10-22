"""Linux (experimental): call detection via pactl, notifications via notify-send, one app at a time."""

import sys
import threading
from types import SimpleNamespace

import pytest

from verbalis.audio.call_detect import call_apps, pulse_entries
from verbalis.notify import LinuxNotifier

PACTL = """Source Output #41
\tDriver: protocol-native.c
\tCorked: no
\tProperties:
\t\tapplication.name = "ZOOM VoiceEngine"
\t\tapplication.process.binary = "zoom"
Source Output #42
\tCorked: yes
\tProperties:
\t\tapplication.process.binary = "firefox"
Source Output #43
\tCorked: no
\tProperties:
\t\tapplication.process.binary = "python3.12"
"""


def test_pactl_lists_programs_using_the_microphone():
    calls = []

    def run(cmd, **kwargs):
        calls.append(kwargs["env"]["LC_ALL"])
        return SimpleNamespace(returncode=0, stdout=PACTL)

    entries = pulse_entries(run)
    assert entries == [("zoom", 1, 0), ("python3.12", 1, 0)]   # paused Firefox doesn't count
    assert calls == ["C"]                                       # English output, whatever the system language
    assert call_apps(entries) == ["Zoom"]


def test_no_pactl_means_no_call():
    def missing(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    assert pulse_entries(missing) == []
    assert pulse_entries(lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="")) == []


class FakeProcess:
    """notify-send --wait: prints the action on a click; `wait=True` stays open until terminated."""

    def __init__(self, output, wait=False):
        self.output, self.terminated = output, threading.Event()
        if not wait:
            self.terminated.set()

    def communicate(self):
        self.terminated.wait(5)
        return self.output, ""

    def poll(self):
        return None

    def terminate(self):
        self.terminated.set()


def test_click_on_linux_notification_opens_the_window(tmp_path):
    clicked, started = [], []

    def popen(cmd, **kwargs):
        started.append(cmd)
        return FakeProcess("default\n")

    n = LinuxNotifier(tmp_path / "icon.ico", lambda: clicked.append(1), popen=popen, which=lambda name: "/usr/bin/" + name)
    assert n.available
    n.show("Teams-Call erkannt – aufnehmen?", "Klicken, um Verbalis zu öffnen.")
    n._waiter.join(5)
    assert clicked == [1]
    assert started[0][0] == "notify-send" and "--wait" in started[0] and started[0][-2:] == [
        "Teams-Call erkannt – aufnehmen?", "Klicken, um Verbalis zu öffnen."]


def test_hide_closes_the_open_notification(tmp_path):
    process = FakeProcess("", wait=True)
    n = LinuxNotifier(tmp_path / "icon.ico", lambda: None, popen=lambda cmd, **kw: process, which=lambda name: name)
    n.show("Titel", "Text")
    n.hide()
    n._waiter.join(5)
    assert process.terminated.is_set() and not n._waiter.is_alive()


def test_without_notify_send_there_are_no_notifications(tmp_path):
    started = []
    n = LinuxNotifier(tmp_path / "icon.ico", lambda: None, popen=lambda cmd, **kw: started.append(cmd),
                      which=lambda name: None)
    n.show("Titel", "Text")
    assert not n.available and started == []


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl lock, Linux only")
def test_second_app_on_linux_is_refused(tmp_path):
    from verbalis import app

    lock = tmp_path / "app.lock"
    try:
        assert app._already_running("linux", lock) is False
        assert app._already_running("linux", lock) is True     # a second start while the first runs
    finally:
        app._MUTEX.close()
        app._MUTEX = None
    assert app._already_running("linux", lock) is False        # first app closed: the lock is free again
    app._MUTEX.close()
    app._MUTEX = None
