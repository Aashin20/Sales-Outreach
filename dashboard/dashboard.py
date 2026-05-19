import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Outreach Intelligence — Operator Dashboard",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global styles ─────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  html, body, [class*="css"] {
    font-family: 'Syne', sans-serif !important;
  }

  /* Page background */
  .stApp {
    background-color: #0c0e14;
    color: #e8eaf0;
  }

  /* Remove default Streamlit padding at top */
  .block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 1280px;
  }

  /* Hide Streamlit decorations */
  #MainMenu, footer, header { visibility: hidden; }
  .stDeployButton { display: none; }

  /* Divider */
  hr {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.06) !important;
    margin: 1.5rem 0 !important;
  }

  /* Metric cards */
  [data-testid="metric-container"] {
    background: #13151f;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    padding: 1rem 1.25rem !important;
  }

  [data-testid="stMetricLabel"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #555b72 !important;
  }

  [data-testid="stMetricValue"] {
    font-size: 28px !important;
    font-weight: 700 !important;
    color: #e8eaf0 !important;
    letter-spacing: -0.5px;
  }

  [data-testid="stMetricDelta"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    color: #4ded8a !important;
  }

  /* Section headings */
  h3 {
    font-size: 11px !important;
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: #555b72 !important;
    font-weight: 400 !important;
    margin-bottom: 0.25rem !important;
  }

  /* Dataframe / table */
  [data-testid="stDataFrame"] {
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 10px !important;
    overflow: hidden;
  }

  .dvn-scroller { background: #13151f !important; }

  /* Sidebar */
  [data-testid="stSidebar"] {
    background: #13151f !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
  }

  /* Checkbox */
  .stCheckbox label { color: #8b92aa !important; font-family: 'JetBrains Mono', monospace !important; font-size: 12px !important; }

  /* Info box */
  .stAlert {
    background: #13151f !important;
    border: 1px solid rgba(91,110,245,0.3) !important;
    border-radius: 10px !important;
    color: #8b92aa !important;
  }
</style>
""", unsafe_allow_html=True)

# ── Plotly theme ───────────────────────────────────────────────────

PLOTLY_THEME = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#13151f",
    font=dict(family="JetBrains Mono, monospace", color="#8b92aa", size=11),
    margin=dict(l=12, r=12, t=12, b=12),
    xaxis=dict(
        gridcolor="rgba(255,255,255,0.04)",
        linecolor="rgba(255,255,255,0.06)",
        tickcolor="rgba(0,0,0,0)",
        zeroline=False,
    ),
    yaxis=dict(
        gridcolor="rgba(255,255,255,0.04)",
        linecolor="rgba(255,255,255,0.06)",
        tickcolor="rgba(0,0,0,0)",
        zeroline=False,
    ),
    colorway=["#5b6ef5", "#9b67f5", "#4ded8a", "#f5c842", "#f5826b"],
)

STAGE_COLORS = {
    "enrich":   "#5b6ef5",
    "research": "#9b67f5",
    "score":    "#4ded8a",
    "draft":    "#f5c842",
    "validate": "#f5826b",
}

ACCENT = "#5b6ef5"

# ── Data loader ────────────────────────────────────────────────────

TRACE_FILE = os.environ.get("TRACE_FILE_PATH", "/app/traces/traces.jsonl")


@st.cache_data(ttl=10)
def load_traces() -> pd.DataFrame:
    path = Path(TRACE_FILE)
    if not path.exists():
        return pd.DataFrame()
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# ── Header ─────────────────────────────────────────────────────────

col_logo, col_status = st.columns([8, 2])
with col_logo:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
      <div style="width:36px;height:36px;background:linear-gradient(135deg,#5b6ef5,#9b67f5);border-radius:9px;
                  display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;color:#fff;
                  letter-spacing:-1px;">OI</div>
      <div>
        <div style="font-size:15px;font-weight:600;color:#c8ccdf;">Outreach Intelligence</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#555b72;margin-top:1px;">operator dashboard</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

with col_status:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:6px;justify-content:flex-end;margin-top:8px;">
      <div style="width:7px;height:7px;background:#4ded8a;border-radius:50%;animation:none;"></div>
      <span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#4ded8a;">live monitoring</span>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ── Load data ──────────────────────────────────────────────────────

df = load_traces()

if df.empty:
    st.info("No trace data yet. Submit some jobs to see metrics here.")
    st.stop()

# ── Key metrics ────────────────────────────────────────────────────

today = datetime.utcnow().date()
today_df = df[df["timestamp"].dt.date == today] if "timestamp" in df.columns else df

total_jobs   = df["job_id"].nunique()
today_jobs   = today_df["job_id"].nunique()
total_cost   = df["cost_usd"].sum() if "cost_usd" in df.columns else 0.0
today_cost   = today_df["cost_usd"].sum() if "cost_usd" in today_df.columns else 0.0
success_rate = df["success"].mean() * 100 if "success" in df.columns else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Jobs",    f"{total_jobs:,}",           delta=f"↑ {today_jobs} today")
c2.metric("Jobs Today",    f"{today_jobs:,}",           delta="since 00:00 UTC")
c3.metric("Cost Today",    f"${today_cost:.4f}",        delta=f"${total_cost:.4f} total")
c4.metric("Success Rate",  f"{success_rate:.1f}%",      delta=f"{success_rate - 93:.1f}pp vs baseline")

st.divider()

# ── Charts row 1 ───────────────────────────────────────────────────

chart_l, chart_r = st.columns(2)

# Success rate by stage
with chart_l:
    st.markdown("### Pipeline health")
    st.markdown("<p style='font-size:13px;font-weight:600;color:#c8ccdf;margin-bottom:12px;'>Success rate by stage</p>", unsafe_allow_html=True)

    if "stage" in df.columns and "success" in df.columns:
        stage_stats = (
            df.groupby("stage")
            .agg(total=("success", "count"), successes=("success", "sum"))
            .reset_index()
        )
        stage_stats["success_rate"] = (
            stage_stats["successes"] / stage_stats["total"] * 100
        ).round(1)
        stage_stats["color"] = stage_stats["stage"].map(
            lambda s: STAGE_COLORS.get(s, ACCENT)
        )

        fig1 = go.Figure(go.Bar(
            x=stage_stats["success_rate"],
            y=stage_stats["stage"],
            orientation="h",
            marker_color=stage_stats["color"].tolist(),
            text=stage_stats["success_rate"].map(lambda v: f"{v:.1f}%"),
            textposition="outside",
            textfont=dict(family="JetBrains Mono, monospace", size=10, color="#8b92aa"),
        ))
        theme1 = {**PLOTLY_THEME, "xaxis": {**PLOTLY_THEME["xaxis"], "range": [0, 108], "ticksuffix": "%"}}
        fig1.update_layout(**theme1, height=260)
        st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})

# Latency by stage
with chart_r:
    st.markdown("### Performance")
    st.markdown("<p style='font-size:13px;font-weight:600;color:#c8ccdf;margin-bottom:12px;'>Latency p50 / p95 / p99</p>", unsafe_allow_html=True)

    if "stage" in df.columns and "latency_ms" in df.columns:
        lat_df = df.dropna(subset=["latency_ms"])
        if not lat_df.empty:
            lat = (
                lat_df.groupby("stage")["latency_ms"]
                .quantile([0.5, 0.95, 0.99])
                .unstack()
                .reset_index()
            )
            lat.columns = ["stage", "p50", "p95", "p99"]

            fig2 = go.Figure()
            for pct, color in [("p50", "#4ded8a"), ("p95", "#f5c842"), ("p99", "#f5826b")]:
                fig2.add_trace(go.Bar(
                    name=pct,
                    x=lat["stage"],
                    y=lat[pct],
                    marker_color=color,
                    marker_line_width=0,
                ))
            theme2 = {**PLOTLY_THEME, "yaxis": {**PLOTLY_THEME["yaxis"], "ticksuffix": " ms"}}
            fig2.update_layout(
                **theme2,
                barmode="group",
                height=260,
                legend=dict(
                    orientation="h",
                    yanchor="bottom", y=1.02,
                    xanchor="right", x=1,
                    font=dict(family="JetBrains Mono, monospace", size=10, color="#555b72"),
                    bgcolor="rgba(0,0,0,0)",
                ),
            )
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

st.divider()

# ── Cost over time ─────────────────────────────────────────────────

st.markdown("### Cost tracking")
st.markdown("<p style='font-size:13px;font-weight:600;color:#c8ccdf;margin-bottom:12px;'>Cost per job over time</p>", unsafe_allow_html=True)

if "cost_usd" in df.columns and "timestamp" in df.columns:
    cost_df = df.dropna(subset=["cost_usd"])
    if not cost_df.empty:
        cost_by_job = (
            cost_df.groupby("job_id")
            .agg(total_cost=("cost_usd", "sum"), timestamp=("timestamp", "min"))
            .reset_index()
            .sort_values("timestamp")
        )

        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=cost_by_job["timestamp"],
            y=cost_by_job["total_cost"],
            mode="lines",
            name="cost",
            line=dict(color=ACCENT, width=1.5),
            fill="tozeroy",
            fillcolor="rgba(91,110,245,0.07)",
        ))
        # Rolling average
        cost_by_job["rolling"] = cost_by_job["total_cost"].rolling(5, min_periods=1).mean()
        fig3.add_trace(go.Scatter(
            x=cost_by_job["timestamp"],
            y=cost_by_job["rolling"],
            mode="lines",
            name="rolling avg",
            line=dict(color="rgba(91,110,245,0.4)", width=1, dash="dot"),
        ))
        theme3 = {**PLOTLY_THEME, "yaxis": {**PLOTLY_THEME["yaxis"], "tickprefix": "$"}}
        fig3.update_layout(
            **theme3,
            height=200,
            legend=dict(
                orientation="h",
                yanchor="bottom", y=1.02,
                xanchor="right", x=1,
                font=dict(family="JetBrains Mono, monospace", size=10, color="#555b72"),
                bgcolor="rgba(0,0,0,0)",
            ),
        )
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})

st.divider()

# ── Trace table ────────────────────────────────────────────────────

st.markdown("### Trace log")
st.markdown("<p style='font-size:13px;font-weight:600;color:#c8ccdf;margin-bottom:12px;'>Recent pipeline entries</p>", unsafe_allow_html=True)

display_cols = [c for c in ["timestamp", "job_id", "stage", "success", "latency_ms",
                              "cost_usd", "cache_hit", "retries", "model", "error"]
                if c in df.columns]

recent = (
    df.sort_values("timestamp", ascending=False).head(50)[display_cols]
    if "timestamp" in df.columns
    else df.head(50)
)
st.dataframe(recent, use_container_width=True, height=380)

# ── Sidebar + auto-refresh ─────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;text-transform:uppercase;
                letter-spacing:0.08em;color:#555b72;margin-bottom:12px;">Settings</div>
    """, unsafe_allow_html=True)
    auto_refresh = st.checkbox("Auto-refresh (10s)", value=True)
    st.markdown(f"""
    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#3d4252;margin-top:16px;">
      Last updated<br>{datetime.utcnow().strftime('%H:%M:%S')} UTC
    </div>
    """, unsafe_allow_html=True)

if auto_refresh:
    time.sleep(10)
    st.rerun()