"""Recognise a call: a call app uses the microphone (Windows).

Windows notes in the registry which app uses the microphone right now – the same
information that drives the microphone icon in the taskbar:

    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone
    - packaged apps (new Teams: «MSTeams_8wekyb3d8bbwe») as subkeys
    - other programs below «NonPackaged»; the key name is the exe path with «#» instead of «\\»

An app uses the microphone while LastUsedTimeStart > 0 and LastUsedTimeStop == 0.
Nothing about the call itself is read.

Only known call apps count: dictation tools and audio mixers (e.g. Voicemeeter) use the
microphone all the time and would suggest a recording constantly. Verbalis itself is
never a call (its level meters open the microphone too).
"""

from __future__ import annotations

import sys
from typing import Iterable

KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

# program or package name (lower case, without «.exe» / publisher id) → name shown to the user
CALL_APPS = {
    "msteams": "Teams", "ms-teams": "Teams", "teams": "Teams",
    "zoom": "Zoom",
    "ciscocollabhost": "Webex", "webex": "Webex", "webexmta": "Webex", "atmgr": "Webex",
    "slack": "Slack", "com.tinyspeck.slackdesktop": "Slack",
    "skype": "Skype", "discord": "Discord",
    "chrome": "Browser", "msedge": "Browser", "firefox": "Browser", "brave": "Browser", "opera": "Browser",
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


def own_programs() -> list[str]:
    """Verbalis' own executables (also the Python behind a virtual environment)."""
    return [p for p in {sys.executable, getattr(sys, "_base_executable", "")} if p]


def detect() -> list[str]:
    return call_apps(registry_entries(), own_programs())
