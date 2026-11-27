"""Settings, stored in ~/.verbalis/settings.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .transcription.models import DEFAULT_MODEL, verbalis_home

QUALITY_BEAM = {"accurate": 5, "fast": 1}

# «Für KI kopieren» in the transcript menu (Claude Code or another AI that reads files): one entry per instruction
# (name, text). The whole text is visible in the settings; Service.ai_prompt fills the placeholders and drops a line
# whose placeholders are all empty. The defaults carry an id, so each one can be put back on its own.
PROMPT_INTRO = """Lies das Transkript {transkript}.
{bilder}
Das Transkript ist aus Schweizerdeutsch übersetzt, Fachbegriffe sind teils verhört. Korrigiere sie anhand der \
Bilder und des Zusammenhangs.

Aufnahme: {titel} ({datum}, {dauer})
Projekt: {projekt}
Teilnehmende: {teilnehmende}
Notizen: {notizen}
"""
DEFAULT_PROMPTS = [
    {"id": "meeting", "name": "Meeting",
     "text": PROMPT_INTRO + "\nFasse die Besprechung als Meeting zusammen und lege es unter dem Projekt im Vault ab. "
                            "Nur ausdrücklich Entschiedenes als Entscheid notieren, Vorschläge als Vorschlag. "
                            "Personennamen nicht korrigieren."},
    {"id": "training", "name": "Schulung",
     "text": PROMPT_INTRO + "\nFasse die Besprechung nach Themen zusammen."},
]
DEFAULT_IDS = {p["id"] for p in DEFAULT_PROMPTS}


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
    screen: str = ""                  # screen snapshots while recording: "" off, "monitor:N", "window:<title>"
    screen_min_s: str = "5"           # pictures for the AI: only those shown at least N seconds (0 = all but repeats)
    screen_start: str = "auto"        # "auto" = pictures from the start, "click" = only after «Bilder starten» (0.7.49)
    sidebar: str = "open"            # the recording list: "open" or "closed" (a narrow rail; Ctrl/Cmd+B)
    window_size: str = ""             # last window size, e.g. "1180x700"
    audio_days: str = "3"             # delete audio after N days; empty = never, 0 = right after transcription
    audio_max_mb: str = ""            # all audio at most N MB; empty = unlimited
    update_check: str = "on"          # "on" = ask GitHub for a newer version at start, "off"
    model_auto_update: str = "off"    # "on" = take newer model files automatically before transcribing
    diarize_others: str = "on"        # tell the others apart (Gegenüber 1, 2, …)
    diarize_me: str = "off"           # tell speakers apart on the own microphone (meetings in a room)
    speaker_split: str = "normal"     # "normal" or "fewer" (a higher clustering threshold: fewer speakers)
    asides: str = "on"                # "on" = short interjections in a column next to the paragraph
    call_detection: str = "on"        # "on" = suggest recording when a call app uses the microphone
    max_recording_min: str = "120"    # end a recording after N minutes (notice 5 min before); empty = never
    auto_transcribe: str = "off"      # "on" = transcribe right after recording; "off" = start it by hand
                                      # (after entering the number of people)
    live_transcribe: str = "on"       # "on" = transcribe already while recording (live.py; on since 0.7.42)
    experimental: str = "on"          # "on" = show features marked «Beta» (BETA in index.html)
    keep_display_on: str = "on"       # "on" = the screen stays on while recording (awake.py; since 0.7.45)
    ai_prompts: str = ""              # JSON list of {"name", "text"}; empty = DEFAULT_PROMPTS
    last_seen_version: str = ""       # version whose «what's new» was shown last
    tour: str = ""                    # "done" once the introduction was finished or closed

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
    def max_recording_s(self) -> float | None:
        return int(self.max_recording_min) * 60 if self.max_recording_min and int(self.max_recording_min) else None

    @property
    def min_shown_s(self) -> int:
        return int(self.screen_min_s)

    @property
    def prompts(self) -> list[dict]:
        if not self.ai_prompts:
            return [dict(p) for p in DEFAULT_PROMPTS]
        return json.loads(self.ai_prompts)

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
        if s.asides not in ("on", "off"):
            s.asides = "on"
        if s.speaker_split not in ("normal", "fewer"):
            s.speaker_split = "normal"
        if s.auto_transcribe not in ("on", "off"):
            s.auto_transcribe = "off"
        if s.live_transcribe not in ("on", "off"):
            s.live_transcribe = "off"
        if s.experimental not in ("on", "off"):
            s.experimental = "on"
        if s.keep_display_on not in ("on", "off"):
            s.keep_display_on = "on"
        s.ai_prompts = _clean_prompts(s.ai_prompts)
        if s.sidebar not in ("open", "closed"):
            s.sidebar = "open"
        if s.screen and not s.screen.startswith(("monitor:", "window:")):
            s.screen = ""
        if not (s.screen_min_s.isdigit() and int(s.screen_min_s) <= 600):
            s.screen_min_s = "5"
        s.screen_min_s = str(int(s.screen_min_s))   # «05» → «5»
        if s.screen_start not in ("auto", "click"):
            s.screen_start = "auto"
        if s.call_detection not in ("on", "off"):
            s.call_detection = "on"
        for name, default in (("audio_days", "3"), ("audio_max_mb", ""), ("max_recording_min", "120")):
            value = getattr(s, name)
            if value and not (value.isdigit() and int(value) < 100_000):
                setattr(s, name, default)  # invalid input → default
        return s

    def save(self) -> None:
        self.path().parent.mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def as_dict(self) -> dict:
        return {**asdict(self), "recordings_path": str(self.recordings), "prompts": self.prompts,
                "default_prompts": DEFAULT_PROMPTS, "prompt_intro": PROMPT_INTRO, "storage_warning": sync_warning(self.recordings)}


def _clean_prompts(value: str) -> str:
    """Only entries with a name or a text, as JSON; empty for invalid input or the defaults unchanged."""
    if not value:
        return ""
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, list):
        return ""
    prompts = []
    for p in data:
        if not isinstance(p, dict):
            continue
        entry = {"name": str(p.get("name") or "").strip()[:60], "text": str(p.get("text") or "").strip()[:5000]}
        if "id" not in p and entry["text"] and "{" not in entry["text"]:
            # saved before the placeholders were visible (only the instruction; the details were added unseen):
            # show the details as placeholders, and a delivered entry gets its id («Standard») back
            entry["text"] = PROMPT_INTRO + "\n" + entry["text"]
            default = next((d for d in DEFAULT_PROMPTS if d["name"] == entry["name"]), None)
            if default:
                entry = {"id": default["id"], **entry}
        if p.get("id") in DEFAULT_IDS:   # a default entry, perhaps changed: «Standard» can put it back
            entry = {"id": p["id"], **entry}
        if entry["name"] or entry["text"]:
            prompts.append(entry)
    if [{**p, "text": p["text"].strip()} for p in DEFAULT_PROMPTS] == prompts:
        prompts = DEFAULT_PROMPTS
    if prompts == DEFAULT_PROMPTS:
        return ""   # the defaults stay «defaults» (a better default text later reaches everybody)
    return json.dumps(prompts, ensure_ascii=False)


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
