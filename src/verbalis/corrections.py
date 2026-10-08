"""Correction list: replace recurring recognition errors automatically.

Structure: each target (correct spelling) is unique and collects its variants:

    tocco   ← Toko, Tokko
    Limmat  ← Limetnah, Limet nah

A variant always belongs to exactly one target. If it is later corrected to a
different target, the newer correction wins.

The list grows out of edits in the transcript: `suggestions()` compares the
text before and after an edit and returns the replaced words.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .transcription.models import verbalis_home

WORD = re.compile(r"\w+(?:[-'’]\w+)*|[.,;:!?…]")  # punctuation acts as a boundary in the diff
PUNCTUATION = set(".,;:!?…")
MAX_WORDS = 3            # longer changes are rephrasings, not recognition errors
MIN_SIMILARITY = 0.6


def _key(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass
class CorrectionList:
    rules: dict[str, list[str]] = field(default_factory=dict)  # target → variants

    # ------------------------------------------------------------ persistence

    @staticmethod
    def path() -> Path:
        return verbalis_home() / "corrections.json"

    @classmethod
    def load(cls) -> "CorrectionList":
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
            return cls({str(t): [str(v) for v in vs] for t, vs in data.get("rules", {}).items()})
        except (FileNotFoundError, json.JSONDecodeError, AttributeError):
            return cls()

    def save(self) -> None:
        self.path().parent.mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps({"rules": self.rules}, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------ queries

    def target_of(self, variant: str) -> str | None:
        k = _key(variant)
        for target, variants in self.rules.items():
            if any(_key(v) == k for v in variants):
                return target
        return None

    def _existing_target(self, target: str) -> str | None:
        """Existing target with the same spelling (ignoring case)."""
        k = _key(target)
        return next((t for t in self.rules if _key(t) == k), None)

    def classify(self, variant: str, target: str) -> dict:
        """What would `add` do? For the preview in the UI.

        kind: "new" | "added" (to an existing target) | "replaces" (variant had
        another target) | "known".
        """
        previous = self.target_of(variant)
        existing = self._existing_target(target)
        if previous is not None and _key(previous) == _key(target):
            kind = "known"
        elif previous is not None:
            kind = "replaces"
        elif existing is not None:
            kind = "added"
        else:
            kind = "new"
        return {"variant": variant, "target": existing or target, "kind": kind, "previous": previous}

    def as_list(self) -> list[dict]:
        return [{"target": t, "variants": sorted(vs, key=str.lower)}
                for t, vs in sorted(self.rules.items(), key=lambda e: e[0].lower())]

    def targets(self) -> list[str]:
        return list(self.rules)

    # ------------------------------------------------------------ changes

    def add(self, variant: str, target: str) -> dict:
        variant, target = " ".join(variant.split()), " ".join(target.split())
        if not variant or not target or _key(variant) == _key(target):
            return {"variant": variant, "target": target, "kind": "ignored", "previous": None}
        info = self.classify(variant, target)
        if info["kind"] == "replaces":
            self.remove(info["previous"], variant)
        target = self._existing_target(target) or target
        variants = self.rules.setdefault(target, [])
        if not any(_key(v) == _key(variant) for v in variants):
            variants.append(variant)
        return info

    def remove(self, target: str, variant: str | None = None) -> None:
        if target not in self.rules:
            return
        if variant is None:
            del self.rules[target]
            return
        k = _key(variant)
        self.rules[target] = [v for v in self.rules[target] if _key(v) != k]
        if not self.rules[target]:
            del self.rules[target]

    # ------------------------------------------------------------ apply

    def apply(self, text: str) -> tuple[str, int]:
        """Replace all variants as whole words. Returns (text, count)."""
        pairs = [(v, t) for t, vs in self.rules.items() for v in vs]
        if not pairs:
            return text, 0
        # Longer variants first, so «Limet nah» wins over «Limet»
        pairs.sort(key=lambda p: len(p[0]), reverse=True)
        target_for = {_key(v): t for v, t in pairs}
        pattern = "|".join(r"\s+".join(map(re.escape, v.split())) for v, _ in pairs)
        regex = re.compile(rf"(?<!\w)(?:{pattern})(?!\w)", re.IGNORECASE)
        count = 0

        def replace(match: re.Match) -> str:
            nonlocal count
            count += 1
            return target_for[_key(match.group(0))]

        return regex.sub(replace, text), count


def suggestions(old: str, new: str) -> list[tuple[str, str]]:
    """Words replaced in an edit, as (variant, target).

    Only short replacements (up to 3 words, not across punctuation) – inserted,
    deleted or rephrased passages yield no rule, a largely rewritten paragraph
    none at all. Pure case changes neither.
    """
    a = [m.group(0) for m in WORD.finditer(old)]
    b = [m.group(0) for m in WORD.finditer(new)]
    matcher = difflib.SequenceMatcher(a=[w.lower() for w in a], b=[w.lower() for w in b], autojunk=False)
    if matcher.ratio() < MIN_SIMILARITY:
        return []  # largely rewritten – not individual recognition errors
    result: list[tuple[str, str]] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op != "replace" or i2 - i1 > MAX_WORDS or j2 - j1 > MAX_WORDS:
            continue
        if PUNCTUATION & {*a[i1:i2], *b[j1:j2]}:
            continue
        variant, target = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        if _key(variant) != _key(target) and (variant, target) not in result:
            result.append((variant, target))
    return result
