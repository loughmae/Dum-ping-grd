# Hp(10) Deep Dose Trend Dashboard

A Streamlit dashboard for exploring occupational dose/exposure monitoring
data — built around the example of **Hp(10) deep dose equivalent readings
for interventional cardiologists over 5 years**.

## Features

- **Trend windows**: 3, 6, 12 and 24-month rolling means, plus the full
  5-year history, switchable with one slider.
- **Cohort view**: monthly or quarterly aggregation, rolling means for the
  whole group, per-worker bars + rolling-average lines.
- **Limit tracking**: trailing 12-month cumulative dose per worker against
  the ICRP 20 mSv/y (5-year average) and 50 mSv single-year reference lines.
- **Annual comparison**: yearly total Hp(10) per worker, faceted and
  colour-coded by role.
- **Bring your own data**: upload any CSV with the schema below, or use the
  bundled synthetic 5-year cardiology example.

## Quick start

```bash
pip install -r requirements.txt
python generate_example_data.py        # writes data/hp10_dose_example.csv
streamlit run app.py
```

## Data schema

| column             | type     | required | notes                              |
|--------------------|----------|----------|------------------------------------|
| `worker_id`        | string   | yes      | unique per monitored worker        |
| `name`             | string   | yes      | display name                       |
| `role`             | string   | yes      | e.g. `cardiologist`                |
| `month`            | YYYY-MM  | yes      | reporting period                   |
| `hp10_deep_msv`    | number   | yes      | Hp(10) deep dose equivalent (mSv)  |
| `monitors_reported`| 0/1      | no       | whether a reading was returned     |

Real-world data typically comes from a dosimetry provider's export
(monthly badge reports). Map their columns to the schema above in a
spreadsheet or a small preprocessing script before uploading; the
dashboard only needs those five fields.

## Notes

- The bundled dataset is **synthetic** (`generate_example_data.py`) —
  realistic seasonal workload variation, per-worker trends, one worker
  with a rising profile, and occasional high-reading outliers.
- Reference limits are hard-coded at the top of `app.py`
  (`ICRP_ANNUAL_AVG_LIMIT`, `ICRP_SINGLE_YEAR_LIMIT`) and can be adjusted
  to local regulations.
