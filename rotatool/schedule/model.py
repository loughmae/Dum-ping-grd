"""CP-SAT model generating one week's rota (Mon-Fri in-hours, weekend
on-call only) from the historical coverage template.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ortools.sat.python import cp_model

from .patterns import Pattern

BLOCK_HOURS = {"early": 8.0, "late": 8.0, "wholeday": 8.0, "call": 0.0}
BANK_STAFF = {"Ashleen", "Conor", "Rebecca", "Richael", "Brandon"}


@dataclass
class SolverStaff:
    name: str
    modalities: set
    pattern: Pattern
    preferred: str
    historical_calls: int = 0

    @property
    def regular(self) -> bool:
        return self.name not in BANK_STAFF


def solve_week(staff, week_start: date, template, weeks: int = 1):
    """staff: list[SolverStaff]; template: weekday -> list[SlotTemplate].

    Returns dict with status, assignments, gaps, per-person hours and calls.
    """
    model = cp_model.CpModel()
    days = [week_start + timedelta(days=i) for i in range(7 * weeks)]
    weekday_names = [d.strftime("%a") for d in days]

    slots_per_day = []
    for i, d in enumerate(days):
        wd = weekday_names[i]
        weekend = wd in ("Sat", "Sun")
        slots_per_day.append(
            [s for s in template.get(wd, []) if (not weekend or s.shift_block == "call")]
        )

    def eligible(p, slot):
        return (
            p.regular
            and bool(p.modalities)
            and slot.modality in p.modalities
        )

    x = {}
    for pi, p in enumerate(staff):
        for di, day_slots in enumerate(slots_per_day):
            for si, slot in enumerate(day_slots):
                if eligible(p, slot):
                    x[pi, di, si] = model.NewBoolVar(f"x_{p.name}_{di}_{si}")

    gaps = {}
    for di, day_slots in enumerate(slots_per_day):
        for si, slot in enumerate(day_slots):
            assigned = [v for (pi, d2, s2), v in x.items() if d2 == di and s2 == si]
            gap = model.NewIntVar(0, slot.required, f"gap_{di}_{si}")
            model.Add(sum(assigned) + gap == slot.required)
            gaps[di, si] = gap

    for pi, p in enumerate(staff):
        pattern = p.pattern
        for di, day_slots in enumerate(slots_per_day):
            blocks = {"call": [], "early": [], "late": [], "wholeday": []}
            for si, slot in enumerate(day_slots):
                if (pi, di, si) in x:
                    blocks[slot.shift_block].append(x[pi, di, si])

            for group, cap in (("wholeday", 1), ("early", 1), ("late", 1)):
                if blocks[group]:
                    model.Add(sum(blocks[group]) <= cap)
            if blocks["wholeday"] and (blocks["early"] or blocks["late"]):
                model.Add(
                    sum(blocks["wholeday"])
                    + sum(blocks["early"])
                    + sum(blocks["late"])
                    <= 1
                )
            if blocks["call"]:
                others = blocks["wholeday"] + blocks["early"] + blocks["late"]
                if others:
                    model.Add(sum(blocks["call"]) + sum(others) <= 1)

            work_vars = [v for g in ("wholeday", "early", "late") for v in blocks[g]]
            if pattern.fixed_days:
                wd = weekday_names[di]
                if wd not in pattern.fixed_days and work_vars:
                    for v in work_vars:
                        model.Add(v == 0)

    for pi, p in enumerate(staff):
        pattern = p.pattern
        work_days = []
        call_vars = []
        hour_terms = []
        for di, day_slots in enumerate(slots_per_day):
            work_vars = [
                x[pi, di, si]
                for si, slot in enumerate(day_slots)
                if (pi, di, si) in x and slot.shift_block != "call"
            ]
            calls_here = [
                x[pi, di, si]
                for si, slot in enumerate(day_slots)
                if (pi, di, si) in x and slot.shift_block == "call"
            ]
            if calls_here:
                call_vars.extend(calls_here)
            if not work_vars:
                continue
            hour_terms.extend(
                round(BLOCK_HOURS[slot.shift_block]) * x[pi, di, si]
                for si, slot in enumerate(day_slots)
                if (pi, di, si) in x and slot.shift_block != "call"
            )
            day_var = model.NewBoolVar(f"wd_{p.name}_{di}")
            model.AddMaxEquality(day_var, work_vars)
            work_days.append(day_var)

        if not pattern.fixed_days:
            model.Add(sum(work_days) <= pattern.flexi_days)
        model.Add(sum(hour_terms) <= int(pattern.weekly_hours * 1.15 + 4))
        if call_vars:
            model.Add(sum(call_vars) <= 2)

    terms = []
    for (pi, di, si), var in x.items():
        p = staff[pi]
        slot = slots_per_day[di][si]
        weight = 100
        if p.preferred and p.preferred.upper() == slot.modality.upper():
            weight += 5
        if slot.shift_block == "call":
            weight -= min(p.historical_calls, 12) // 2
        terms.append(weight * var)
    for gap in gaps.values():
        terms.append(-1000 * gap)
    model.Maximize(sum(terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
    status = solver.Solve(model)

    result = {
        "status": solver.StatusName(status),
        "assignments": [],
        "gaps": [],
        "hours": {},
        "calls": {},
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return result

    for di, day_slots in enumerate(slots_per_day):
        for si, slot in enumerate(day_slots):
            if solver.Value(gaps[di, si]) > 0:
                result["gaps"].append(
                    (days[di].isoformat(), slot.canonical, solver.Value(gaps[di, si]))
                )
            for pi, p in enumerate(staff):
                if (pi, di, si) in x and solver.Value(x[pi, di, si]):
                    result["assignments"].append(
                        {
                            "date": days[di].isoformat(),
                            "weekday": weekday_names[di],
                            "canonical": slot.canonical,
                            "area_label": slot.area_label,
                            "block": slot.shift_block,
                            "person": p.name,
                        }
                    )

    hours, calls = {}, {}
    for a in result["assignments"]:
        if a["block"] != "call":
            hours[a["person"]] = hours.get(a["person"], 0.0) + BLOCK_HOURS[a["block"]]
        else:
            calls[a["person"]] = calls.get(a["person"], 0) + 1
    result["hours"] = hours
    result["calls"] = calls
    return result
