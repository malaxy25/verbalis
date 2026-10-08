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
        for name, default in (("audio_days", "3"), ("audio_max_mb", "")):
            value = getattr(s, name)
            if value and not (value.isdigit() and int(value) < 100_000):
                setattr(s, name, default)  # invalid input → default
        return s

    def save(self) -> None:
        self.path().parent.mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def as_dict(self) -> dict:
        return {**asdict(self), "recordings_path": str(self.recordings)}
