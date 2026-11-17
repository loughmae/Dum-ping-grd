"""Parsing for dosimetry provider exports and canonical dose CSVs."""
from __future__ import annotations

import re
from io import BytesIO

import pandas as pd

REQUIRED_COLS = {"worker_id", "name", "role", "month", "hp10_deep_msv"}

DOSE_COLS = {
    "hp10_deep_msv": ("hp10", "hp10 deep", "hp(10) deep", "hp10 deep dose"),
    "hp3_eye_msv": ("hp3", "hp3 eye", "hp(3) eye"),
    "hp007_shallow_msv": ("hp007", "hp0.07", "hp(0.07) shallow", "hp(0.07)"),
    "neutron_msv": ("neutron",),
}


def _norm(col: str) -> str:
    return re.sub(r"[\s_#()./]+", "", str(col).strip().lower())


def _find(columns: list[str], *aliases: str) -> str | None:
    normalized = {_norm(c): c for c in columns}
    for alias in aliases:
        key = _norm(alias)
        if key in normalized:
            return normalized[key]
        for nk, orig in normalized.items():
            if nk.startswith(key):
                return orig
    return None


def is_provider_format(columns: list[str]) -> bool:
    return _find(columns, "wearer", "wearer no", "wearer number") is not None and (
        _find(columns, "serial no", "serial") is not None
        or _find(columns, "badge type") is not None
    )


def _clean_wearer(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "control":
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def parse_provider_csv(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(df.columns)
    wearer_col = _find(cols, "wearer", "wearer no", "wearer number")
    name_col = _find(cols, "name")
    serial_col = _find(cols, "serial no", "serial")
    badge_col = _find(cols, "badge type")
    region_col = _find(cols, "body region", "body reg")
    location_col = _find(cols, "location")
    start_col = _find(cols, "start date")
    end_col = _find(cols, "end date")
    notes_col = _find(cols, "notes")

    out = pd.DataFrame(index=df.index)
    wearer = df[wearer_col].map(_clean_wearer) if wearer_col else None
    if wearer is None:
        wearer = pd.Series([None] * len(df), index=df.index)
    is_control = wearer.isna()

    serials = df[serial_col].astype(str).str.strip() if serial_col else ""
    out["worker_id"] = wearer.copy()
    out.loc[is_control, "worker_id"] = [
        f"CONTROL-{s if s and s != 'nan' else i}"
        for i, s in enumerate(serials[is_control], start=1)
    ]
    out["name"] = (
        df[name_col].astype(str).str.strip()
        if name_col
        else out["worker_id"].astype(str)
    )
    out.loc[is_control, "name"] = "Control dosimeter"
    out.loc[out["name"].isin(["nan", ""]), "name"] = out.loc[
        out["name"].isin(["nan", ""]), "worker_id"
    ]

    dates = pd.to_datetime(
        df[end_col] if end_col else df[start_col], errors="coerce", dayfirst=False
    )
    if dates.isna().all():
        dates = pd.to_datetime(df[start_col], errors="coerce", dayfirst=False)
    out["month"] = pd.PeriodIndex(dates, freq="M")
    out["start_date"] = pd.to_datetime(df[start_col], errors="coerce") if start_col else pd.NaT
    out["end_date"] = dates

    for canonical, aliases in DOSE_COLS.items():
        src = _find(cols, *aliases)
        out[canonical] = pd.to_numeric(df[src], errors="coerce") if src else pd.NA

    out["badge_type"] = df[badge_col].astype(str).str.strip() if badge_col else ""
    out["badge_type"] = out["badge_type"].str.replace(r"\.0$", "", regex=True)
    out.loc[out["badge_type"].isin(["nan", "None"]), "badge_type"] = ""
    out["body_region"] = df[region_col].astype(str).str.strip() if region_col else ""
    out["location"] = df[location_col].astype(str).str.strip() if location_col else ""
    out["notes"] = df[notes_col].astype(str).str.strip() if notes_col else ""
    out["monitors_reported"] = out["hp10_deep_msv"].notna().astype(int)

    out = out.dropna(subset=["month"])
    dose_rows = out[list(DOSE_COLS)].notna().any(axis=1)
    out = out[dose_rows]
    return out.reset_index(drop=True)


def parse_canonical_csv(df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    df = df.copy()
    df["month"] = pd.PeriodIndex(df["month"], freq="M")
    df["hp10_deep_msv"] = pd.to_numeric(df["hp10_deep_msv"], errors="coerce")
    df = df.dropna(subset=["hp10_deep_msv"])
    if "monitors_reported" not in df.columns:
        df["monitors_reported"] = 1
    return df.sort_values(["worker_id", "month"]).reset_index(drop=True)


def read_dose_csv(source: bytes | str) -> tuple[pd.DataFrame, bool]:
    df = pd.read_csv(BytesIO(source) if isinstance(source, bytes) else source)
    df = df.dropna(how="all")
    if is_provider_format(list(df.columns)):
        return parse_provider_csv(df), True
    return parse_canonical_csv(df), False
