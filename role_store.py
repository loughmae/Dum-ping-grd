"""Persistent role assignments keyed by wearer number."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

ROLE_FILE = Path(os.environ.get("DOSE_ROLE_FILE", "role_assignments.csv"))
DEFAULT_ROLES = [
    "cardiologist",
    "cardiology_fellow",
    "cath_lab_nurse",
    "radiographer",
    "control",
    "unassigned",
]


def load_roles() -> dict[str, str]:
    if not ROLE_FILE.exists():
        return {}
    df = pd.read_csv(ROLE_FILE, dtype={"worker_id": str, "role": str})
    return dict(zip(df["worker_id"], df["role"]))


def save_roles(roles: dict[str, str]) -> None:
    df = pd.DataFrame(
        sorted(roles.items()), columns=["worker_id", "role"]
    )
    df["updated"] = date.today().isoformat()
    df.to_csv(ROLE_FILE, index=False)


def role_options(assigned: dict[str, str], extra: list[str]) -> list[str]:
    return sorted(set(DEFAULT_ROLES) | set(assigned.values()) | set(extra))
