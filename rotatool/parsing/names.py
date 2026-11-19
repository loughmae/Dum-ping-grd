"""Cleaning and resolution of person names written in rota cells.

Rota cells contain informal entries such as ``Salim8-6``, ``Carlo(L)``,
``Bahia wfh``, ``Kitija/Jen``, ``Kitjia`` or ``Mark 11hrs/``. This module
splits cells into individual entries, extracts annotations and resolves
each person token against the staff master.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches

TIME_RE = re.compile(r"(\d{1,2}\s*[-–]\s*\d{1,2}(:\d{2})?)")
LATE_RE = re.compile(r"\(L\)|\bLate\b")
KNOWN_WORDS_RE = re.compile(
    r"\b(wfh|closed|check|training|student|hrs?|hours?)\b|\*", re.IGNORECASE
)

MANUAL_ALIASES = {
    "jhon": "Johnrey",
    "johnrey": "Johnrey",
    "kitjia": "Kitija",
    "kitija": "Kitija",
    "richeal": "Richael",
    "richeal ": "Richael",
    "mark": "Markpol",
    "markpol": "Markpol",
    "jen": None,
    "jenila": "Jennila",
    "jessica": "Jess",
}

AMBIGUOUS_PREFIXES = ["jen"]


@dataclass
class Entry:
    """One person token parsed out of a rota cell."""

    raw: str
    person: str | None = None
    resolved: bool = False
    candidates: list[str] = field(default_factory=list)
    late: bool = False
    wfh: bool = False
    explicit_time: str | None = None
    notes: list[str] = field(default_factory=list)


def split_cell(value: str) -> list[str]:
    """Split a cell into raw person tokens."""
    parts = [p.strip() for p in str(value).split("/")]
    return [p for p in parts if p and not p.startswith("+")]


def _strip_annotations(token: str) -> tuple[str, dict]:
    annotations: dict = {"late": False, "wfh": False, "explicit_time": None, "notes": []}

    def _consume(match: re.Match) -> str:
        text = match.group(0)
        if LATE_RE.fullmatch(text):
            annotations["late"] = True
        elif TIME_RE.fullmatch(text):
            annotations["explicit_time"] = text.replace(" ", "")
        else:
            annotations["notes"].append(text)
        return ""

    work = token
    work = LATE_RE.sub(_consume, work, count=1)
    work = TIME_RE.sub(_consume, work)
    work = re.sub(r"\bwfh\b", "", work, flags=re.IGNORECASE)
    if work != token and "wfh" in token.lower():
        annotations["wfh"] = True
        annotations["notes"].append("wfh")

    for word in KNOWN_WORDS_RE.finditer(token):
        annotations["notes"].append(word.group(0))
    work = KNOWN_WORDS_RE.sub(" ", work)

    work = work.replace("(", "").replace(")", "")
    work = re.sub(r"\s+", " ", work).strip(" .,*-")
    return work, annotations


def resolve(token: str, staff_names: list[str]) -> Entry:
    """Resolve a raw token to a known staff name."""
    cleaned, ann = _strip_annotations(token)
    entry = Entry(raw=token, **ann)

    if not cleaned:
        return entry

    lowered = cleaned.lower()
    if lowered in MANUAL_ALIASES:
        canonical = MANUAL_ALIASES[lowered]
        if canonical is None:
            entry.candidates = [
                n for n in staff_names if n.lower().startswith(lowered)
            ]
            return entry
        entry.person, entry.resolved = canonical, True
        return entry

    for name in staff_names:
        if name.lower() == lowered:
            entry.person, entry.resolved = name, True
            return entry

    prefix_matches = [n for n in staff_names if n.lower().startswith(lowered)]
    if len(prefix_matches) == 1:
        entry.person, entry.resolved = prefix_matches[0], True
        return entry
    if len(prefix_matches) > 1:
        entry.candidates = prefix_matches
        return entry

    close = get_close_matches(lowered, [n.lower() for n in staff_names], n=1, cutoff=0.75)
    if close:
        entry.person, entry.resolved = close[0].title(), True
        return entry

    entry.candidates = []
    return entry


def resolve_cell(value: str, staff_names: list[str] | set[str]) -> list[Entry]:
    """Parse a full rota cell into resolved entries."""
    names = list(staff_names)
    return [resolve(tok, names) for tok in split_cell(str(value))]
