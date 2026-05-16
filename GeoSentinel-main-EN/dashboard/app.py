"""
Dashboard GeoSentinel — inspector interface.

Run with: streamlit run dashboard/app.py
"""

import json
import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from streamlit_folium import st_folium

# Add project root to path so modules can be imported
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import SITES, get_site  # noqa: E402
from agent.brief_offline import generate_brief_offline  # noqa: E402

# LLM import is optional — the project runs 100% offline without it
try:
    from agent.brief import generate_brief as generate_brief_llm  # noqa: E402
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False


DATA_DIR = ROOT / "data"

SEVERITY_COLORS = {
    "info": "#3b82f6",     # blue
    "watch": "#f59e0b",    # amber
    "warning": "#ef4444",  # red
    "alarm": "#7f1d1d",    # dark red
}
SEVERITY_LABELS = {
    "info": "ℹ️ Normal",
    "watch": "👁️ Watch",
    "warning": "⚠️ Warning",
    "alarm": "🚨 ALARM",
}


@st.cache_data
def load_alerts():
    with open(DATA_DIR / "alerts.json", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_site_timeseries(site_id: str):
    insar = pd.read_csv(DATA_DIR / f"{site_id}_insar.csv", parse_dates=["date"])
    seismic = pd.read_csv(
        DATA_DIR / f"{site_id}_seismic.csv", parse_dates=["datetime"]
    )
    hydro = pd.read_csv(DATA_DIR / f"{site_id}_hydro.csv", parse_dates=["date"])
    return insar, seismic, hydro


def build_map(alerts):
    # Romania center
    m = folium.Map(location=[45.9, 25.0], zoom_start=7, tiles="OpenStreetMap")
    for alert in alerts:
        site = get_site(alert["site_id"])
        color = SEVERITY_COLORS[alert["overall_severity"]]
        popup_html = (
            f"<b>{site.name}</b><br>"
            f"Operator: {site.operator}<br>"
            f"Severity: {SEVERITY_LABELS[alert['overall_severity']]}<br>"
            f"ML score: {alert['ml_anomaly_score']:.2f}"
        )
        folium.CircleMarker(
            location=[site.lat, site.lon],
            radius=10 + 5 * ["info", "watch", "warning", "alarm"].index(
                alert["overall_severity"]
            ),
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=site.name,
            color=color,
            fill=True,
            fillColor=color,
            fillOpacity=0.7,
        ).add_to(m)
    return m


def plot_timeseries(site_id: str):
    insar, seismic, hydro = load_site_timeseries(site_id)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        subplot_titles=(
            "InSAR subsidence (cumulative displacement, mm)",
            "Microseismicity (magnitude)",
            "Mine infiltration (l/h)",
        ),
        vertical_spacing=0.08,
    )

    fig.add_trace(
        go.Scatter(
            x=insar["date"], y=insar["displacement_mm"],
            mode="lines+markers", name="Displacement",
            line=dict(color="#0ea5e9", width=2),
        ),
        row=1, col=1,
    )

    if len(seismic):
        fig.add_trace(
            go.Scatter(
                x=seismic["datetime"], y=seismic["magnitude"],
                mode="markers", name="Microseisms",
                marker=dict(
                    color=seismic["magnitude"],
                    colorscale="Reds", size=8,
                    showscale=False,
                ),
            ),
            row=2, col=1,
        )

    fig.add_trace(
        go.Scatter(
            x=hydro["date"], y=hydro["infiltration_l_per_hour"],
            mode="lines", name="Infiltration",
            line=dict(color="#10b981", width=2),
            fill="tozeroy", fillcolor="rgba(16,185,129,0.15)",
        ),
        row=3, col=1,
    )

    fig.update_layout(
        height=600, showlegend=False,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


# ─────────────────────────  UI  ─────────────────────────

st.set_page_config(page_title="GeoSentinel", layout="wide", page_icon="⛏️")

st.markdown(
    """
    <style>
      .main-title { font-size: 2.4rem; font-weight: 700; margin-bottom: 0;}
      .subtitle { color: #6b7280; margin-top: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<p class="main-title">⛏️ GeoSentinel</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="subtitle">Early warning system for mine stability — '
    'InSAR + seismicity + hydrology + AI agent fusion</p>',
    unsafe_allow_html=True,
)

try:
    alerts = load_alerts()
except FileNotFoundError:
    st.error(
        "No alerts file exists. Run:\n"
        "```\npython -m ingestion.real_data    # OR ingestion.synthetic_data\n"
        "python -m detection.detect\n```"
    )
    st.stop()

# Check the data source by looking at the columns in the first hydro CSV
first_site = alerts[0]["site_id"]
hydro_df = pd.read_csv(DATA_DIR / f"{first_site}_hydro.csv", nrows=1)
data_source_badge = (
    "🌐 Hybrid data (real Open-Meteo + synthetic InSAR)"
    if "precipitation_mm" in hydro_df.columns
    else "🧪 Synthetic data"
)
st.caption(data_source_badge)

# ─── Top summary
col1, col2, col3, col4 = st.columns(4)
counts = {"info": 0, "watch": 0, "warning": 0, "alarm": 0}
for a in alerts:
    counts[a["overall_severity"]] += 1
col1.metric("Monitored sites", len(alerts))
col2.metric("⚠️ Warnings", counts["warning"])
col3.metric("🚨 Alarms", counts["alarm"])
col4.metric("👁️ Watch", counts["watch"])

st.divider()

# ─── Main layout: map | details
left, right = st.columns([1, 1])

with left:
    st.subheader("Site status map")
    map_obj = build_map(alerts)
    map_data = st_folium(map_obj, width=None, height=500, key="map")

    # Site selection from map click or select box
    site_names = {a["site_id"]: a["site_name"] for a in alerts}
    selected_id = st.selectbox(
        "Or choose a site from the list:",
        options=list(site_names.keys()),
        format_func=lambda x: site_names[x],
    )

with right:
    alert = next(a for a in alerts if a["site_id"] == selected_id)
    site = get_site(selected_id)

    st.subheader(f"📍 {site.name}")
    st.caption(
        f"Operator: **{site.operator}** | Type: **{site.mine_type}** | "
        f"Status: **{site.status}** | Depth/cover: **{site.depth_m}m**"
    )

    sev = alert["overall_severity"]
    st.markdown(
        f"<div style='padding: 1rem; border-radius: 8px; "
        f"background: {SEVERITY_COLORS[sev]}22; "
        f"border-left: 6px solid {SEVERITY_COLORS[sev]};'>"
        f"<b style='font-size: 1.2rem;'>{SEVERITY_LABELS[sev]}</b><br>"
        f"ML anomaly score: {alert['ml_anomaly_score']:.2f}"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("**Signals:**")
    for s in alert["signals"]:
        emoji = {"info": "✅", "watch": "🟡", "warning": "🟠", "alarm": "🔴"}[
            s["severity"]
        ]
        st.markdown(
            f"{emoji} **{s['name']}**: `{s['value']} {s['unit']}` — {s['threshold_hit']}"
        )

st.divider()

# ─── Time series
st.subheader("📈 Fused time series")
st.plotly_chart(plot_timeseries(selected_id), use_container_width=True)

st.divider()

# ─── Agent / brief generator
st.subheader("🤖 GeoSentinel operational briefing")

cached_path = DATA_DIR / f"brief_{selected_id}.md"
col_a, col_b = st.columns([3, 1])

with col_b:
    use_llm = False
    if LLM_AVAILABLE:
        use_llm = st.toggle(
            "Use Claude LLM",
            value=False,
            help="Requires a valid ANTHROPIC_API_KEY in .env. Off = offline-generated brief."
        )
    regenerate = st.button("🔄 Generate brief", type="primary")

if regenerate or not cached_path.exists():
    with st.spinner("Generating the briefing..."):
        try:
            if use_llm:
                brief_text = generate_brief_llm(selected_id)
            else:
                brief_text = generate_brief_offline(selected_id)
            cached_path.write_text(brief_text, encoding="utf-8")
        except Exception as e:
            st.error(
                f"Eroare la generarea brief-ului LLM: {e}\n\n"
                "Using the offline variant as fallback."
            )
            brief_text = generate_brief_offline(selected_id)
            cached_path.write_text(brief_text, encoding="utf-8")
else:
    brief_text = cached_path.read_text(encoding="utf-8")

if brief_text:
    with col_a:
        st.markdown(brief_text)

st.divider()
st.caption(
    "⚠️ GeoSentinel is a decision-support system. All alerts must be "
    "validated by authorized ITM/ANRM inspectors before operational action."
)
