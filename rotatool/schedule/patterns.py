"""Parsers for staff master working-pattern strings.

Examples handled:
    "M-F 8-4", "3x 8-8", "M,T,T,F", "4 x 9-7", "W-F (7:30-8)",
    "M-W 8-8", "Mon, Tues, Fri 7:30-8", "Tues, Wed", "T,W,T",
    "Tues-Thur 8-8", "Mon, Fri 8-8", "Tues-Thur 8-8", "M-F (Late Start on Tues, Wed)"
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri"]

DAY_TOKENS = {
    "mon": "Mon", "m": "Mon",
    "tue": "Tue", "tues": "Tue", "tu": "Tue", "t": "Tue",
    "wed": "Wed", "w": "Wed",
    "thu": "Thu", "thur": "Thu", "thurs": "Thu", "th": "Thu",
    "fri": "Fri", "f": "Fri",
}

SPAN_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*[-\u2013]\s*(\d{1,2})(?::(\d{2}))?")


@dataclass
class Pattern:
    fixed_days: set | None  # None = flexible
    flexi_days: int
    day_hours: float

    @property
    def weekly_hours(self) -> float:
        days = len(self.fixed_days) if self.fixed_days else self.flexi_days
        return days * self.day_hours


def _span_hours(span: str) -> float | None:
    m = SPAN_RE.fullmatch(span.strip())
    if not m:
        return None
    start = int(m.group(1)) + int(m.group(2) or 0) / 60
    end = int(m.group(3)) + int(m.group(4) or 0) / 60
    if end <= start or end - start < 4:
        end += 12
    return round(end - start, 2)


def parse_pattern(pattern: str) -> Pattern:
    text = str(pattern).strip().lower()
    if not text:
        return Pattern(fixed_days=None, flexi_days=5, day_hours=8.0)
    if "late start" in text:
        text = "m-f 8-4"

    spans = SPAN_RE.findall(text)
    hours = None
    if spans:
        rebuilt = text
        values = []
        for h1, m1, h2, m2 in spans:
            span = f"{h1}{':' + m1 if m1 else ''}-{h2}{':' + m2 if m2 else ''}"
            values.append(_span_hours(span))
            rebuilt = rebuilt.replace(span, " ", 1)
        usable = [v for v in values if v]
        if usable:
            hours = sum(usable) / len(usable)
        text = rebuilt

    flexi_match = re.search(r"(\d+)\s*x\b", text)
    flexi_days = int(flexi_match.group(1)) if flexi_match else None

    cleaned = re.sub(r"\d+", " ", text)
    cleaned = re.sub(r"[^\w\s,\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")

    days: set[str] = set()
    for rng in re.findall(
        r"\b(m|tu|tues|t|w|thu|thur|thurs|f)\s*-\s*(m|tu|tues|t|w|thu|thur|thurs|f)\b",
        cleaned,
    ):
        start_name = DAY_TOKENS[rng[0]]
        end_name = DAY_TOKENS[rng[1]]
        i, j = DAY_ORDER.index(start_name), DAY_ORDER.index(end_name)
        if i <= j:
            days.update(DAY_ORDER[i : j + 1])
        cleaned = re.sub(r"\b(m|tu|tues|t|w|thu|thur|thurs|f)\s*-\s*(m|tu|tues|t|w|thu|thur|thurs|f)\b", " ", cleaned, count=1)

    named = re.findall(r"\b(mon|tue|tues|tu|wed|thu|thur|thurs|th|fri)\b", cleaned)
    for n in named:
        days.add(DAY_TOKENS[n])
    cleaned = re.sub(r"\b(mon|tue|tues|tu|wed|thu|thur|thurs|th|fri)\b", " ", cleaned)

    lone_t = 0
    for letter in re.findall(r"(?<![a-z])([mtwf])(?![a-z])", cleaned):
        if letter == "t":
            lone_t += 1
    if lone_t >= 2:
        days.update({"Tue", "Thu"})
    elif lone_t == 1:
        days.add("Thu" if re.search(r"(?<![a-z])w(?![a-z])", cleaned) else "Tue")
    for letter in re.findall(r"(?<![a-z])([mwf])(?![a-z])", cleaned):
        days.add(DAY_TOKENS[letter])

    if not days:
        if flexi_days:
            return Pattern(fixed_days=None, flexi_days=flexi_days, day_hours=hours or 8.0)
        return Pattern(fixed_days=None, flexi_days=5, day_hours=hours or 8.0)

    if "wk" in text or "/" in text:
        return Pattern(fixed_days=None, flexi_days=flexi_days or 3, day_hours=hours or 8.0)

    return Pattern(fixed_days=days, flexi_days=flexi_days or len(days), day_hours=hours or 8.0)
