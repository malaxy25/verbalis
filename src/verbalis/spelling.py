"""Spell checking while correcting a transcript.

Uses the Swiss German Hunspell dictionary of LibreOffice (de_CH, «ss» instead
of «ß») via spylls, a pure-Python Hunspell implementation. Checking a word
takes milliseconds; suggestions are cut off after a time limit because the
slow n-gram phase can take seconds for badly garbled words.

The dictionary is GPL licensed, so it is not part of this MIT project: it is
downloaded on first use into ~/.verbalis/dictionaries/ (like the models).

Words the user marks as correct go to ~/.verbalis/words.txt. Keywords and
correction-list targets count as correct too (e.g. «tocco»).
"""

from __future__ import annotations

import logging
import re
import threading
import time
import urllib.request
from pathlib import Path

from .transcription.models import verbalis_home

log = logging.getLogger(__name__)

DICTIONARY = "de_CH_frami"
SOURCE = "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/de/"
FILES = (f"{DICTIONARY}.aff", f"{DICTIONARY}.dic", "README_de_DE_frami.txt")
WORD = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*")
QUIET_S = 0.25  # stop searching once no new suggestion came for this long


def dictionary_dir() -> Path:
    return verbalis_home() / "dictionaries"


def personal_words_path() -> Path:
    return verbalis_home() / "words.txt"


class Speller:
    """Loads the dictionary in the background; status: idle → loading → ready | error."""

    def __init__(self, folder: Path | None = None, download: bool = True):
        self.folder = folder
        self.download = download
        self.status = "idle"
        self.error: str | None = None
        self._dictionary = None
        self._cache: dict[str, bool] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ loading

    def _folder(self) -> Path:
        return self.folder or dictionary_dir()

    def start(self) -> None:
        with self._lock:
            if self.status != "idle":
                return
            self.status = "loading"
        threading.Thread(target=self._load, name="spelling", daemon=True).start()

    def load_now(self) -> None:
        """Synchronous variant (tests, CLI)."""
        self.status = "loading"
        self._load()

    def _download(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for name in FILES:
            target = folder / name
            if target.exists():
                continue
            tmp = target.with_suffix(target.suffix + ".tmp")
            with urllib.request.urlopen(SOURCE + name, timeout=60) as response:
                tmp.write_bytes(response.read())
            tmp.replace(target)
        log.info("Dictionary %s downloaded", DICTIONARY)

    def _load(self) -> None:
        try:
            from spylls.hunspell import Dictionary

            folder = self._folder()
            if not all((folder / name).exists() for name in FILES[:2]):
                if not self.download:
                    raise FileNotFoundError(f"Wörterbuch fehlt in {folder}")
                self._download(folder)
            t = time.monotonic()
            self._dictionary = Dictionary.from_files(str(folder / DICTIONARY))
            log.info("Dictionary loaded in %.1f s", time.monotonic() - t)
            self.status = "ready"
        except Exception as e:
            log.exception("Loading the dictionary failed")
            self.error = ("Das Wörterbuch konnte nicht geladen werden – für den ersten Gebrauch braucht es "
                          f"eine Internetverbindung. ({e})")
            self.status = "error"

    # ------------------------------------------------------------ personal words

    @staticmethod
    def personal_words() -> set[str]:
        try:
            return {w.strip().lower() for w in personal_words_path().read_text(encoding="utf-8").splitlines()
                    if w.strip()}
        except FileNotFoundError:
            return set()

    def add_word(self, word: str) -> None:
        word = word.strip()
        if not word or word.lower() in self.personal_words():
            return
        path = personal_words_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(word + "\n")

    # ------------------------------------------------------------ checking

    def _correct(self, word: str) -> bool:
        if word not in self._cache:
            ok = self._dictionary.lookup(word)
            if not ok and "-" in word:  # compound with hyphen: every part correct is enough
                ok = all(self._dictionary.lookup(part) for part in word.split("-") if part)
            self._cache[word] = ok
        return self._cache[word]

    @staticmethod
    def _skip(word: str, known: set[str]) -> bool:
        return (len(word) < 2 or word.lower() in known
                or (word.isupper() and len(word) <= 5))  # abbreviations such as CEO, PDF

    def check(self, words: list[str], extra: list[str] = ()) -> dict:
        """Which of these words are misspelled? Starts loading on first use."""
        self.start()
        if self.status != "ready":
            return {"status": self.status, "error": self.error, "misspelled": []}
        known = self.personal_words() | {w.lower() for w in extra}
        misspelled = sorted({w for w in words if WORD.fullmatch(w) and not self._skip(w, known)
                             and not self._correct(w)})
        return {"status": "ready", "error": None, "misspelled": misspelled}

    def suggest(self, word: str, limit: int = 6, time_limit_s: float = 0.8) -> list[str]:
        """Suggestions, at most `limit`, whatever was found within `time_limit_s`.

        spylls can't be interrupted while it computes the next suggestion (up to
        seconds for garbled words), so the search runs in its own thread and we
        only wait for the time limit.
        """
        if self.status != "ready":
            return []
        result: list[str] = []
        stop = threading.Event()

        def search():
            for suggestion in self._dictionary.suggest(word):
                if stop.is_set():
                    return
                if suggestion not in result:
                    result.append(suggestion)
                if len(result) >= limit:
                    return

        worker = threading.Thread(target=search, name="suggest", daemon=True)
        worker.start()
        started = last_change = time.monotonic()
        seen = 0
        while worker.is_alive() and time.monotonic() - started < time_limit_s:
            worker.join(0.03)
            if len(result) != seen:
                seen, last_change = len(result), time.monotonic()
            elif result and time.monotonic() - last_change > QUIET_S:
                break  # good suggestions come first; more would only be far-fetched
        stop.set()
        return list(result[:limit])
