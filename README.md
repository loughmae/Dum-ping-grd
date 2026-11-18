# Hp(10) Deep Dose Trend Dashboard

A Streamlit dashboard for exploring occupational dose/exposure monitoring
data — built around the example of **Hp(10) deep dose equivalent readings
for interventional cardiologists over 5 years**.

## Features

- **Trend windows**: 3, 6, 12 and 24-month rolling means, plus the full
  5-year history, switchable with one slider.
- **Dose-metric selector**: the same trend views work for HP(10) Deep,
  HP(3) Eye (lens of eye), HP(0.07) Shallow (skin) and Neutron, each with
  its own Irish IRR19 limits and classification bands. Metrics
  without readings in the loaded data are hidden automatically.
- **Irish classification framework** (S.I. No. 30 of 2019 / EU BSSD):
  whole-body effective dose — 1 mSv/y public/Cat B trigger, 6 mSv/y Cat A
  trigger, 20 mSv/y annual limit; lens of eye — 15 mSv/y Cat A trigger,
  20 mSv/y annual limit (100 mSv/5y, max 50 mSv single year); skin —
  500 mSv/y. The attention list shows each worker's classification band,
  and charts carry all threshold lines plus the 100 mSv/5-year constraint.
- **Cohort view**: monthly or quarterly aggregation, rolling means for the
  whole group, per-worker bars + rolling-average lines.
- **Worker attention list**: every wearer ranked by trailing 12-month dose
  as a percentage of the annual reference limit, with their classification
  band and months-reported context, plus cohort-relative flagging (`×role`
  median, ⚠️ at ≥2× peers) and a next-year projection band (seasonal
  climatology with 24+ months of history, run-rate with 6+, withheld
  below that).
- **Significant trends chart**: per-worker linear regression over the last
  12 reported months, shown only where the slope is statistically
  significant — rising in red, falling in green, with fitted lines.
- **Low-dose & badge-compliance watch**: workers at or below 1 mSv/y
  (IRR19: individual monitoring not required) flagged as reduced-
  surveillance candidates; missing badge-return months flagged separately,
  since a low dose with return gaps means badges not worn, not low
  exposure.
- **Dose heatmap**: worker × month grid of the last 24 months for spotting
  workload spikes and pattern changes at a glance.
- **Eye : deep dose ratio (HP(3) : HP(10))**: badge-aware pairing — both
  quantities on one badge reflect attenuation at that badge position;
  eye dosimeter vs chest badge is labelled cross-badge and reflects apron
  shielding plus geometry. Ratios computed only where deep ≥ 0.1 mSv, and
  flagged on statistically significant drift from the worker's own
  baseline.
- **Limit tracking**: trailing 12-month cumulative dose per worker against
  ICRP reference lines per metric.
- **Annual comparison**: yearly total Hp(10) per worker, faceted and
  colour-coded by role.
- **Bring your own data**: upload a dosimetry provider export or a canonical
  CSV, or use the bundled synthetic 5-year cardiology example.
- **Role tagging**: tag each wearer with a role in the app; assignments are
  remembered per wearer number in `role_assignments.csv` and applied
  automatically to future uploads.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

The first run auto-generates `data/hp10_dose_example.csv` (or run
`python generate_example_data.py` manually to customise months/seed).

## Data formats

**Provider exports** are auto-detected by their columns, e.g.:

```
Account, Location, Wearer #, Name, ID, Serial No, Badge Type, Body Region,
Start Date, End Date, HP(10) Deep, HP(3) Eye, HP(0.07) Shallow, Neutron, Notes
```

- The reporting month is taken from the End Date.
- Rows with `CONTROL` (or blank) in Wearer # are treated as control
  dosimeters (`CONTROL-<serial>` ids) and excluded from the role filter by
  default.
- HP(3) Eye, HP(0.07) Shallow and Neutron columns are parsed and kept in the
  data table; trend charts currently use HP(10) Deep.
- Excel overflow values (`########`) and unreadable rows are dropped.

**Canonical CSV schema:**

| column             | type     | required | notes                              |
|--------------------|----------|----------|------------------------------------|
| `worker_id`        | string   | yes      | unique per monitored worker        |
| `name`             | string   | yes      | display name                       |
| `role`             | string   | no       | seeds the role store on first load |
| `month`            | YYYY-MM  | yes      | reporting period                   |
| `hp10_deep_msv`    | number   | yes      | Hp(10) deep dose equivalent (mSv)  |
| `monitors_reported`| 0/1      | no       | whether a reading was returned     |

## Role memory

Roles are stored in `role_assignments.csv` (override the path with the
`DOSE_ROLE_FILE` environment variable) keyed by wearer number, so each
monthly export you upload inherits the roles you assigned previously. New
wearer numbers appear as `unassigned` in the tagging panel.

## Notes

- The bundled dataset is **synthetic** (`generate_example_data.py`) —
  realistic seasonal workload variation, per-worker trends, one worker
  with a rising profile, and occasional high-reading outliers.
- Reference limits are hard-coded at the top of `app.py`
  (`ICRP_ANNUAL_AVG_LIMIT`, `ICRP_SINGLE_YEAR_LIMIT`) and can be adjusted
  to local regulations.
