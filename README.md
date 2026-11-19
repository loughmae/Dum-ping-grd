# dum-ping-grd

A radiography rota scheduling tool: ingests the hand-made Excel rotas,
normalises them into structured data, and drives a constraint-solving
scheduler (OR-Tools CP-SAT) for Monday to Sunday service coverage with
on-call, individualised patterns, leave and shift swaps.

## Current stage

1. **Ingestion** - `rotatool` parses the existing monthly rota workbooks
   (Week 1-5 sheets, Mon-Fri day columns with `Absent:`, `COMMENTS:`,
   bank-staff and staff-pattern row groups) plus the staff master workbook
   (Staff Master, Area Reference, Staff Qualifications), and produces
   normalised CSVs and a data-quality report.
2. **Replay scheduler** - derives a per-weekday coverage template from the
   historical rotas, then generates one week with CP-SAT (Mon-Fri in-hours,
   on-call on every day, weekends on-call only), respecting each person's
   parsed contract pattern, skills, weekly-hours cap, rest rules and a
   person-day slot cap. It then audits the hand-made rota for skill,
   pattern and rest violations and compares load per person.

See `docs/ASSUMPTIONS.md` for the confirmed rules and modelling decisions.

### Pipeline

```bash
pip install -r requirements.txt
python -m rotatool.cli ingest --raw data/raw --out data/processed \
    --staff "data/raw/Staff master guide for rota.xlsx"
python -m rotatool.cli replay --week-start 2025-04-14
python -m pytest tests/
```

Outputs in `data/processed/`:

| File | Contents |
|---|---|
| `staff_master.csv` | staff, modalities, locations, individual work patterns |
| `area_reference.csv` | area/shift catalogue: modality, shift type, location, staffing level |
| `assignments.csv` | one row per person-token per shift-slot per day, with resolved name, late/WFH/time annotations |
| `absences.csv` | leave entries extracted from `Absent:` rows with reasons |
| `data_quality_report.md` | coverage by day, weekday distribution, unresolved name tokens, leave signals, swap comments |
| `solved_week_<start>.csv` | the generated rota for the replay week |
| `replay_report_<start>.md` | solver result vs hand-made rota comparison and per-person load |

### Name handling

Rota cells are free text (`Salim8-6`, `Carlo(L)`, `Bahia wfh`, `Kitjia`,
`Kitija/Jen`, `Jhon`). The parser splits cells, strips annotations, resolves
tokens against the staff master (exact, alias, prefix, fuzzy) and reports
ambiguous tokens (`Jen` could be Jenner or Jennila) instead of guessing.

## Data policy

`data/raw/` and `data/processed/` are git-ignored: the rotas contain real
staff names and this is (or may become) a public repository. To reproduce,
drop the raw `.xlsx` files into `data/raw/` locally.

## Roadmap

1. **Done** - ingestion + normalisation + historical replay report (Feb-May 2025).
2. **Done** - CP-SAT replay scheduler for one week with pattern, skill,
   hours-cap and on-call rest constraints.
3. Leave-request and swap workflow with automatic constraint validation;
   multi-week continuity and on-call fairness across weeks.
4. Web portal (FastAPI + frontend), iCal export, coordinator console.
