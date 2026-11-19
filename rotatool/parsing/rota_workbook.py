"""Parser for the weekly rota workbooks.

Each workbook holds one month, one sheet per week. Column A holds the
area/shift label, day columns hold free-text person entries. Extra row
groups carry absences (``Absent: n``), free-text comments (``COMMENTS:``),
the staff pattern reference block (``Staff: n``) and the bank pool
(``Bank Staff: n``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import openpyxl

from .names import resolve_cell

MONTHS = {
    m.lower(): i + 1
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"]
    )
}
MONTHS.update({m[:3].lower(): v for m, v in MONTHS.items()})

DATE_RE = re.compile(
    r"(?:(mon|tue|wed|thu|fri|sat|sun)\w*)?\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)",
    re.IGNORECASE,
)

AREA_REMODALITY_FALLBACK = re.compile(r"^([^:]+?)\s*:?\s*$")


@dataclass
class Assignment:
    source_file: str
    sheet: str
    date: str
    weekday: str
    area_label: str
    category: str
    raw_cell: str
    person: str | None
    resolved: bool
    candidates: str
    late: bool
    wfh: bool
    explicit_time: str
    notes: str


@dataclass
class Absence:
    source_file: str
    sheet: str
    date: str
    raw_cell: str
    person: str | None
    resolved: bool
    reason: str


def _clean(value) -> str:
    return str(value).strip() if value is not None else ""


def parse_date_cell(text: str, default_year: int) -> date | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    month = MONTHS.get(m.group(3).lower()[:3])
    if not month:
        return None
    return date(default_year, month, int(m.group(2)))


def classify(label: str) -> str:
    lowered = label.lower()
    if lowered.startswith("absent"):
        return "absence"
    if lowered.startswith("comment"):
        return "comment"
    if lowered.startswith("staff:"):
        return "staff_ref"
    if lowered.startswith("bank staff"):
        return "bank"
    if not label:
        return "empty"
    return "area"


@dataclass
class RotaSheetData:
    source_file: str
    sheet: str
    week_start: str
    days: list[str]
    assignments: list[Assignment] = field(default_factory=list)
    absences: list[Absence] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)


def parse_rota_workbook(
    workbook_path, staff_names: list[str] | set[str], default_year: int = 2025
) -> list[RotaSheetData]:
    """Parse every weekly sheet of a monthly rota workbook."""
    import os

    source = os.path.basename(workbook_path)
    wb = openpyxl.load_workbook(workbook_path, data_only=True)
    results = []

    for ws in wb.worksheets:
        headers: list[date | None] = []
        for cell in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))[1:]:
            headers.append(parse_date_cell(_clean(cell), default_year))

        first = next((h for h in headers if h), None)
        if first is None:
            continue

        for i in range(len(headers)):
            if headers[i] is None and i > 0 and headers[i - 1] is not None:
                from datetime import timedelta

                headers[i] = headers[i - 1] + timedelta(days=1)

        sheet_data = RotaSheetData(
            source_file=source,
            sheet=ws.title,
            week_start=first.isoformat(),
            days=[(h.isoformat() if h else "") for h in headers],
        )

        for row in ws.iter_rows(min_row=2, values_only=True):
            label = _clean(row[0])
            kind = classify(label)
            if kind == "empty" or not any(v is not None for v in row[1:]):
                continue

            for col_idx, value in enumerate(row[1:]):
                if col_idx >= len(headers) or headers[col_idx] is None:
                    continue
                text = _clean(value)
                if not text:
                    continue
                day = headers[col_idx]

                if kind == "absence":
                    m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", text)
                    reason = m.group(2).strip() if m else ""
                    person_text = m.group(1).strip() if m else text
                    entries = resolve_cell(person_text, staff_names)
                    for e in entries:
                        sheet_data.absences.append(
                            Absence(
                                source_file=source,
                                sheet=ws.title,
                                date=day.isoformat(),
                                raw_cell=text,
                                person=e.person,
                                resolved=e.resolved,
                                reason=reason,
                            )
                        )
                elif kind == "comment":
                    sheet_data.comments.append(f"{day.isoformat()}: {text}")
                elif kind in ("area", "bank"):
                    entries = resolve_cell(text, staff_names)
                    for e in entries:
                        sheet_data.assignments.append(
                            Assignment(
                                source_file=source,
                                sheet=ws.title,
                                date=day.isoformat(),
                                weekday=day.strftime("%a"),
                                area_label=label,
                                category=kind,
                                raw_cell=text,
                                person=e.person,
                                resolved=e.resolved,
                                candidates=";".join(e.candidates),
                                late=e.late,
                                wfh=e.wfh,
                                explicit_time=e.explicit_time or "",
                                notes=";".join(e.notes),
                            )
                        )
        results.append(sheet_data)
    return results
