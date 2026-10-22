"""Recognise a call: a call app uses the microphone (Windows, Linux).

Windows notes in the registry which app uses the microphone right now – the same
information that drives the microphone icon in the taskbar:

    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone
    - packaged apps (new Teams: «MSTeams_8wekyb3d8bbwe») as subkeys
    - other programs below «NonPackaged»; the key name is the exe path with «#» instead of «\\»

An app uses the microphone while LastUsedTimeStart > 0 and LastUsedTimeStop == 0.
Nothing about the call itself is read.

Linux (experimental): PipeWire/PulseAudio list every program recording from a
microphone as a «source output» (`pactl list source-outputs`); paused ones are «corked».

Only known call apps count: dictation tools and audio mixers (e.g. Voicemeeter) use the
microphone all the time and would suggest a recording constantly. Verbalis itself is
never a call (its level meters open the microphone too).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Callable, Iterable

KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

# program or package name (lower case, without «.exe» / publisher id) → name shown to the user
CALL_APPS = {
    "msteams": "Teams", "ms-teams": "Teams", "teams": "Teams",
    "zoom": "Zoom",
    "ciscocollabhost": "Webex", "webex": "Webex", "webexmta": "Webex", "atmgr": "Webex",
    "slack": "Slack", "com.tinyspeck.slackdesktop": "Slack",
    "skype": "Skype", "discord": "Discord",
    "chrome": "Browser", "msedge": "Browser", "firefox": "Browser", "brave": "Browser", "opera": "Browser",
    # Linux program names
    "teams-for-linux": "Teams", "zoom.real": "Zoom", "discord.real": "Discord",
    "chromium": "Browser", "chromium-browser": "Browser", "firefox-bin": "Browser", "msedge-beta": "Browser",
}


def _program(key_name: str) -> str:
    """«MSTeams_8wekyb3d8bbwe» → «msteams», «C:#Program Files#Zoom#bin#Zoom.exe» → «zoom»."""
    name = key_name.rsplit("#", 1)[-1].lower()
    if name.endswith(".exe"):
        return name[:-4]
    return name.split("_", 1)[0]   # packaged app: name_publisherid


def call_apps(entries: Iterable[tuple[str, int, int]], own: Iterable[str] = ()) -> list[str]:
    """Names of call apps using the microphone. entries: (key name, LastUsedTimeStart, LastUsedTimeStop)."""
    ignore = {path.lower().replace("\\", "#").replace("/", "#") for path in own if path}
    found: list[str] = []
    for key_name, start, stop in entries:
        if not start or stop or key_name.lower() in ignore:
            continue
        app = CALL_APPS.get(_program(key_name))
        if app and app not in found:
            found.append(app)
    return found


def registry_entries() -> list[tuple[str, int, int]]:
    """The microphone entries of the current user; empty on other systems or on errors."""
    if sys.platform != "win32":
        return []
    import winreg

    entries: list[tuple[str, int, int]] = []

    def read(path: str) -> None:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                name = winreg.EnumKey(key, i)
                if name == "NonPackaged":
                    read(path + "\\" + name)
                    continue
                try:
                    with winreg.OpenKey(key, name) as sub:
                        start = winreg.QueryValueEx(sub, "LastUsedTimeStart")[0]
                        stop = winreg.QueryValueEx(sub, "LastUsedTimeStop")[0]
                except OSError:
                    continue
                entries.append((name, int(start or 0), int(stop or 0)))

    try:
        read(KEY)
    except OSError:
        return []
    return entries


def pulse_entries(run: Callable = subprocess.run) -> list[tuple[str, int, int]]:
    """Programs recording from a microphone right now (Linux); empty on errors (e.g. no pactl).

    Same shape as registry_entries(): (program name, 1, 0) for every source output that isn't paused.
    """
    try:
        result = run(["pactl", "list", "source-outputs"], capture_output=True, text=True, timeout=5,
                     check=False, env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    entries: list[tuple[str, int, int]] = []
    # one block per source output, starting with an unindented «Source Output #12»
    for block in re.split(r"^(?=\S)", result.stdout, flags=re.M):
        if re.search(r"^\s*Corked:\s*yes", block, flags=re.M):
            continue
        program = re.search(r'application\.process\.binary = "([^"]*)"', block)
        if program:
            entries.append((program.group(1), 1, 0))
    return entries


def own_programs() -> list[str]:
    """Verbalis' own executables (also the Python behind a virtual environment)."""
    return [p for p in {sys.executable, getattr(sys, "_base_executable", "")} if p]


def detect() -> list[str]:
    entries = pulse_entries() if sys.platform.startswith("linux") else registry_entries()
    return call_apps(entries, own_programs())
