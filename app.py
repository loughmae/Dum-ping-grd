"""Hp(10) deep dose trend dashboard.

Streamlit app for exploring personal dose/exposure monitoring data
(e.g. Hp(10) deep dose equivalent for interventional cardiologists)
over 3, 6, 12-month and multi-year windows.

Expected CSV columns:
    worker_id, name, role, month (YYYY-MM), hp10_deep_msv
Optional:
    monitors_reported (0/1, whether a reading was reported)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

REQUIRED_COLS = {"worker_id", "name", "role", "month", "hp10_deep_msv"}
EXAMPLE_CSV = Path(__file__).parent / "data" / "hp10_dose_example.csv"

ICRP_ANNUAL_AVG_LIMIT = 20.0
ICRP_SINGLE_YEAR_LIMIT = 50.0

WINDOW_CHOICES = {
    "3 months": 3,
    "6 months": 6,
    "12 months": 12,
    "24 months": 24,
    "5 years (all)": 60,
}

st.set_page_config(page_title="Hp(10) Dose Trends", page_icon="☢️", layout="wide")


@st.cache_data
def load_csv(source: bytes | None) -> pd.DataFrame:
    if source is None:
        df = pd.read_csv(EXAMPLE_CSV)
    else:
        df = pd.read_csv(pd.io.common.BytesIO(source))
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    df["month"] = pd.PeriodIndex(df["month"], freq="M")
    df["hp10_deep_msv"] = pd.to_numeric(df["hp10_deep_msv"], errors="coerce")
    df = df.dropna(subset=["hp10_deep_msv"])
    if "monitors_reported" not in df.columns:
        df["monitors_reported"] = 1
    return df.sort_values(["worker_id", "month"]).reset_index(drop=True)


def add_rolling(df: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    out = df.copy()
    for w in windows:
        out[f"roll_{w}m"] = (
            out.groupby("worker_id", group_keys=False)["hp10_deep_msv"]
            .apply(lambda s: s.rolling(w, min_periods=max(w // 2, 1)).mean())
        )
        out[f"roll_{w}m_sum"] = (
            out.groupby("worker_id", group_keys=False)["hp10_deep_msv"]
            .apply(lambda s: s.rolling(w, min_periods=w).sum())
        )
    return out


def kpi_card(label: str, value: str, delta: str = "", help: str = "") -> None:
    st.metric(label, value, delta=delta or None, help=help or None)

def monthly_trend_plot(sub: pd.DataFrame, window: int, aggregate: str) -> go.Figure:
    freq = {"Monthly": "M", "Quarterly": "Q"}[aggregate]
    agg = (
        sub.groupby(["worker_id", "name", sub["month"].dt.to_timestamp(freq=freq)])
        .agg(dose=("hp10_deep_msv", "sum"))
        .reset_index()
        .rename(columns={"month": "period"})
    )
    agg[f"rolling_{window}p"] = (
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
                y=grp[f"rolling_{window}p"],
                mode="lines",
                name=f"{name} ({window}p avg)",
                line=dict(width=2),
                legendgroup=wid,
            )
        )
    fig.update_layout(
        barmode="relative",
        template="plotly_white",
        height=440,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        yaxis_title=f"Dose per {aggregate.lower()[:-2] if aggregate == 'Quarterly' else 'month'} (mSv)",
        xaxis_title="Period",
        hovermode="x unified",
    )
    return fig


def rolling_windows_plot(sub: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    colors = px.colors.qualitative.Set2
    for idx, (label, w) in enumerate(WINDOW_CHOICES.items()):
        if label == "5 years (all)":
            continue
        roll = (
            sub.groupby("worker_id", group_keys=False)["hp10_deep_msv"]
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
        yaxis_title="Cohort mean Hp(10) (mSv/month)",
        xaxis_title="Month",
        hovermode="x unified",
    )
    return fig


def trailing_cumulative_plot(sub: pd.DataFrame) -> go.Figure:
    roll_sum = (
        sub.groupby("worker_id", group_keys=False)["hp10_deep_msv"]
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
    fig.add_hline(
        y=ICRP_ANNUAL_AVG_LIMIT,
        line_dash="dash",
        annotation_text="ICRP 20 mSv/y (5-yr mean)",
        line_color="#ff7f0e",
    )
    fig.add_hline(
        y=ICRP_SINGLE_YEAR_LIMIT,
        line_dash="dot",
        annotation_text="50 mSv single-year cap",
        line_color="#d62728",
    )
    fig.update_layout(
        template="plotly_white",
        height=360,
        yaxis_title="Trailing 12-month Hp(10) (mSv)",
        xaxis_title="Month",
        hovermode="x unified",
    )
    return fig


def worker_comparison_plot(sub: pd.DataFrame) -> go.Figure:
    sub = sub.copy()
    sub["year"] = sub["month"].dt.year
    yearly = (
        sub.groupby(["worker_id", "name", "role", "year"])["hp10_deep_msv"]
        .sum()
        .reset_index()
    )
    fig = px.bar(
        yearly,
        x="year",
        y="hp10_deep_msv",
        color="role",
        facet_col="name",
        facet_col_wrap=4,
        labels={"hp10_deep_msv": "Annual Hp(10) (mSv)", "year": "Year"},
    )
    fig.add_hline(
        y=ICRP_ANNUAL_AVG_LIMIT,
        line_dash="dash",
        line_color="#ff7f0e",
        annotation_text="20 mSv/y",
    )
    fig.update_layout(template="plotly_white", height=520, showlegend=True)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    return fig


def main() -> None:
    st.title("☢️ Hp(10) Deep Dose Trend Dashboard")
    st.caption(
        "Occupational exposure trends for cardiology staff — 3, 6, 12-month "
        "rolling views plus multi-year history. Reference limits: ICRP 20 mSv/y "
        "averaged over 5 years, 50 mSv in any single year."
    )

    with st.sidebar:
        st.header("Data")
        uploaded = st.file_uploader("Upload dose CSV", type="csv")
        st.caption(
            "Columns: worker_id, name, role, month (YYYY-MM), "
            "hp10_deep_msv. Leave empty to use the bundled 5-year "
            "cardiology example dataset."
        )

    try:
        df = load_csv(uploaded.getvalue() if uploaded is not None else None)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    with st.sidebar:
        st.header("Filters")
        roles = sorted(df["role"].unique())
        selected_roles = st.multiselect("Role", roles, default=roles)
        workers = df[df["role"].isin(selected_roles)]["name"].sort_values().unique()
        selected_workers = st.multiselect(
            "Workers (empty = all)", list(workers),
            default=None if len(workers) <= 12 else list(workers)[:12],
        )
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
    if sub.empty:
        st.warning("No data for the selected filters.")
        st.stop()

    sub = add_rolling(sub, [3, 6, 12])

    latest = sub["month"].max()
    latest_row = sub[sub["month"] == latest]
    trailing = (
        sub.groupby("worker_id")["hp10_deep_msv"]
        .apply(lambda s: s.tail(12).sum())
        .sort_values(ascending=False)
    )
    top_worker = trailing.index[0]
    top_name = sub.loc[sub["worker_id"] == top_worker, "name"].iloc[0]
    prev_12 = (
        sub[sub["month"] < latest - 11]
        .groupby("worker_id")["hp10_deep_msv"]
        .apply(lambda s: s.tail(12).sum())
        .mean()
    )

    st.subheader(f"Key indicators — through {latest.strftime('%b %Y')}")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi_card(
            "Latest month (mean)",
            f"{latest_row['hp10_deep_msv'].mean():.2f} mSv",
            help="Mean Hp(10) across selected workers in the latest reported month.",
        )
    with c2:
        kpi_card(
            "3-month rolling mean",
            f"{sub['roll_3m'].tail(1).mean():.2f} mSv/mo",
        )
    with c3:
        kpi_card(
            "6-month rolling mean",
            f"{sub['roll_6m'].tail(1).mean():.2f} mSv/mo",
        )
    with c4:
        kpi_card(
            "12-month rolling mean",
            f"{sub['roll_12m'].tail(1).mean():.2f} mSv/mo",
        )
    with c5:
        worst = trailing.iloc[0]
        kpi_card(
            "Highest trailing 12-mo",
            f"{worst:.1f} mSv",
            f"{top_name}",
            help="Sum of the last 12 months for the most exposed selected worker, "
            "against the ICRP 20 mSv/y average limit.",
        )

    if not np.isnan(prev_12) and prev_12 > 0:
        st.caption(
            f"Cohort trailing 12-month dose changed "
            f"{(trailing.mean() / prev_12 - 1) * 100:+.1f}% versus the previous "
            f"12-month block."
        )

    st.subheader(f"Dose trend — {window_label} window")
    st.plotly_chart(monthly_trend_plot(sub, window, aggregate), width="stretch")

    left, right = st.columns(2)
    with left:
        st.subheader("Rolling means (cohort)")
        st.plotly_chart(rolling_windows_plot(sub), width="stretch")
    with right:
        st.subheader("Trailing 12-month cumulative vs limits")
        st.plotly_chart(trailing_cumulative_plot(sub), width="stretch")

    st.subheader("Annual dose by worker")
    st.plotly_chart(worker_comparison_plot(sub), width="stretch")

    with st.expander("Recent data"):
        show = sub[["month", "worker_id", "name", "role", "hp10_deep_msv"]].copy()
        show["month"] = show["month"].astype(str)
        st.dataframe(show.tail(200), width="stretch")
        st.download_button(
            "Download filtered data (CSV)",
            show.to_csv(index=False).encode(),
            file_name="hp10_filtered.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
