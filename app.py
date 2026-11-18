"""Hp(10) deep dose trend dashboard.

Streamlit app for exploring personal dose/exposure monitoring data
(e.g. Hp(10) deep dose equivalent for interventional cardiologists)
over 3, 6, 12-month and multi-year windows.

Accepts two CSV formats:
  Provider exports (e.g. Landauer-style): Account, Location, Wearer #,
  Name, ID, Serial No, Badge Type, Body Region, Start Date, End Date,
  HP(10) Deep, HP(3) Eye, HP(0.07) Shallow, Neutron, Notes.
  Canonical: worker_id, name, role, month (YYYY-MM), hp10_deep_msv.

Roles are tagged in the app and remembered per wearer number in
role_assignments.csv.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import dose_io
import role_store

EXAMPLE_CSV = Path(__file__).parent / "data" / "hp10_dose_example.csv"

INF = float("inf")

LOW_DOSE_ANNUAL = 1.0
MIN_DEEP_FOR_RATIO = 0.1
PEER_MULTIPLE_FLAG = 2.0
SIG_T_THRESHOLD = 2.0

METRICS = {
    "HP(10) Deep": {
        "col": "hp10_deep_msv",
        "annual_limit": 20.0,
        "bands": [
            (1.0, "⚪ below Cat B (<1 mSv/y)"),
            (6.0, "🔵 Cat B band (1-6 mSv/y)"),
            (20.0, "🟠 Cat A band (6-20 mSv/y)"),
            (INF, "🔴 over dose limit (>20 mSv/y)"),
        ],
        "lines": [
            (1.0, "Cat B threshold 1 mSv/y", "dot", "#1f77b4"),
            (6.0, "Cat A threshold 6 mSv/y", "dash", "#ff7f0e"),
            (20.0, "Annual dose limit 20 mSv/y", "dash", "#d62728"),
        ],
        "single_year": 50.0,
        "cap_label": "50 mSv single-year cap",
        "five_year": 100.0,
        "five_year_label": "100 mSv in any 5 consecutive years",
        "limit_caption": "IRR19: 20 mSv/y effective dose; Cat B beyond 1 mSv/y, Cat A beyond 6 mSv/y",
    },
    "HP(3) Eye": {
        "col": "hp3_eye_msv",
        "annual_limit": 20.0,
        "bands": [
            (15.0, "🟢 below Cat A threshold (<15 mSv/y)"),
            (20.0, "🟠 Cat A trigger (15-20 mSv/y)"),
            (INF, "🔴 over eye limit (>20 mSv/y)"),
        ],
        "lines": [
            (15.0, "Cat A threshold 15 mSv/y", "dot", "#1f77b4"),
            (20.0, "Eye dose limit 20 mSv/y", "dash", "#d62728"),
        ],
        "single_year": 50.0,
        "cap_label": "50 mSv single-year max",
        "five_year": 100.0,
        "five_year_label": "100 mSv in any 5 consecutive years",
        "limit_caption": "IRR19: 20 mSv/y eye limit (100 mSv/5y, max 50/y); Cat A beyond 15 mSv/y",
    },
    "HP(0.07) Shallow": {
        "col": "hp007_shallow_msv",
        "annual_limit": 500.0,
        "bands": [
            (500.0, "🟢 ok (<500 mSv/y)"),
            (INF, "🔴 over skin limit (>500 mSv/y)"),
        ],
        "lines": [(500.0, "Skin limit 500 mSv/y", "dash", "#d62728")],
        "single_year": None,
        "cap_label": None,
        "five_year": None,
        "five_year_label": None,
        "limit_caption": "IRR19: skin limit 500 mSv/y averaged over 1 cm²",
    },
    "Neutron": {
        "col": "neutron_msv",
        "annual_limit": 20.0,
        "bands": [
            (20.0, "🟢 ok (<20 mSv/y)"),
            (INF, "🔴 over limit (>20 mSv/y)"),
        ],
        "lines": [(20.0, "Dose limit 20 mSv/y", "dash", "#d62728")],
        "single_year": None,
        "cap_label": None,
        "five_year": None,
        "five_year_label": None,
        "limit_caption": "Dose limit 20 mSv/y",
    },
}


def band_for(t12: float, bands: list[tuple[float, str]]) -> str:
    for value, label in bands:
        if t12 < value:
            return label
    return bands[-1][1]


def add_limit_lines(fig: go.Figure, cfg: dict) -> None:
    for value, label, dash, color in cfg["lines"]:
        fig.add_hline(
            y=value, line_dash=dash, annotation_text=label, line_color=color,
            annotation_position="top left",
        )
    if cfg["single_year"] is not None:
        fig.add_hline(
            y=cfg["single_year"], line_dash="dot",
            annotation_text=cfg["cap_label"], line_color="#d62728",
            annotation_position="top left",
        )

WINDOW_CHOICES = {
    "3 months": 3,
    "6 months": 6,
    "12 months": 12,
    "24 months": 24,
    "5 years (all)": 60,
}

st.set_page_config(page_title="Dose Trends", page_icon="☢️", layout="wide")


def ensure_example_csv() -> Path:
    if not EXAMPLE_CSV.exists():
        from generate_example_data import generate
        EXAMPLE_CSV.parent.mkdir(parents=True, exist_ok=True)
        generate().to_csv(EXAMPLE_CSV, index=False)
    return EXAMPLE_CSV


@st.cache_data
def load_csv(source: bytes | None) -> tuple[pd.DataFrame, bool]:
    if source is None:
        df, is_provider = dose_io.read_dose_csv(str(ensure_example_csv()))
    else:
        df, is_provider = dose_io.read_dose_csv(source)
    return df, is_provider


def apply_roles(df: pd.DataFrame) -> pd.DataFrame:
    assigned = role_store.load_roles()
    if "role" in df.columns:
        known = df.dropna(subset=["role"])[["worker_id", "role"]].drop_duplicates()
        new = {
            str(w): str(r)
            for w, r in known.itertuples(index=False)
            if str(w) not in assigned
        }
        if new:
            assigned.update(new)
            role_store.save_roles(assigned)
        df = df.drop(columns=["role"])
    df = df.copy()
    df["worker_id"] = df["worker_id"].astype(str)
    df["role"] = df["worker_id"].map(assigned).fillna("unassigned")
    return df, assigned


def add_rolling(df: pd.DataFrame, windows: list[int], col: str) -> pd.DataFrame:
    out = df.copy()
    for w in windows:
        out[f"roll_{w}m"] = (
            out.groupby("worker_id", group_keys=False)[col]
            .apply(lambda s: s.rolling(w, min_periods=max(w // 2, 1)).mean())
        )
    return out


def kpi_card(label: str, value: str, delta: str = "", help: str = "") -> None:
    st.metric(label, value, delta=delta or None, help=help or None)


def monthly_trend_plot(
    sub: pd.DataFrame, window: int, aggregate: str, col: str, metric: str
) -> go.Figure:
    freq = {"Monthly": "M", "Quarterly": "Q"}[aggregate]
    agg = (
        sub.groupby(["worker_id", "name", sub["month"].dt.to_timestamp(freq=freq)])
        .agg(dose=(col, "sum"))
        .reset_index()
        .rename(columns={"month": "period"})
    )
    agg["rolling"] = (
        agg.groupby("worker_id", group_keys=False)["dose"]
        .apply(lambda s: s.rolling(window, min_periods=max(window // 2, 1)).mean())
    )
    fig = go.Figure()
    for wid, grp in agg.groupby("worker_id"):
        name = grp["name"].iloc[0]
        fig.add_trace(
            go.Bar(
                x=grp["period"],
                y=grp["dose"],
                name=name,
                marker=dict(opacity=0.35),
                legendgroup=wid,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=grp["period"],
                y=grp["rolling"],
                mode="lines",
                name=f"{name} ({window}p avg)",
                line=dict(width=2),
                legendgroup=wid,
            )
        )
    unit = "quarter" if aggregate == "Quarterly" else "month"
    fig.update_layout(
        barmode="relative",
        template="plotly_white",
        height=440,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        yaxis_title=f"{metric} per {unit} (mSv)",
        xaxis_title="Period",
        hovermode="x unified",
    )
    return fig


def rolling_windows_plot(sub: pd.DataFrame, col: str, metric: str) -> go.Figure:
    fig = go.Figure()
    colors = px.colors.qualitative.Set2
    for idx, (label, w) in enumerate(WINDOW_CHOICES.items()):
        if label == "5 years (all)":
            continue
        roll = (
            sub.groupby("worker_id", group_keys=False)[col]
            .apply(lambda s: s.rolling(w, min_periods=max(w // 2, 1)).mean())
        )
        mean = roll.groupby(sub["month"]).mean()
        fig.add_trace(
            go.Scatter(
                x=mean.index.to_timestamp(),
                y=mean.values,
                mode="lines",
                name=f"{label} rolling mean",
                line=dict(width=2, color=colors[idx % len(colors)]),
            )
        )
    fig.update_layout(
        template="plotly_white",
        height=360,
        yaxis_title=f"Cohort mean {metric} (mSv/month)",
        xaxis_title="Month",
        hovermode="x unified",
    )
    return fig


def trailing_cumulative_plot(
    sub: pd.DataFrame, col: str, metric: str, cfg: dict
) -> go.Figure:
    roll_sum = (
        sub.groupby("worker_id", group_keys=False)[col]
        .apply(lambda s: s.rolling(12, min_periods=12).sum())
    )
    tmp = sub.assign(trailing12=roll_sum)
    by_month = tmp.groupby("month")["trailing12"].agg(["mean", "max"]).reset_index()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=by_month["month"].dt.to_timestamp(),
            y=by_month["max"],
            name="Highest worker (12-mo sum)",
            line=dict(width=2, color="#d62728"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=by_month["month"].dt.to_timestamp(),
            y=by_month["mean"],
            name="Cohort mean (12-mo sum)",
            line=dict(width=2, color="#1f77b4"),
        )
    )
    if cfg.get("five_year") is not None:
        roll5 = (
            sub.groupby("worker_id", group_keys=False)[col]
            .apply(lambda s: s.rolling(60, min_periods=60).sum())
        )
        tmp5 = sub.assign(trailing60=roll5).dropna(subset=["trailing60"])
        if not tmp5.empty:
            by_month5 = tmp5.groupby("month")["trailing60"].agg(["mean", "max"]).reset_index()
            fig.add_trace(
                go.Scatter(
                    x=by_month5["month"].dt.to_timestamp(),
                    y=by_month5["max"],
                    name="Highest worker (5-yr sum)",
                    line=dict(width=2, color="#9467bd", dash="dot"),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=by_month5["month"].dt.to_timestamp(),
                    y=by_month5["mean"],
                    name="Cohort mean (5-yr sum)",
                    line=dict(width=2, color="#8c564b", dash="dot"),
                )
            )
    add_limit_lines(fig, cfg)
    fig.update_layout(
        template="plotly_white",
        height=360,
        yaxis_title=f"Trailing 12-month {metric} (mSv)",
        xaxis_title="Month",
        hovermode="x unified",
    )
    return fig


def worker_comparison_plot(
    sub: pd.DataFrame, col: str, metric: str, cfg: dict
) -> go.Figure:
    sub = sub.copy()
    sub["year"] = sub["month"].dt.year
    yearly = sub.groupby(["worker_id", "name", "role", "year"])[col].sum().reset_index()
    fig = px.bar(
        yearly,
        x="year",
        y=col,
        color="role",
        facet_col="name",
        facet_col_wrap=4,
        labels={col: f"Annual {metric} (mSv)", "year": "Year"},
    )
    add_limit_lines(fig, cfg)
    fig.update_layout(template="plotly_white", height=520, showlegend=True)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    return fig


def band_index(band_label: str, bands: list[tuple[float, str]]) -> int:
    for idx, (_, label) in enumerate(bands):
        if label == band_label:
            return idx
    return -1


def project_next_year(grp: pd.DataFrame, col: str) -> tuple[float | None, str]:
    grp = grp.sort_values("month")
    n_months = grp["month"].nunique()
    climatology = grp.groupby(grp["month"].dt.month)[col].mean()
    if n_months >= 24 and len(climatology) == 12 and climatology.notna().all():
        return float(climatology.sum()), "seasonal"
    if n_months >= 6:
        return float(grp[col].tail(6).mean() * 12), "run-rate"
    return None, "insufficient"


def attention_table(sub: pd.DataFrame, col: str, cfg: dict) -> pd.DataFrame:
    t12_map = sub.groupby("worker_id").apply(
        lambda g: g.sort_values("month")[col].tail(12).sum()
    )
    role_map = sub.groupby("worker_id")["role"].first()
    role_sizes = role_map.value_counts()
    role_median = t12_map.groupby(role_map).median()
    cohort_median = float(t12_map.median())
    rows = []
    for wid, grp in sub.groupby("worker_id"):
        grp = grp.sort_values("month")
        t12 = grp[col].tail(12).sum()
        months = grp["month"].tail(12).nunique()
        projected, method = project_next_year(grp, col)
        current_band = band_for(t12, cfg["bands"])
        if projected is None:
            projected_band = "— insufficient history"
            direction = "—"
            projected_display = None
        else:
            projected_band = band_for(projected, cfg["bands"])
            ci, pi = band_index(current_band, cfg["bands"]), band_index(projected_band, cfg["bands"])
            direction = "⬆️ worsening" if pi > ci else "⬇️ improving" if pi < ci else "→ stable"
            projected_display = round(projected, 2)
        pct = t12 / cfg["annual_limit"] * 100 if cfg["annual_limit"] else 0
        peers_n = int(role_sizes.get(grp["role"].iloc[0], 0))
        peer_med = (
            float(role_median.get(grp["role"].iloc[0], cohort_median))
            if peers_n >= 3 and float(role_median.get(grp["role"].iloc[0], 0)) > 0
            else cohort_median
        )
        vs_peers = float(t12) / peer_med if peer_med > 0 else np.nan
        peers_label = (
            f"{vs_peers:.1f}× role" if peers_n >= 3 else f"{vs_peers:.1f}× cohort"
        )
        if np.isfinite(vs_peers) and vs_peers >= PEER_MULTIPLE_FLAG:
            peers_label += " ⚠️"
        rows.append(
            {
                "worker": grp["name"].iloc[0],
                "role": grp["role"].iloc[0],
                "rolling 12-mo (mSv)": round(float(t12), 2),
                "months reported": months,
                "% of annual limit": round(float(pct), 1),
                "current band": current_band,
                "projected next 12-mo (mSv)": projected_display,
                "projected band": projected_band,
                "direction": direction,
                "projection method": method if projected is not None else "—",
                "vs peers": peers_label,
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values("% of annual limit", ascending=False)
        .reset_index(drop=True)
    )


def dose_heatmap(sub: pd.DataFrame, col: str, metric: str, n_months: int = 24) -> go.Figure:
    monthly = (
        sub.groupby(["name", "month"])[col].sum().reset_index()
    )
    cutoff = sub["month"].max() - (n_months - 1)
    recent = monthly[monthly["month"] >= cutoff]
    piv = recent.pivot(index="name", columns="month", values=col).fillna(0.0)
    totals = sub.groupby("name")[col].sum().sort_values(ascending=False)
    piv = piv.loc[[n for n in totals.index if n in piv.index]]
    piv.columns = [p.strftime("%b %y") for p in piv.columns]
    fig = px.imshow(
        piv,
        aspect="auto",
        color_continuous_scale="YlOrRd",
        labels=dict(color=f"{metric} (mSv)"),
    )
    fig.update_layout(
        template="plotly_white",
        height=max(320, 28 * len(piv) + 120),
        yaxis_title="Worker",
        xaxis_title="Month",
    )
    return fig


def significant_trends(
    sub: pd.DataFrame, col: str, months: int = 12, min_months: int = 8,
    t_thresh: float = SIG_T_THRESHOLD,
) -> list[dict]:
    results = []
    for wid, grp in sub.groupby("worker_id"):
        g = grp.sort_values("month").tail(months)
        y = g[col].to_numpy(dtype=float)
        if len(y) < min_months:
            continue
        x = np.arange(len(y), dtype=float)
        sxx = float(((x - x.mean()) ** 2).sum())
        if sxx == 0:
            continue
        slope, intercept = np.polyfit(x, y, 1)
        resid = y - (slope * x + intercept)
        dof = len(y) - 2
        sse = float((resid ** 2).sum())
        se = np.sqrt(sse / dof / sxx) if dof > 0 and sse > 0 else np.inf
        t = slope / se if se and np.isfinite(se) and se > 0 else 0.0
        if abs(t) > t_thresh:
            results.append(
                {
                    "worker_id": wid,
                    "name": g["name"].iloc[0],
                    "slope": float(slope),
                    "t": float(t),
                    "months": list(g["month"]),
                    "actual": y,
                    "fit": slope * x + intercept,
                }
            )
    return results


def significant_trends_plot(results: list[dict], metric: str) -> go.Figure:
    fig = go.Figure()
    for r in results:
        color = "#d62728" if r["slope"] > 0 else "#2ca02c"
        label = f'{r["name"]} (t={r["t"]:.1f})'
        stamps = [p.to_timestamp() for p in r["months"]]
        fig.add_trace(
            go.Scatter(
                x=stamps, y=r["actual"], mode="lines+markers",
                name=label, legendgroup=label, line=dict(color=color),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=stamps, y=r["fit"], mode="lines",
                name=None, legendgroup=label, showlegend=False,
                line=dict(color=color, dash="dash", width=1),
            )
        )
    fig.update_layout(
        template="plotly_white",
        height=360,
        yaxis_title=f"{metric} (mSv/month)",
        xaxis_title="Month",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def low_dose_table(
    sub: pd.DataFrame, col: str, threshold: float = LOW_DOSE_ANNUAL
) -> pd.DataFrame:
    rows = []
    for wid, grp in sub.groupby("worker_id"):
        g = grp.sort_values("month")
        t12 = g[col].tail(12).sum()
        expected = g["month"].max().ordinal - g["month"].min().ordinal + 1
        reported = g["month"].nunique()
        gaps = expected - reported
        notes = []
        if gaps > 0:
            notes.append(f"🟠 {gaps} missing month(s) — verify badge wear/return")
        if t12 <= threshold:
            notes.append(
                f"🔵 ≤ {threshold:g} mSv/y — candidate for reduced surveillance "
                f"(no individual monitoring required at or below this level)"
            )
        if not notes:
            notes.append("🟢 routine individual monitoring")
        rows.append(
            {
                "worker": g["name"].iloc[0],
                "role": g["role"].iloc[0],
                "rolling 12-mo (mSv)": round(float(t12), 2),
                "months in service": expected,
                "months returned": reported,
                "gaps": gaps,
                "surveillance note": "; ".join(notes),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["gaps", "rolling 12-mo (mSv)"], ascending=[False, True])
        .reset_index(drop=True)
    )


def eye_deep_pairs(df: pd.DataFrame, min_deep: float = MIN_DEEP_FOR_RATIO) -> pd.DataFrame:
    cols_needed = {"hp10_deep_msv", "hp3_eye_msv"} <= set(df.columns)
    if not cols_needed:
        return pd.DataFrame()
    records = []
    for (wid, month), grp in df.groupby(["worker_id", "month"]):
        deep_ok = grp["hp10_deep_msv"].notna() & (grp["hp10_deep_msv"] >= min_deep)
        eye_ok = grp["hp3_eye_msv"].notna()
        same_badge = grp[deep_ok & eye_ok]
        if not same_badge.empty:
            for _, r in same_badge.iterrows():
                region = str(getattr(r, "body_region", "") or "").lower()
                if "eye" in region or "temple" in region or "forehead" in region:
                    basis = "eye-position dosimeter (both quantities)"
                else:
                    basis = "same badge"
                records.append(
                    {
                        "worker_id": wid, "name": grp["name"].iloc[0],
                        "role": grp["role"].iloc[0], "month": month,
                        "ratio": float(r["hp3_eye_msv"] / r["hp10_deep_msv"]),
                        "basis": basis,
                    }
                )
            continue
        if deep_ok.any() and eye_ok.any():
            eye_rows = grp[eye_ok]
            deep_rows = grp[deep_ok]
            records.append(
                {
                    "worker_id": wid, "name": grp["name"].iloc[0],
                    "role": grp["role"].iloc[0], "month": month,
                    "ratio": float(eye_rows["hp3_eye_msv"].sum() / deep_rows["hp10_deep_msv"].sum()),
                    "basis": "eye badge vs chest badge (cross-badge)",
                }
            )
    return pd.DataFrame(records)


def eye_deep_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for wid, grp in pairs.sort_values("month").groupby("worker_id"):
        r_vals = grp["ratio"].to_numpy(dtype=float)
        basis = grp["basis"].mode().iloc[0]
        recent = r_vals[-6:]
        baseline = r_vals[:-6]
        if len(recent) >= 4 and len(baseline) >= 4:
            m1, m2 = recent.mean(), baseline.mean()
            v1 = recent.var(ddof=1)
            v2 = baseline.var(ddof=1)
            se = np.sqrt(v1 / len(recent) + v2 / len(baseline))
            drift_t = (m1 - m2) / se if se > 0 else 0.0
            pct_drift = (m1 / m2 - 1) * 100 if m2 > 0 else 0.0
            flag = "🟠 significant ratio drift" if abs(drift_t) > 2 else "🟢 stable"
        else:
            drift_t, pct_drift = np.nan, np.nan
            flag = "— building history"
        rows.append(
            {
                "worker": grp["name"].iloc[0],
                "role": grp["role"].iloc[0],
                "paired months": len(grp),
                "mean eye:deep ratio": round(float(r_vals.mean()), 2),
                "recent mean ratio": round(float(recent.mean()), 2),
                "drift": f"{pct_drift:+.0f}%" if np.isfinite(pct_drift) else "—",
                "status": flag,
                "basis": basis,
            }
        )
    return pd.DataFrame(rows)


def eye_deep_ratio_plot(pairs: pd.DataFrame) -> go.Figure:
    fig = px.line(
        pairs, x=pairs["month"].dt.to_timestamp(), y="ratio", color="name",
        markers=True, labels={"y": "Eye : Deep ratio", "month": "Month", "name": "Worker"},
    )
    fig.add_hline(
        y=float(pairs["ratio"].median()), line_dash="dot",
        annotation_text="cohort median", line_color="grey",
    )
    fig.update_layout(
        template="plotly_white", height=380,
        yaxis_title="Eye : Deep dose ratio",
        xaxis_title="Month",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def main() -> None:
    st.title("☢️ Radiation Dose Trend Dashboard")
    st.caption(
        "Occupational exposure trends for cardiology staff — 3, 6, 12-month "
        "rolling views plus multi-year history, by dose metric."
    )

    with st.sidebar:
        st.header("Data")
        uploaded = st.file_uploader("Upload dose CSV", type="csv")
        st.caption(
            "Accepts dosimetry provider exports (Wearer #, HP(10) Deep, ...) "
            "or canonical CSVs (worker_id, name, role, month, hp10_deep_msv). "
            "Leave empty to use the bundled 5-year cardiology example."
        )

    try:
        df, is_provider = load_csv(
            uploaded.getvalue() if uploaded is not None else None
        )
        df, assigned_roles = apply_roles(df)
    except (ValueError, TypeError) as exc:
        st.error(f"Could not parse the dose data: {exc}")
        st.stop()

    available_metrics = [
        label for label, cfg in METRICS.items()
        if cfg["col"] in df.columns and df[cfg["col"]].notna().any()
    ]
    unassigned = df.loc[df["role"] == "unassigned", "worker_id"].nunique()
    with st.expander(
        f"🏷️ Worker roles — {unassigned} unassigned",
        expanded=0 < unassigned <= 20,
    ):
        st.caption(
            "Tag each wearer with a role. Assignments are remembered per "
            "wearer number in `role_assignments.csv` and applied automatically "
            "to future uploads."
        )
        worker_list = df[["worker_id", "name", "role"]].drop_duplicates().sort_values(["role", "name"])
        if "custom_roles" not in st.session_state:
            st.session_state["custom_roles"] = []
        new_role = st.text_input("Add a new role option")
        if st.button("Add role option") and new_role.strip():
            st.session_state["custom_roles"].append(new_role.strip().lower())
            st.rerun()
        options = role_store.role_options(assigned_roles, st.session_state["custom_roles"])
        search = st.text_input("Find wearer (ID or name)")
        visible = worker_list
        if search:
            s = search.lower()
            visible = worker_list[
                worker_list["worker_id"].str.lower().str.contains(s, na=False)
                | worker_list["name"].str.lower().str.contains(s, na=False)
            ]
        changed = False
        for row in visible.itertuples(index=False):
            current = assigned_roles.get(row.worker_id, "unassigned")
            opts = options if current in options else [current, *options]
            chosen = st.selectbox(
                f"{row.worker_id} — {row.name}",
                opts,
                index=opts.index(current),
                key=f"role_{row.worker_id}",
            )
            if chosen != current:
                assigned_roles[row.worker_id] = chosen
                changed = True
        if changed:
            role_store.save_roles(assigned_roles)
            st.cache_data.clear()
            st.rerun()

    with st.sidebar:
        st.header("Filters")
        metric_label = st.selectbox("Dose metric", available_metrics)
        cfg = METRICS[metric_label]
        dose_col = cfg["col"]
        roles = sorted(df["role"].unique())
        default_roles = [r for r in roles if r != "control"]
        selected_roles = st.multiselect("Role", roles, default=default_roles)
        workers = df[df["role"].isin(selected_roles)]["name"].sort_values().unique()
        selected_workers = st.multiselect("Workers (empty = all)", list(workers))
        window_label = st.select_slider(
            "Trend window", options=list(WINDOW_CHOICES), value="12 months"
        )
        aggregate = st.radio("Aggregation", ["Monthly", "Quarterly"], horizontal=True)
        date_min, date_max = df["month"].min(), df["month"].max()
        date_range = st.slider(
            "History range",
            min_value=date_min.ordinal,
            max_value=date_max.ordinal,
            value=(date_min.ordinal, date_max.ordinal),
            format="",
        )
        start = pd.Period(ordinal=date_range[0], freq="M")
        end = pd.Period(ordinal=date_range[1], freq="M")

    window = WINDOW_CHOICES[window_label]
    mask = df["role"].isin(selected_roles) & df["month"].between(start, end)
    if selected_workers:
        mask &= df["name"].isin(selected_workers)
    sub = df[mask].copy()
    sub = sub[sub[dose_col].notna()]
    if sub.empty:
        st.warning(f"No {metric_label} readings for the selected filters.")
        st.stop()

    numeric_cols = [
        c for c in ["hp10_deep_msv", "hp3_eye_msv", "hp007_shallow_msv", "neutron_msv"]
        if c in sub.columns
    ]
    sub = (
        sub.groupby(["worker_id", "name", "role", "month"], as_index=False)[numeric_cols]
        .sum()
        .sort_values("month")
        .reset_index(drop=True)
    )
    sub = add_rolling(sub, [3, 6, 12], dose_col)

    latest = sub["month"].max()
    latest_row = sub[sub["month"] == latest]
    trailing = (
        sub.groupby("worker_id")[dose_col]
        .apply(lambda s: s.tail(12).sum())
        .sort_values(ascending=False)
    )
    top_worker = trailing.index[0]
    top_name = sub.loc[sub["worker_id"] == top_worker, "name"].iloc[0]
    prev_12 = (
        sub[sub["month"] < latest - 11]
        .groupby("worker_id")[dose_col]
        .apply(lambda s: s.tail(12).sum())
        .mean()
    )

    st.subheader(f"Key indicators — {metric_label}, through {latest.strftime('%b %Y')}")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi_card(
            "Latest month (mean)",
            f"{latest_row[dose_col].mean():.2f} mSv",
            help=f"Mean {metric_label} across selected workers in the latest reported month.",
        )
    with c2:
        kpi_card("3-month rolling mean", f"{sub['roll_3m'].tail(1).mean():.2f} mSv/mo")
    with c3:
        kpi_card("6-month rolling mean", f"{sub['roll_6m'].tail(1).mean():.2f} mSv/mo")
    with c4:
        kpi_card("12-month rolling mean", f"{sub['roll_12m'].tail(1).mean():.2f} mSv/mo")
    with c5:
        worst = trailing.iloc[0]
        kpi_card(
            "Highest trailing 12-mo",
            f"{worst:.1f} mSv",
            f"{top_name}",
            help=f"Sum of the last 12 months for the most exposed selected worker, "
            f"against the {cfg['annual_limit']:g} mSv/y annual limit.",
        )

    pct_of_limit = worst / cfg["annual_limit"] * 100
    change_note = ""
    if not np.isnan(prev_12) and prev_12 > 0:
        change_note = (
            f" Cohort trailing 12-month dose changed "
            f"{(trailing.mean() / prev_12 - 1) * 100:+.1f}% versus the previous "
            f"12-month block."
        )
    st.caption(
        f"Highest worker sits in band: {band_for(worst, cfg['bands'])} "
        f"({pct_of_limit:.0f}% of the {cfg['annual_limit']:g} mSv/y limit).{change_note} "
        f"Note: {cfg['limit_caption']}. Classification bands are prospective "
        f"(expected dose); the trailing 12-month sum is a retrospective proxy."
    )

    st.subheader("Worker attention list")
    attn = attention_table(sub, dose_col, cfg)
    st.dataframe(attn, width="stretch", hide_index=True)
    st.caption(
        "Current band uses the rolling 12-month sum. The projection annualises "
        "what the worker would receive in the next year: with 24+ months of "
        "history it uses each calendar month's historical mean (seasonal), "
        "otherwise the last-6-month run-rate, and below 6 reported months no "
        "projection is shown. Classification itself is a prospective RPO "
        "decision."
    )
    flagged = attn[
        attn["current band"].str.contains("🔴|🟠", regex=True)
        | attn["projected band"].str.contains("🔴|🟠", regex=True)
    ]
    if not flagged.empty:
        st.caption(
            f"{len(flagged)} worker(s) at or above a classification trigger now or "
            f"on projection — review workload, apron integrity and "
            f"radiation-protection practices."
        )

    st.subheader(f"Dose trend — {window_label} window")
    st.plotly_chart(
        monthly_trend_plot(sub, window, aggregate, dose_col, metric_label),
        width="stretch",
    )

    st.subheader(f"Statistically significant dose trends — {metric_label}")
    sig = significant_trends(sub, dose_col)
    if sig:
        for r in sorted(sig, key=lambda r: r["slope"], reverse=True):
            sign = "rising" if r["slope"] > 0 else "falling"
            st.caption(
                f"**{r['name']}** — {sign} at {r['slope']:+.3f} mSv/month "
                f"(t={r['t']:.1f}) over the last 12 reported months"
            )
        st.plotly_chart(significant_trends_plot(sig, metric_label), width="stretch")
    else:
        st.caption(
            "No statistically significant monthly trend for any selected worker "
            f"(|t| > {SIG_T_THRESHOLD:g}, ≥ 8 reported months)."
        )

    st.subheader("Low-dose & badge-compliance watch")
    st.dataframe(low_dose_table(sub, dose_col), width="stretch", hide_index=True)
    st.caption(
        "Workers at or below 1 mSv/y rolling effective dose may not require "
        "individual monitoring under IRR19 (RPO decision). Missing months are "
        "flagged separately: a low reported dose with badge gaps suggests "
        "badges not worn or not returned, not low exposure."
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Rolling means (cohort)")
        st.plotly_chart(rolling_windows_plot(sub, dose_col, metric_label), width="stretch")
    with right:
        st.subheader("Trailing 12-month cumulative vs limits")
        st.plotly_chart(
            trailing_cumulative_plot(sub, dose_col, metric_label, cfg), width="stretch"
        )

    st.subheader(f"Dose heatmap — last 24 months ({metric_label})")
    st.plotly_chart(dose_heatmap(sub, dose_col, metric_label), width="stretch")

    pairs = eye_deep_pairs(df[mask])
    if not pairs.empty:
        st.subheader("Eye : deep dose ratio (HP(3) : HP(10))")
        st.dataframe(eye_deep_summary(pairs), width="stretch", hide_index=True)
        st.plotly_chart(eye_deep_ratio_plot(pairs), width="stretch")
        st.caption(
            "Ratio meaning depends on data basis: values recorded on the same "
            "badge (dual-quantity chip) reflect attenuation at that badge's "
            "position; values from a dedicated eye dosimeter versus a chest "
            "badge are cross-badge and reflect apron shielding plus geometry. "
            "Ratios are suppressed where the deep dose is below "
            f"{MIN_DEEP_FOR_RATIO:g} mSv (denominator too small to be meaningful). "
            "Flags mark statistically significant drift in a worker's own "
            "baseline, not an absolute regulatory limit."
        )

    st.subheader("Annual dose by worker")
    st.plotly_chart(
        worker_comparison_plot(sub, dose_col, metric_label, cfg),
        width="stretch",
    )

    with st.expander("Recent data"):
        base_cols = ["month", "worker_id", "name", "role", dose_col]
        extra_cols = [
            c for c in [
                "hp3_eye_msv", "hp007_shallow_msv", "neutron_msv",
                "badge_type", "location",
            ]
            if c in sub.columns and c != dose_col
        ]
        show = sub[base_cols + extra_cols].copy()
        show["month"] = show["month"].astype(str)
        st.dataframe(show.tail(200), width="stretch")
        st.download_button(
            "Download filtered data (CSV)",
            show.to_csv(index=False).encode(),
            file_name="dose_filtered.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
