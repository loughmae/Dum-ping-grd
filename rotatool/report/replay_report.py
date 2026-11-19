"""Ingest raw rota workbooks and produce normalised CSVs plus a data
quality report.

Usage:
    python -m rotatool.cli ingest --raw data/raw --out data/processed \
        --staff "data/raw/Staff master guide for rota.xlsx"
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
from collections import Counter, defaultdict
from datetime import date

from ..parsing.rota_workbook import parse_rota_workbook
from ..parsing.staff_master import parse_areas, parse_staff

IRISH_BANK_HOLIDAYS_2025 = {
    date(2025, 1, 1), date(2025, 2, 3), date(2025, 3, 17),
    date(2025, 4, 21), date(2025, 5, 5), date(2025, 6, 2),
    date(2025, 8, 4), date(2025, 10, 27), date(2025, 12, 25),
    date(2025, 12, 26),
}

ASSIGNMENT_FIELDS = [
    "source_file", "sheet", "date", "weekday", "area_label", "category",
    "raw_cell", "person", "resolved", "candidates", "late", "wfh",
    "explicit_time", "notes",
]
ABSENCE_FIELDS = ["source_file", "sheet", "date", "raw_cell", "person",
                  "resolved", "reason"]


def _write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_ingest(raw_dir: str, out_dir: str, staff_path: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    staff = parse_staff(staff_path)
    areas = parse_areas(staff_path)
    names = [s.name for s in staff]

    _write_csv(
        os.path.join(out_dir, "staff_master.csv"),
        ["name", "modalities", "locations", "pattern", "preferred_areas"],
        [
            {
                "name": s.name,
                "modalities": ";".join(s.modalities),
                "locations": ";".join(s.locations),
                "pattern": s.pattern,
                "preferred_areas": s.preferred_areas,
            }
            for s in staff
        ],
    )
    _write_csv(
        os.path.join(out_dir, "area_reference.csv"),
        ["code", "modality", "shift_type", "location", "assignment_rule",
         "required_skills", "staffing_level"],
        [vars(a) | {"modality": a.modality} for a in areas],
    )

    rosters = sorted(
        f for f in glob.glob(os.path.join(raw_dir, "*.xlsx"))
        if os.path.basename(f) != os.path.basename(staff_path)
    )

    all_sheets, all_assignments, all_absences, all_comments = [], [], [], []
    for path in rosters:
        for sheet in parse_rota_workbook(path, names):
            all_sheets.append(sheet)
            all_assignments.extend(sheet.assignments)
            all_absences.extend(sheet.absences)
            all_comments.extend(sheet.comments)

    _write_csv(
        os.path.join(out_dir, "assignments.csv"),
        ASSIGNMENT_FIELDS,
        [vars(a) for a in all_assignments],
    )
    _write_csv(
        os.path.join(out_dir, "absences.csv"),
        ABSENCE_FIELDS,
        [vars(a) for a in all_absences],
    )

    report = _build_report(
        staff, areas, all_sheets, all_assignments, all_absences, all_comments
    )
    report_path = os.path.join(out_dir, "data_quality_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    return report_path


def _build_report(staff, areas, sheets, assignments, absences, comments) -> str:
    lines = ["# Rota ingestion — data quality report", ""]

    total = len(assignments)
    unresolved = [a for a in assignments if not a.resolved]
    lines += [
        f"- Staff in master: **{len(staff)}** (incl. {sum(1 for s in staff if not s.modalities)} without recorded modalities)",
        f"- Area/shift codes in reference: **{len(areas)}**",
        f"- Weekly sheets parsed: **{len(sheets)}** "
        f"({', '.join(s.sheet for s in sheets[:1])}…)",
        f"- Assignment entries: **{total}**; unresolved: **{len(unresolved)}** "
        f"({100 * len(unresolved) / max(total, 1):.1f}%)",
        f"- Absence entries: **{len(absences)}**",
        f"- Comments captured: **{len(comments)}**",
        "",
    ]

    by_day = Counter(a.date for a in assignments)
    lines += ["## Coverage by day (assignment entries)", ""]
    for month in sorted({d[:7] for d in by_day}):
        day_rows = [(d, c) for d, c in sorted(by_day.items()) if d.startswith(month)]
        lines.append(f"### {month}")
        lines.append("")
        lines.append("| Date | Day | Entries | Note |")
        lines.append("|---|---|---|---|")
        for d, c in day_rows:
            weekday = date.fromisoformat(d).strftime("%a")
            note = "Irish bank holiday" if date.fromisoformat(d) in IRISH_BANK_HOLIDAYS_2025 else ""
            lines.append(f"| {d} | {weekday} | {c} | {note} |")
        lines.append("")

    weekdays = Counter(date.fromisoformat(a.date).strftime("%a") for a in assignments)
    lines += [
        "## Weekday distribution",
        "",
        f"`" + "  ".join(f"{k}: {v}" for k, v in sorted(weekdays.items())) + "`",
        "",
        "A Mon–Fri-only distribution means weekends are covered outside these "
        "sheets (likely on-call only) — confirm how weekends are rostered.",
        "",
    ]

    unresolved_tokens = Counter(a.raw_cell.strip() for a in unresolved)
    if unresolved_tokens:
        lines += ["## Unresolved name tokens", "", "| Raw token | Count | Candidates |", "|---|---|---|"]
        seen = set()
        for token, count in unresolved_tokens.most_common():
            cands = next((a.candidates for a in unresolved if a.raw_cell.strip() == token and a.candidates), "—")
            if cands == "—":
                cands = next((a.candidates for a in unresolved if a.raw_cell.strip() == token), "—") or "—"
            if token in seen:
                continue
            seen.add(token)
            lines.append(f"| {token} | {count} | {cands} |")
        lines.append("")

    if absences:
        reason_counts = Counter(
            a.raw_cell.split("(")[1].split(")")[0]
            for a in absences if "(" in a.raw_cell and ")" in a.raw_cell
        )
        people = Counter(a.person or a.raw_cell for a in absences)
        lines += [
            "## Leave signals from Absent rows",
            "",
            f"- Distinct staff with absences: **{len(people)}**",
            "- Reason mentions: "
            + ", ".join(f"{k} ({v})" for k, v in reason_counts.most_common(10)),
            "",
        ]

    if comments:
        lines += ["## Comments (swaps and manual notes)", ""]
        lines += [f"- {c}" for c in comments]
        lines.append("")

    return "\n".join(lines)
