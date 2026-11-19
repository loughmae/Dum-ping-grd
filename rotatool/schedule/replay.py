"""End-to-end replay: derive template from history, solve one week with
CP-SAT, and compare the generated rota against the hand-made one.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from .model import BANK_STAFF, SolverStaff, solve_week
from .patterns import parse_pattern
from .template import (
    canonical_key,
    derive_template,
    load_area_reference,
    modality_from_label,
    norm_modality,
    shift_block,
)


def _parse_date(text: str) -> date:
    return date.fromisoformat(text)


def load_staff(staff_csv_path, solved_history=None):
    staff = []
    with open(staff_csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            staff.append(
                SolverStaff(
                    name=row["name"].strip(),
                    modalities={
                        norm_modality(m)
                        for m in row["modalities"].split(";")
                        if m.strip()
                    },
                    pattern=parse_pattern(row["pattern"]),
                    preferred=norm_modality(row["preferred_areas"] or ""),
                )
            )
    return staff


def historical_call_counts(assignments_path):
    counts = Counter()
    with open(assignments_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["category"] == "area" and "call" in row["area_label"].lower() and row["person"]:
                counts[row["person"]] += 1
    return counts


def actual_week_rows(assignments_path, week_start: date):
    end = week_start + timedelta(days=7)
    rows = []
    with open(assignments_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["category"] != "area" or not row["person"]:
                continue
            d = _parse_date(row["date"])
            if week_start <= d < end:
                rows.append(row)
    return rows


def audit_actual(rows, staff_by_name, areas):
    skill_violations, pattern_violations, rest_violations = [], [], []
    by_person_day = defaultdict(list)
    for row in rows:
        by_person_day[(row["person"], row["date"])].append(row)

    for (person, day), day_rows in by_person_day.items():
        p = staff_by_name.get(person)
        if not p:
            continue
        works = [r for r in day_rows if not r["area_label"].lower().endswith("call")
                 and "call" not in r["area_label"].lower()]
        calls = [r for r in day_rows if "call" in r["area_label"].lower()]
        if works and calls:
            rest_violations.append((person, day, len(works)))

        wd = _parse_date(day).strftime("%a")
        if p.pattern.fixed_days and wd not in p.pattern.fixed_days and works:
            pattern_violations.append((person, day))

        if not p.modalities:
            continue
        for r in works:
            modality = modality_from_label(r["area_label"], areas)
            if modality not in p.modalities:
                skill_violations.append((person, day, r["area_label"], modality))

    per_day_block_counts = Counter()
    for (person, day), day_rows in by_person_day.items():
        blocks = Counter(shift_block(r["area_label"], None) for r in day_rows)
        n = blocks["wholeday"] + blocks["early"] + blocks["late"]
        per_day_block_counts[n] += 1

    return skill_violations, pattern_violations, rest_violations, per_day_block_counts


def run_replay(processed_dir: str, week_start: date) -> str:
    areas = load_area_reference(f"{processed_dir}/area_reference.csv")
    template = derive_template(f"{processed_dir}/assignments.csv", areas)
    staff = load_staff(f"{processed_dir}/staff_master.csv")
    calls = historical_call_counts(f"{processed_dir}/assignments.csv")
    for p in staff:
        p.historical_calls = calls.get(p.name, 0)
    staff_by_name = {p.name: p for p in staff}

    result = solve_week(staff, week_start, template)

    solved_path = f"{processed_dir}/solved_week_{week_start.isoformat()}.csv"
    with open(solved_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["date", "weekday", "area_label", "canonical", "block", "person"],
        )
        writer.writeheader()
        for a in sorted(result["assignments"], key=lambda a: (a["date"], a["canonical"])):
            writer.writerow(a)

    rows = actual_week_rows(f"{processed_dir}/assignments.csv", week_start)
    skill_v, pattern_v, rest_v, block_counts = audit_actual(rows, staff_by_name, areas)

    template_required = {
        d.strftime("%a"): sum(s.required for s in template.get(d.strftime("%a"), []))
        for d in (week_start + timedelta(days=i) for i in range(7))
    }

    lines = [
        f"# Solver replay — week of {week_start.isoformat()}",
        "",
        f"- Solver status: **{result['status']}**",
        f"- Slots filled: **{len(result['assignments'])}** "
        f"of template requirement {sum(template_required.values())}",
        f"- Unfilled slots: **{len(result['gaps'])}**"
        + (f" ({'; '.join(f'{d} {c} x{n}' for d, c, n in result['gaps'][:10])})" if result["gaps"] else ""),
        "",
        "## Comparison with the hand-made rota for the same week",
        "",
        f"- Actual assignment rows parsed: **{len(rows)}**",
        f"- Actual skill mismatches (person without the area modality): **{len(skill_v)}**",
        f"- Actual pattern violations (work on a non-contracted day): **{len(pattern_v)}**",
        f"- Actual same-day work + on-call (rest rule): **{len(rest_v)}**",
        f"- Actual slots per person-day distribution: "
        + ", ".join(f"{n}: {c}" for n, c in sorted(block_counts.items()))
        + " (solver caps at 2: early+late, or one wholeday)",
        "",
    ]
    if skill_v:
        lines.append("### Sample skill mismatches in the historical rota")
        lines.extend(f"- {p} on {d}: {label} (needs {mod})" for p, d, label, mod in skill_v[:15])
        lines.append("")

    lines += ["## Generated week — per-person load", "", "| Person | Hours | On-call | Contracted |", "|---|---|---|---|"]
    for name in sorted(result["hours"], key=lambda n: -result["hours"][n]):
        p = staff_by_name.get(name)
        contracted = round(p.pattern.weekly_hours, 1) if p else "?"
        lines.append(
            f"| {name} | {result['hours'].get(name, 0):.0f} | {result['calls'].get(name, 0)} | {contracted} |"
        )

    report_path = f"{processed_dir}/replay_report_{week_start.isoformat()}.md"
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return report_path
