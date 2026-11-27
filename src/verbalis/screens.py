"""Screen snapshots during a recording (0.7.46).

While recording, the chosen monitor or window is looked at once per second. A picture is kept when the screen
differs clearly from the last kept one and has been still for a moment (a new slide, another section of a
document) – or, if it never comes to rest (video tiles), at most every MAX_WAIT_S. The pictures land in
`<recording>/screens/` named after their recording time (`00-07-45.png`), which is the time used in the
transcript; transcript.md links them at the right place, so Claude (Code) can relate comments to what was shown.

Small copies for the app's transcript view are in `screens/.thumbs/`.

Window capture works on Windows only (PrintWindow: also when the window is covered by others); other systems
offer the monitors. The pictures never leave the computer.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

FOLDER = "screens"
THUMBS = ".thumbs"
THUMB_WIDTH = 480
INTERVAL_S = 1.0
STILL_SAMPLES = 2        # unchanged for this many samples in a row = the screen came to rest
MAX_WAIT_S = 30.0        # a screen that never rests (video) is still kept, but at most this often
PIXEL_STEP = 24          # grey-level difference that counts as a changed pixel
CHANGED_SHARE = 0.03     # share of changed pixels for «a different picture»
STILL_SHARE = 0.01       # less change than this between two samples = still
# Areas that keep moving (the video tiles of the people in a Teams call next to the shared screen) are left out of
# both comparisons: per pixel, how often it changed recently (moving average); above BUSY it is ignored. A pixel that
# changes every second is ignored after 2 seconds; a slide change (once) never reaches it.
ACTIVITY_WEIGHT = 0.2
BUSY = 0.3
MIN_STEADY = 0.05        # if almost everything moves (a full-screen video), compare everything again

MONITOR = "monitor:"
WINDOW = "window:"
_NAME = re.compile(r"^(\d+)-(\d\d)-(\d\d)(?:_\d+)?\.png$")


# ------------------------------------------------------------------ what can be captured

# Meeting windows, recognised by their title. The new Teams names every window «… | Microsoft Teams»; its main
# window starts with the section shown (Chat, Calendar …), a call window with the meeting's name or «Meeting».
TEAMS = "microsoft teams"
TEAMS_SECTIONS = {"activity", "aktivität", "chat", "teams", "calendar", "kalender", "calls", "anrufe", "apps",
                  "onedrive", "files", "dateien", "community", "communities", "copilot", "people", "personen",
                  "assignments", "aufgaben", "planner", "approvals", "genehmigungen", "settings", "einstellungen",
                  "notifications", "benachrichtigungen", "home", "start"}
_MEET = re.compile(r"^Meet\s+[-–]\s")   # Google Meet in a browser: «Meet – abc-defg-hij - Google Chrome»
_APPS = ("zoom", "webex", "3cx", "skype", "jitsi", "whereby", "gotomeeting", "goto meeting")


def meeting_kind(title: str) -> str | None:
    """«call» for a window that shows a running call, «app» for another window of a meeting program, else None."""
    low = title.lower()
    if low.endswith(TEAMS):
        first = low.split("|")[0].strip()
        return "app" if first in TEAMS_SECTIONS or first == TEAMS else "call"
    if _MEET.match(title):
        return "call"
    if low.startswith(("zoom meeting", "zoom webinar")) or "jitsi meet" in low:
        return "call"
    if any(app in low for app in _APPS):
        return "app"
    return None


def meeting_name(title: str) -> str:
    """What to call a call window in a hint: «Teams-Meeting», «Zoom-Meeting» …"""
    low = title.lower()
    if low.endswith(TEAMS):
        return "Teams-Meeting"
    if _MEET.match(title):
        return "Google-Meet"
    if "zoom" in low:
        return "Zoom-Meeting"
    return "Meeting"


def call_windows() -> list[dict]:
    """The windows of running calls (Windows only; elsewhere []): {value, label}, front-most first."""
    if sys.platform != "win32":
        return []
    return [m for m in group_windows([title for _, title in _win_windows()])["meetings"] if m["call"]]


def group_windows(titles: list[str]) -> dict:
    """Window titles as choices: meeting windows (calls first, otherwise in the given order) and the others."""
    meetings, windows = [], []
    for title in titles:
        kind = meeting_kind(title)
        entry = {"value": WINDOW + title, "label": title}
        if kind:
            meetings.append({**entry, "call": kind == "call"})
        else:
            windows.append(entry)
    meetings.sort(key=lambda m: not m["call"])   # stable: keeps the front-most-first order within each kind
    return {"meetings": meetings, "windows": windows}


def sources() -> dict:
    """The monitors and (Windows) the open windows, for the choice in the recording view.

    Meeting windows are listed apart (`meetings`, running calls first, each with `call`), the rest in `windows`.
    """
    result = {"monitors": [], "meetings": [], "windows": [], "windows_supported": sys.platform == "win32"}
    try:
        import mss

        with mss.mss() as sct:
            screens = sct.monitors[1:]
        for n, m in enumerate(screens, start=1):
            label = f"Ganzer Bildschirm {n} ({m['width']}×{m['height']})" if len(screens) > 1 \
                else f"Ganzer Bildschirm ({m['width']}×{m['height']})"
            result["monitors"].append({"value": f"{MONITOR}{n}", "label": label})
    except Exception as e:   # no display (CI, Linux without X/Wayland access)
        log.warning("Monitors could not be listed: %s", e)
    if sys.platform == "win32":
        try:
            result.update(group_windows([title for _, title in _win_windows()]))
        except Exception as e:
            log.warning("Windows could not be listed: %s", e)
    return result


def describe(target: str) -> str:
    """User-facing name of a choice, e.g. for messages."""
    if target.startswith(MONITOR):
        return f"Bildschirm {target[len(MONITOR):]}"
    if target.startswith(WINDOW):
        return f"Fenster «{target[len(WINDOW):]}»"
    return target


def open_grabber(target: str) -> Callable[[], np.ndarray | None]:
    """A function returning the current picture (height × width × 3, RGB) or None (window minimised).

    Raises RuntimeError (German) if the target does not exist. Must be called in the thread that grabs:
    mss keeps per-thread handles on Windows.
    """
    if target.startswith(MONITOR):
        import mss

        n = int(target[len(MONITOR):] or 1)
        sct = mss.mss()
        if not 1 <= n < len(sct.monitors):
            sct.close()
            raise RuntimeError(f"Bildschirm {n} gibt es nicht (mehr). Bitte «Geräte neu laden» und neu wählen.")
        monitor = sct.monitors[n]

        def grab() -> np.ndarray:
            shot = sct.grab(monitor)
            return np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)[:, :, 2::-1]
        grab.close = sct.close   # type: ignore[attr-defined]
        return grab
    if target.startswith(WINDOW):
        if sys.platform != "win32":
            raise RuntimeError("Einzelne Fenster aufnehmen geht nur unter Windows – bitte einen Bildschirm wählen.")
        title = target[len(WINDOW):]
        hwnd = find_window(title)
        if hwnd is None:
            raise RuntimeError(f"Das Fenster «{title}» gibt es nicht mehr. Bitte «Geräte neu laden» und neu wählen.")
        return lambda: _win_capture(hwnd)
    raise RuntimeError(f"Unbekannte Bildschirm-Auswahl: {target}")


def find_window(title: str) -> int | None:
    """The window with exactly this title, otherwise the first one whose title contains it."""
    windows = _win_windows()
    for hwnd, t in windows:
        if t == title:
            return hwnd
    for hwnd, t in windows:
        if title.lower() in t.lower():
            return hwnd
    return None


# ------------------------------------------------------------------ deciding which pictures to keep

def small(picture: np.ndarray) -> np.ndarray:
    """A coarse grey version for comparing (every 8th pixel)."""
    p = picture[::8, ::8].astype(np.int16)
    return (p[:, :, 0] * 3 + p[:, :, 1] * 6 + p[:, :, 2]) // 10


def changed_share(a: np.ndarray | None, b: np.ndarray | None, steady: np.ndarray | None = None) -> float:
    """Share of changed pixels; steady: only these pixels count (the ones that don't keep moving)."""
    if a is None or b is None or a.shape != b.shape:
        return 1.0
    changed = np.abs(a - b) > PIXEL_STEP
    if steady is not None and steady.shape == changed.shape and steady.mean() >= MIN_STEADY:
        return float(changed[steady].mean())
    return float(changed.mean())


class ChangeDetector:
    """Feed one coarse picture per sample; says when to keep the current picture and from which time.

    A picture is kept when it differs from the last kept one and the screen has been still for
    STILL_SAMPLES – or after MAX_WAIT_S of a screen that keeps changing. The time is the moment the
    change began, so the picture sits in the transcript before the talk about it. Areas that keep moving
    (video tiles) don't count for either (see BUSY).
    """

    def __init__(self) -> None:
        self.kept: np.ndarray | None = None
        self.previous: np.ndarray | None = None
        self.still = 0
        self.change_since: float | None = None
        self.kept_at: float | None = None
        self.activity: np.ndarray | None = None   # per pixel: how often it changed recently (0–1)

    def steady(self) -> np.ndarray | None:
        """The pixels that don't keep moving."""
        return None if self.activity is None else self.activity < BUSY

    def feed(self, picture: np.ndarray, t: float) -> float | None:
        """Returns the time to keep the picture under, or None."""
        steady = self.steady()
        different = changed_share(picture, self.kept, steady)
        # still: hardly any change since the last sample – compared with how much changed since the last kept
        # picture, so what is left of a video tile next to a new slide doesn't count as movement
        still = changed_share(picture, self.previous, steady) < max(STILL_SHARE, different / 4)
        if self.previous is not None and self.previous.shape == picture.shape:
            moved = (np.abs(picture - self.previous) > PIXEL_STEP).astype(np.float32)
            if self.activity is None:
                self.activity = np.zeros(picture.shape, np.float32)
            self.activity = self.activity * (1 - ACTIVITY_WEIGHT) + moved * ACTIVITY_WEIGHT
        else:
            self.activity = None   # first picture or the window changed size: learn anew
        self.previous = picture
        self.still = self.still + 1 if still else 0
        if different < CHANGED_SHARE:
            self.change_since = None
            return None
        if self.change_since is None:
            self.change_since = t
        waited = t - (self.kept_at if self.kept_at is not None else self.change_since)
        if self.still >= STILL_SAMPLES or waited >= MAX_WAIT_S:
            at = self.change_since
            self.kept, self.kept_at, self.change_since = picture, t, None
            return at
        return None


# ------------------------------------------------------------------ files

def file_name(seconds: float) -> str:
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h:02d}-{m:02d}-{s:02d}.png"


def listing(folder: Path) -> list[tuple[float, str]]:
    """(recording second, path relative to the recording folder) of all snapshots, in time order."""
    found = []
    for path in (folder / FOLDER).glob("*.png"):
        if m := _NAME.match(path.name):
            found.append((int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]), f"{FOLDER}/{path.name}"))
    return sorted(found)


def save(folder: Path, seconds: float, picture: np.ndarray) -> Path:
    """Write the picture (and its small copy for the app). Never overwrites an earlier one."""
    target = folder / FOLDER
    target.mkdir(parents=True, exist_ok=True)
    path = target / file_name(seconds)
    n = 1
    while path.exists():
        path = target / f"{file_name(seconds)[:-4]}_{n}.png"
        n += 1
    _write_with_thumb(path, picture)
    return path


def _write_with_thumb(path: Path, picture: np.ndarray) -> None:
    """The picture as PNG and its small copy in .thumbs/ next to it."""
    import mss.tools

    (path.parent / THUMBS).mkdir(parents=True, exist_ok=True)
    h, w = picture.shape[:2]
    mss.tools.to_png(np.ascontiguousarray(picture).tobytes(), (w, h), level=6, output=str(path))
    step = max(1, -(-w // THUMB_WIDTH))
    thumb = np.ascontiguousarray(picture[::step, ::step])
    mss.tools.to_png(thumb.tobytes(), (thumb.shape[1], thumb.shape[0]), level=6, output=str(path.parent / THUMBS / path.name))


def _remove_with_thumb(path: Path) -> None:
    path.unlink(missing_ok=True)
    (path.parent / THUMBS / path.name).unlink(missing_ok=True)


def read_png(path: Path) -> np.ndarray:
    """A snapshot written by `save` (8-bit RGB, no row filters – what mss writes) as height × width × 3."""
    import struct
    import zlib

    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name}: kein PNG")
    pos, chunks, w, h = 8, [], 0, 0
    while pos + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, color = struct.unpack(">IIBB", body[:10])
            if (depth, color) != (8, 2):
                raise ValueError(f"{path.name}: unerwartetes PNG-Format")
        elif kind == b"IDAT":
            chunks.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + n
    raw = np.frombuffer(zlib.decompress(b"".join(chunks)), np.uint8).reshape(h, 1 + w * 3)
    if raw[:, 0].any():
        raise ValueError(f"{path.name}: PNG mit Zeilenfiltern wird nicht gelesen")
    return raw[:, 1:].reshape(h, w, 3)


# ------------------------------------------------------------------ preparing the pictures for an AI (0.7.46)
#
# A recording of a Teams call keeps ~3 pictures a minute, most of them in-between states (clicking, scrolling),
# each showing the meeting's own bar, the people's video tiles and the taskbar too. Before «Für KI kopieren» the
# pictures are cut to the shared content and only the ones that were shown for a while are chosen; they land in
# screens_crop/, and transcript.md links those (the others are named as text). The originals stay as they were.
#
# The content area needs no text recognition: it is where the pictures differ from one another. The bar and the
# taskbar hardly change between two kept pictures, the video tiles rarely (they don't make pictures, see BUSY),
# the shared screen almost every time.

CROP_FOLDER = "screens_crop"
INDEX = "index.json"
MIN_SHOWN_S = 5          # shown for less = an in-between state while clicking or scrolling: not chosen
                         # (the default of the setting screen_min_s)
PROFILE_SHARE = 0.2      # a row/column belongs to the content if it changes at least this share of the busiest one
GAP_SHARE = 0.05         # gaps up to this share of the picture inside the content are bridged (a white slide area)
PAD_SHARE = 0.01


def _grey(picture: np.ndarray, step: int = 4) -> np.ndarray:
    p = picture[::step, ::step].astype(np.int16)
    return (p[:, :, 0] * 3 + p[:, :, 1] * 6 + p[:, :, 2]) // 10


def _span(profile: np.ndarray) -> tuple[int, int] | None:
    """The main stretch of a change profile: runs above PROFILE_SHARE of its top, small gaps bridged, the run with
    the most change."""
    top = profile.max()
    if top <= 0:
        return None
    above = np.flatnonzero(profile >= top * PROFILE_SHARE)
    gap = max(1, int(len(profile) * GAP_SHARE))
    runs = [[above[0], above[0]]]
    for i in above[1:]:
        if i - runs[-1][1] <= gap:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    start, end = max(runs, key=lambda r: profile[r[0]:r[1] + 1].sum())
    return int(start), int(end) + 1


def content_box(greys: list[np.ndarray]) -> tuple[float, float, float, float] | None:
    """(top, bottom, left, right) as shares of the picture: where pictures of the same size differ from the one
    before. None if there are too few pictures or the whole picture changes (nothing to cut away)."""
    if len(greys) < 3:
        return None
    count = np.zeros(greys[0].shape, np.int32)
    for a, b in zip(greys, greys[1:]):
        count += np.abs(a - b) > PIXEL_STEP
    rows, cols = _span(count.mean(axis=1)), _span(count.mean(axis=0))
    if rows is None or cols is None:
        return None
    h, w = count.shape
    top, bottom = max(0.0, rows[0] / h - PAD_SHARE), min(1.0, rows[1] / h + PAD_SHARE)
    left, right = max(0.0, cols[0] / w - PAD_SHARE), min(1.0, cols[1] / w + PAD_SHARE)
    area = (bottom - top) * (right - left)
    if area > 0.9 or area < 0.1:   # nothing worth cutting – or something odd: keep the whole picture
        return None
    return top, bottom, left, right


def _cut(picture: np.ndarray, box) -> np.ndarray:
    if box is None:
        return picture
    h, w = picture.shape[:2]
    return picture[int(box[0] * h):int(np.ceil(box[1] * h)), int(box[2] * w):int(np.ceil(box[3] * w))]


def choose(times: list[float], greys: list[np.ndarray], end_s: float | None,
           min_shown_s: float = MIN_SHOWN_S) -> list[str]:
    """For each picture (its cut, coarse grey version): "" chosen, "short" (shown less than min_shown_s) or the
    index of the earlier chosen picture it repeats (differs in less than CHANGED_SHARE), as text. If none would be
    chosen (a very short recording), the one shown longest is."""
    result, chosen = [], []
    for i, (t, grey) in enumerate(zip(times, greys)):
        until = times[i + 1] if i + 1 < len(times) else end_s
        same = next((j for j in chosen if changed_share(greys[j], grey) < CHANGED_SHARE), None)
        if same is not None:
            result.append(str(same))
        elif until is not None and until - t < min_shown_s:
            result.append("short")
        else:
            result.append("")
            chosen.append(i)
    if not chosen and times:
        shown = [(times[i + 1] if i + 1 < len(times) else (end_s or t)) - t for i, t in enumerate(times)]
        result[shown.index(max(shown))] = ""
    return result


#
# Choices by hand (0.7.49): the panel «Bilder» in the transcript view adds a left-out picture to the transcript or
# leaves a chosen one out. They are kept in index.json (`manual`: source → "in" / "out") and survive a new `prepare`
# (e.g. another min_shown_s). The automatic verdict stays in each entry (`short`, `same_as`; neither = chosen), so
# «back to automatic» (the undo) knows it; `file` is there exactly when the picture is in the transcript.

MANUAL_IN, MANUAL_OUT, AUTOMATIC = "in", "out", "auto"


def _read_index(folder: Path) -> dict | None:
    """index.json if it matches the pictures in screens/, else None (not prepared, or pictures added since)."""
    import json

    try:
        index = json.loads((folder / CROP_FOLDER / INDEX).read_text(encoding="utf-8"))
        if [p for _, p in listing(folder)] != [e["source"] for e in index["pictures"]]:
            return None
        index.setdefault("manual", {})
        index.setdefault("boxes", {})
        return index
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _write_index(folder: Path, index: dict) -> None:
    import json

    path = folder / CROP_FOLDER / INDEX
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=1), encoding="utf-8")
    tmp.replace(path)


def _shape_key(picture: np.ndarray) -> str:
    return f"{picture.shape[0]}x{picture.shape[1]}"


def _box_for(folder: Path, index: dict, picture: np.ndarray):
    """The content box for pictures of this size – from index.json, or worked out once (an index of 0.7.46–48)."""
    key = _shape_key(picture)
    if key not in index["boxes"]:
        same = [p for p in (read_png(folder / s) for s in (e["source"] for e in index["pictures"]))
                if p.shape == picture.shape]
        box = content_box([_grey(p) for p in same])
        index["boxes"][key] = list(box) if box else None
    return index["boxes"][key]


def _write_cut(folder: Path, source: str, box) -> str:
    """Cut the original `source` with `box` into screens_crop/; returns the path relative to the recording."""
    name = Path(source).name
    _write_with_thumb(folder / CROP_FOLDER / name, _cut(read_png(folder / source), box))
    return f"{CROP_FOLDER}/{name}"


def prepare(folder: Path, end_s: float | None = None, min_shown_s: float = MIN_SHOWN_S) -> bool:
    """Cut and choose the snapshots for an AI (screens_crop/ and its index.json). Does nothing if that is up to
    date with screens/ and min_shown_s; True if it was (re)done. Choices by hand are kept."""
    import json

    pictures = listing(folder)
    target = folder / CROP_FOLDER
    if not pictures:
        return False
    try:
        manual = dict(json.loads((target / INDEX).read_text(encoding="utf-8")).get("manual") or {})
    except (OSError, ValueError, AttributeError, TypeError):
        manual = {}
    current = _read_index(folder)
    if current is not None and current.get("min_shown_s") == min_shown_s:
        return False
    sources = [p for _, p in pictures]
    manual = {k: v for k, v in manual.items() if k in sources and v in (MANUAL_IN, MANUAL_OUT)}
    loaded = [read_png(folder / p) for p in sources]
    boxes = {}
    for shape in {p.shape for p in loaded}:
        boxes[shape] = content_box([_grey(p) for p in loaded if p.shape == shape])
    cut = [_cut(p, boxes[p.shape]) for p in loaded]
    verdicts = choose([t for t, _ in pictures], [_grey(c) for c in cut], end_s, min_shown_s)
    target.mkdir(exist_ok=True)
    for stale in [*target.glob("*.png"), *(target / THUMBS).glob("*.png")]:
        stale.unlink()
    entries = []
    for (t, source), picture, verdict in zip(pictures, cut, verdicts):
        entry = {"t": t, "source": source}
        if verdict == "short":
            entry["short"] = True
        elif verdict:
            entry["same_as"] = pictures[int(verdict)][0]
        if source in manual:
            entry["manual"] = manual[source]
        if manual.get(source, MANUAL_IN if verdict == "" else MANUAL_OUT) == MANUAL_IN:
            name = Path(source).name
            _write_with_thumb(target / name, picture)
            entry["file"] = f"{CROP_FOLDER}/{name}"
        entries.append(entry)
    _write_index(folder, {"min_shown_s": min_shown_s, "manual": manual,
                          "boxes": {_shape_key(p): (list(boxes[p.shape]) if boxes[p.shape] else None) for p in loaded},
                          "pictures": entries})
    log.info("Snapshots of %s prepared: %d of %d chosen%s", folder.name, sum("file" in e for e in entries),
             len(entries), f", {len(manual)} by hand" if manual else "")
    return True


def choose_by_hand(folder: Path, sources: list[str], choice: str) -> int:
    """«ins Transkript» (MANUAL_IN), «weglassen» (MANUAL_OUT) or back to the automatic choice (AUTOMATIC, the undo)
    for these pictures. Returns how many changed. Needs prepared pictures (`prepare`)."""
    if choice not in (MANUAL_IN, MANUAL_OUT, AUTOMATIC):
        raise ValueError(f"Unbekannte Auswahl «{choice}».")
    index = _read_index(folder)
    if index is None:
        raise RuntimeError("Die Bilder sind noch nicht vorbereitet – bitte das Transkript neu öffnen.")
    wanted, changed = set(sources), 0
    for e in index["pictures"]:
        source = e["source"]
        if source not in wanted:
            continue
        if choice == AUTOMATIC:
            index["manual"].pop(source, None)
            e.pop("manual", None)
            use = not e.get("short") and "same_as" not in e
        else:
            index["manual"][source] = e["manual"] = choice
            use = choice == MANUAL_IN
        if use and "file" not in e:
            e["file"] = _write_cut(folder, source, _box_for(folder, index, read_png(folder / source)))
            changed += 1
        elif not use and "file" in e:
            _remove_with_thumb(folder / e.pop("file"))
            changed += 1
    _write_index(folder, index)
    log.info("Snapshots of %s: %d changed by hand (%s)", folder.name, changed, choice)
    return changed


def delete(folder: Path, sources: list[str]) -> int:
    """Delete these snapshots for good: original, small copy, cut copy, entry. Returns how many were deleted."""
    known = {p for _, p in listing(folder)}
    index = _read_index(folder)
    gone = []
    for source in sources:
        if source not in known:
            continue
        name = Path(source).name
        _remove_with_thumb(folder / FOLDER / name)
        _remove_with_thumb(folder / CROP_FOLDER / name)
        gone.append(source)
    if index is not None:   # still matches the pictures that are left
        index["pictures"] = [e for e in index["pictures"] if e["source"] not in gone]
        for source in gone:
            index["manual"].pop(source, None)
        _write_index(folder, index)
    log.info("Snapshots of %s: %d deleted by hand", folder.name, len(gone))
    return len(gone)


REASONS = {"short": "nur kurz gezeigt", "manual": "von Hand weggelassen"}


def _reason(e: dict) -> str:
    """Why a picture is not in the transcript: "manual", "short" or "same"; "" if it is."""
    if "file" in e:
        return ""
    if e.get("manual") == MANUAL_OUT:
        return "manual"
    return "same" if "same_as" in e else "short"


def overview(folder: Path) -> list[dict]:
    """All snapshots for the panel «Bilder»: t, source (original), file (what the transcript shows: the cut copy;
    the original if not prepared), used, reason ("", "short", "same", "manual"), same_as, manual (by hand: in/out)."""
    index = _read_index(folder)
    if index is None:
        return [{"t": t, "source": p, "file": p, "used": True, "reason": "", "same_as": None, "manual": None}
                for t, p in listing(folder)]
    return [{"t": e["t"], "source": e["source"], "file": e.get("file"), "used": "file" in e, "reason": _reason(e),
             "same_as": e.get("same_as"), "manual": e.get("manual")} for e in index["pictures"]]


def for_transcript(folder: Path) -> list[tuple[float, str, str]]:
    """The snapshots for transcript.md: (second, path, note). Prepared: the chosen ones from screens_crop/ with an
    empty note, the others from screens/ with why they were left out. Not (yet) prepared: all originals."""
    from .transcript import _time

    result = []
    for p in overview(folder):
        if p["used"]:
            result.append((p["t"], p["file"], ""))
        elif p["reason"] == "same":
            result.append((p["t"], p["source"], f"gleich wie {_time(p['same_as'])}"))
        else:
            result.append((p["t"], p["source"], REASONS[p["reason"]]))
    return result


def image_path(folder: Path, relative: str, thumb: bool = False) -> Path:
    """A snapshot file of this recording (original in screens/ or cut copy in screens_crop/) – only names like
    `listing` gives, no paths elsewhere."""
    name = Path(relative).name
    sub = next((f for f in (FOLDER, CROP_FOLDER) if relative == f"{f}/{name}"), None)
    if not _NAME.match(name) or sub is None:
        raise RuntimeError("Unbekanntes Bild.")
    path = folder / sub / THUMBS / name if thumb else folder / sub / name
    if thumb and not path.exists():
        path = folder / sub / name
    return path


# ------------------------------------------------------------------ the capture thread

class ScreenCapture:
    """Grabs the target once per INTERVAL_S while recording. position() is the recording time without pauses,
    or None while paused (nothing is kept then)."""

    def __init__(self, folder: Path, target: str, position: Callable[[], float | None],
                 opener: Callable[[str], Callable] = open_grabber, interval_s: float = INTERVAL_S):
        self.folder = folder
        self.target = target
        self.position = position
        self.opener = opener
        self.interval_s = interval_s
        self.count = 0
        self.problem: str | None = None
        self.paused = False   # «Bilder pausieren»: the audio goes on, no pictures (0.7.49)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="screens")

    def start(self, wait_s: float = 5.0) -> None:
        """Start and wait until the target is open – a wrong choice raises here, before the recording runs."""
        self._thread.start()
        self._ready.wait(wait_s)
        if self.problem and not self._thread.is_alive():
            raise RuntimeError(self.problem)

    def stop(self, wait_s: float = 5.0) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(wait_s)

    def _run(self) -> None:
        try:
            grab = self.opener(self.target)
        except Exception as e:
            self.problem = str(e) or type(e).__name__
            self._ready.set()
            return
        self._ready.set()
        detector = ChangeDetector()
        failures = 0
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                t = None if self.paused else self.position()
                if t is None:   # paused: a change that began before does not date a picture after it
                    detector.change_since, detector.still = None, 0
                else:
                    try:
                        picture = grab()
                        failures = 0
                    except _WindowGone:
                        self.problem = f"{describe(self.target)} wurde geschlossen – keine weiteren Schnappschüsse."
                        log.info("Screen capture %s: window gone", self.folder.name)
                        return
                    except Exception:
                        failures += 1
                        if failures in (1, 30):
                            log.exception("Screen capture of %s failed", self.folder.name)
                        picture = None
                    if picture is not None:
                        at = detector.feed(small(picture), t)
                        if at is not None:
                            try:
                                save(self.folder, at, picture)
                                self.count += 1
                            except OSError as e:
                                self.problem = f"Schnappschuss konnte nicht gespeichert werden ({e})."
                                log.exception("Saving a snapshot of %s failed", self.folder.name)
                self._stop.wait(max(0.05, self.interval_s - (time.monotonic() - started)))
        finally:
            close = getattr(grab, "close", None)
            if close:
                close()
            log.info("Screen capture of %s ended: %d snapshots", self.folder.name, self.count)


# ------------------------------------------------------------------ Windows: windows and PrintWindow

class _WindowGone(Exception):
    pass


def _win_windows() -> list[tuple[int, str]]:
    """Visible top-level windows with a title (not cloaked, not tool windows), front-most first."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    found: list[tuple[int, str]] = []
    GWL_EXSTYLE, WS_EX_TOOLWINDOW, DWMWA_CLOAKED = -20, 0x80, 14
    user32.GetWindowLongW.restype = ctypes.c_long

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        cloaked = wintypes.DWORD()
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.strip() and buf.value not in ("Program Manager",):
                found.append((int(hwnd or 0), buf.value))
        return True

    user32.EnumWindows(visit, 0)
    return found


def _win_capture(hwnd: int) -> np.ndarray | None:
    """The window's picture via PrintWindow (PW_RENDERFULLCONTENT: also browsers/Teams, also when covered).
    None while minimised; _WindowGone once it is closed."""
    import ctypes
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    for f in (user32.GetWindowDC, gdi32.CreateCompatibleDC, gdi32.CreateCompatibleBitmap, gdi32.SelectObject):
        f.restype = ctypes.c_void_p
    user32.GetWindowDC.argtypes = [ctypes.c_void_p]
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_uint]
    if not user32.IsWindow(ctypes.c_void_p(hwnd)):
        raise _WindowGone()
    if user32.IsIconic(ctypes.c_void_p(hwnd)):
        return None
    rect = wintypes.RECT()
    user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, w, h)
    old = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, 2):   # 2 = PW_RENDERFULLCONTENT
            return None
        info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(memory_dc, bitmap, 0, h, buf, ctypes.byref(info), 0):
            return None
        return np.frombuffer(buf.raw, np.uint8).reshape(h, w, 4)[:, :, 2::-1]
    finally:
        gdi32.SelectObject(memory_dc, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
