"""Coverage template derived from the historical rotas and the Area
Reference catalogue, plus modality normalisation.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass

MODALITY_ALIASES = {
    "mr": "MRI",
    "dxa": "DEXA",
    "ultrasound": "US",
}

WEEKEND_CALL_CODES = ["General Call", "CT Call", "Cath Lab Call"]


def norm_modality(name: str) -> str:
    key = str(name).strip().lower().replace(" ", "")
    return MODALITY_ALIASES.get(key, str(name).strip().upper())


def norm_label(label: str) -> str:
    return " ".join(str(label).lower().replace(":", " ").split())


@dataclass
class AreaInfo:
    code: str
    modality: str
    shift_type: str
    location: str
    staffing_level: int


def load_area_reference(path) -> dict[str, AreaInfo]:
    areas = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = row["code"].strip()
            if not code:
                continue
            areas[norm_label(code)] = AreaInfo(
                code=code,
                modality=norm_modality(row["modality"]),
                shift_type=row["shift_type"].strip(),
                location=row["location"].strip(),
                staffing_level=int(row["staffing_level"] or 0),
            )
    return areas


def match_area(label: str, areas: dict[str, AreaInfo]) -> AreaInfo | None:
    key = norm_label(label).replace("  ", " ")
    if key in areas:
        return areas[key]
    stripped = key.strip()
    if stripped in areas:
        return areas[stripped]
    return None


def shift_block(label: str, info: AreaInfo | None) -> str:
    lowered = str(label).lower()
    if "call" in lowered:
        return "call"
    if info:
        st = info.shift_type.lower()
        if "early" in st:
            return "early"
        if "late" in st:
            return "late"
        if "early/late" in st:
            return "late"
    if "early" in lowered:
        return "early"
    if "late" in lowered:
        return "late"
    return "wholeday"


def modality_from_label(label: str, areas: dict[str, AreaInfo]) -> str:
    lowered = norm_label(label)
    for token in lowered.replace(":", " ").split():
        norm = norm_modality(token)
        if norm in {"MRI", "CT", "GENERAL", "CATH LAB", "SCREENING", "MAMMO",
                    "DEXA", "US", "PET", "NUC", "PACS", "INTERVENTIONAL",
                    "RSM", "RPO"}:
            return norm
    info = match_area(label, areas)
    if info:
        return info.modality
    return "GENERAL"


def canonical_key(label: str, areas: dict[str, AreaInfo]) -> str:
    lowered = norm_label(label)
    if "call" in lowered:
        return f"call:{modality_from_label(label, areas)}"
    info = match_area(label, areas)
    if info:
        block = shift_block(label, info)
    else:
        block = shift_block(label, None)
    modality = modality_from_label(label, areas)
    return f"{modality}|{block}"


@dataclass
class SlotTemplate:
    area_label: str
    canonical: str
    modality: str
    shift_block: str
    required: int


def derive_template(assignments_path, areas: dict[str, AreaInfo]) -> dict[str, list[SlotTemplate]]:
    """weekday -> slot list; required headcount = modal number of slots per
    day observed in history for that weekday and canonical key."""
    per_day: dict[tuple, Counter] = defaultdict(Counter)
    examples: dict[str, str] = {}

    with open(assignments_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["category"] not in ("area", "bank"):
                continue
            key = canonical_key(row["area_label"], areas)
            per_day[(row["weekday"], row["date"])][key] += 1
            examples.setdefault(key, row["area_label"].strip())

    totals: dict[str, Counter] = defaultdict(Counter)
    for (weekday, _date), counter in per_day.items():
        for key, n in counter.items():
            totals[weekday][key] += n

    observed_days: Counter = Counter(weekday for (weekday, _d) in per_day)

    template: dict[str, list[SlotTemplate]] = {}
    for weekday, counter in totals.items():
        days = max(observed_days[weekday], 1)
        slots = []
        for key, total in counter.items():
            count = round(total / days)
            if count <= 0:
                continue
            if key.startswith("call:"):
                modality, block = key.split(":")[1], "call"
            else:
                modality, block = key.split("|")
            slots.append(
                SlotTemplate(
                    area_label=examples[key],
                    canonical=key,
                    modality=modality,
                    shift_block=block,
                    required=count,
                )
            )
        template[weekday] = sorted(slots, key=lambda s: (-s.required, s.canonical))
    return template
