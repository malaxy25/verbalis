"""Settings, stored in ~/.verbalis/settings.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .transcription.models import DEFAULT_MODEL, verbalis_home

QUALITY_BEAM = {"accurate": 5, "fast": 1}


@dataclass
class Settings:
    name: str = "Ich"                 # display name of the microphone track (user-facing)
    others: str = "Gegenüber"         # display name of the system audio track
    model: str = DEFAULT_MODEL
    quality: str = "accurate"         # "accurate" (beam 5) or "fast" (beam 1)
    keywords: str = ""
    recordings_dir: str = ""          # empty = ~/.verbalis/recordings
    microphone: str = ""              # empty = system default
    speakers: str = ""                # output device whose loopback is recorded
    window_size: str = ""             # last window size, e.g. "1180x700"
    audio_days: str = "3"             # delete audio after N days; empty = never, 0 = right after transcription
    audio_max_mb: str = ""            # all audio at most N MB; empty = unlimited
    update_check: str = "on"          # "on" = ask GitHub for a newer version at start, "off"
    model_auto_update: str = "off"    # "on" = take newer model files automatically before transcribing
    diarize_others: str = "on"        # tell the others apart (Gegenüber 1, 2, …)
    diarize_me: str = "off"           # tell speakers apart on the own microphone (meetings in a room)
    last_seen_version: str = ""       # version whose «what's new» was shown last

    @property
    def recordings(self) -> Path:
        return Path(self.recordings_dir).expanduser() if self.recordings_dir else verbalis_home() / "recordings"

    @property
    def days(self) -> int | None:
        return int(self.audio_days) if self.audio_days else None

    @property
    def max_mb(self) -> int | None:
        return int(self.audio_max_mb) if self.audio_max_mb else None

    @property
    def beam_size(self) -> int:
        return QUALITY_BEAM.get(self.quality, 5)

    @classmethod
    def path(cls) -> Path:
        return verbalis_home() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        values = {k: str(v).strip() for k, v in data.items() if k in known and v is not None}
        s = cls(**values)
        if s.quality not in QUALITY_BEAM:
            s.quality = "accurate"
        s.name = s.name or "Ich"
        s.others = s.others or "Gegenüber"
        s.model = s.model or DEFAULT_MODEL
        if s.update_check not in ("on", "off"):
            s.update_check = "on"
        if s.model_auto_update not in ("on", "off"):
            s.model_auto_update = "off"
        if s.diarize_others not in ("on", "off"):
            s.diarize_others = "on"
        if s.diarize_me not in ("on", "off"):
            s.diarize_me = "off"
        for name, default in (("audio_days", "3"), ("audio_max_mb", "")):
            value = getattr(s, name)
            if value and not (value.isdigit() and int(value) < 100_000):
                setattr(s, name, default)  # invalid input → default
        return s

    def save(self) -> None:
        self.path().parent.mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def as_dict(self) -> dict:
        return {**asdict(self), "recordings_path": str(self.recordings),
                "storage_warning": sync_warning(self.recordings)}


SYNC_FOLDERS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud", "mobile documents",
                "nextcloud", "owncloud", "sharepoint", "box sync", "pcloud")


def sync_warning(path: Path) -> str | None:
    """Warn when recordings would land in a folder that a cloud service synchronises.

    Verbalis itself uploads nothing – but OneDrive & co. would copy confidential
    calls to the cloud without anybody noticing.
    """
    lowered = [part.lower() for part in Path(path).expanduser().parts]
    for part in lowered:
        for name in SYNC_FOLDERS:
            if part == name or part.startswith(name + " ") or part.startswith(name + "-"):
                return (f"Der Aufnahmeordner liegt in einem synchronisierten Ordner ({Path(path).name} in «{part}»). "
                        "Aufnahmen würden so in die Cloud kopiert – für vertrauliche Gespräche einen lokalen Ordner wählen.")
    return None
