"""Parsers for the staff master workbook (Staff Master / Area Reference /
Staff Qualifications sheets)."""

from __future__ import annotations

from dataclasses import dataclass

import openpyxl


@dataclass
class StaffMember:
    name: str
    modalities: list[str]
    locations: list[str]
    pattern: str
    preferred_areas: str
    leave_start: str
    leave_end: str
    notes: str


@dataclass
class AreaShift:
    code: str
    modality: str
    shift_type: str
    location: str
    assignment_rule: str
    required_skills: str
    staffing_level: int


def _clean(value) -> str:
    return str(value).strip() if value is not None else ""


def parse_staff(workbook_path) -> list[StaffMember]:
    ws = openpyxl.load_workbook(workbook_path, data_only=True)["Staff Master"]
    staff = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        name = _clean(row[0])
        if not name:
            continue
        modalities = [m.strip() for m in _clean(row[1]).split(",") if m.strip()]
        locations = [l.strip() for l in _clean(row[2]).split(",") if l.strip()]
        staff.append(
            StaffMember(
                name=name,
                modalities=modalities,
                locations=locations,
                pattern=_clean(row[3]),
                preferred_areas=_clean(row[4]) if len(row) > 4 else "",
                leave_start=_clean(row[5]) if len(row) > 5 else "",
                leave_end=_clean(row[6]) if len(row) > 6 else "",
                notes=_clean(row[7]) if len(row) > 7 else "",
            )
        )
    return staff


def parse_areas(workbook_path) -> list[AreaShift]:
    ws = openpyxl.load_workbook(workbook_path, data_only=True)["Area Reference"]
    areas = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        code = _clean(row[0])
        if not code:
            continue
        try:
            level = int(row[6]) if row[6] is not None else 0
        except (TypeError, ValueError):
            level = 0
        areas.append(
            AreaShift(
                code=code,
                modality=_clean(row[1]),
                shift_type=_clean(row[2]),
                location=_clean(row[3]),
                assignment_rule=_clean(row[4]),
                required_skills=_clean(row[5]),
                staffing_level=level,
            )
        )
    return areas
