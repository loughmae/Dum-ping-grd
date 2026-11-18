"""Generate synthetic monthly Hp(10) deep dose records for example use.

Creates five years of monthly dosimeter readings for a cardiology
department: interventional cardiologists (cath lab), plus a few
supporting roles for comparison. Output: data/hp10_dose_example.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROLES = {
    "cardiologist": 8,
    "cardiology_fellow": 3,
    "cath_lab_nurse": 4,
    "radiographer": 2,
}


def _worker_profile(rng: np.random.Generator, role: str) -> dict:
    base = {
        "cardiologist": rng.uniform(0.4, 1.4),
        "cardiology_fellow": rng.uniform(0.2, 0.8),
        "cath_lab_nurse": rng.uniform(0.1, 0.5),
        "radiographer": rng.uniform(0.05, 0.3),
    }[role]
    return {
        "base": base,
        "trend": rng.uniform(-0.004, 0.010),
        "seasonal_amp": rng.uniform(0.0, 0.35),
        "noise_sd": 0.18 * base + 0.01,
        "eye_ratio": rng.uniform(0.4, 1.3),
    }


def generate(months: int = 63, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = pd.Period("2025-06", freq="M")
    periods = pd.period_range(end=end, periods=months, freq="M")

    rows = []
    worker_no = 0
    for role, count in ROLES.items():
        for _ in range(count):
            worker_no += 1
            wid = f"{role[:3].upper()}-{worker_no:03d}"
            name = f"{role.replace('_', ' ').title()} {worker_no:02d}"
            p = _worker_profile(rng, role)
            for i, period in enumerate(periods):
                frac = i / max(len(periods) - 1, 1)
                seasonal = p["seasonal_amp"] * p["base"] * np.sin(2 * np.pi * (period.month - 3) / 12)
                mean = max(p["base"] + p["trend"] * i + seasonal, 0.02)
                dose = rng.normal(mean, p["noise_sd"])

                if role == "cardiologist" and wid.endswith("003") and frac > 0.75:
                    dose *= 1.0 + 1.6 * (frac - 0.75) / 0.25
                if rng.random() < 0.015:
                    dose *= rng.uniform(1.8, 3.0)

                dose = max(round(float(dose), 3), 0.0)
                eye_ratio = p["eye_ratio"]
                if role == "cardiologist" and wid.endswith("003") and frac > 0.6:
                    eye_ratio *= 1.0 + 1.2 * (frac - 0.6) / 0.4
                eye = max(round(float(dose * eye_ratio * rng.uniform(0.8, 1.2)), 3), 0.0)
                rows.append(
                    {
                        "worker_id": wid,
                        "name": name,
                        "role": role,
                        "month": str(period),
                        "hp10_deep_msv": dose,
                        "hp3_eye_msv": eye,
                        "monitors_reported": int(rng.random() < 0.97),
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=63)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "hp10_dose_example.csv")
    args = parser.parse_args()

    df = generate(months=args.months, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
