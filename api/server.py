"""
Backend Flask GeoSentinel.

Servește HTML-ul UI și expune date pipeline-ului ca JSON pentru fetch().

Rulează cu:
    python -m api.server

Apoi deschide: http://localhost:5000
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, send_file, abort

# Adăugăm rădăcina la path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import SITES, get_site, is_tunnel  # noqa: E402


DATA_DIR = ROOT / "data"
STATIC_HTML = ROOT / "frontend" / "index.html"

app = Flask(__name__, static_folder=None)


# ─────────────────────────── Helpers ───────────────────────────

# Maparea severității din Python la culorile UI-ului HTML
SEVERITY_TO_UI = {
    "alarm": {
        "risk": "high",
        "label_mine": "ALARMA",
        "label_tunnel": "ALERTĂ",
        "color_mine": "#ff4444",
        "color_tunnel": "#ff7d3b",
    },
    "warning": {
        "risk": "high",
        "label_mine": "WARNING",
        "label_tunnel": "WARNING",
        "color_mine": "#ff4444",
        "color_tunnel": "#ff7d3b",
    },
    "watch": {
        "risk": "medium",
        "label_mine": "WATCH",
        "label_tunnel": "WATCH",
        "color_mine": "#f5c842",
        "color_tunnel": "#f5c842",
    },
    "info": {
        "risk": "low",
        "label_mine": "NOMINAL",
        "label_tunnel": "NOMINAL",
        "color_mine": "#00d4a0",
        "color_tunnel": "#00d4a0",
    },
}

# Mapăm severitățile semnalelor individuale la cele din UI
SIGNAL_SEV_TO_UI = {
    "alarm": {"color": "#ff4444", "alert": "alarm"},
    "warning": {"color": "#ff7d3b", "alert": "alarm"},
    "watch": {"color": "#f5c842", "alert": "watch"},
    "info": {"color": "#00d4a0", "alert": "ok"},
}


def _load_alerts() -> list[dict]:
    alerts_path = DATA_DIR / "alerts.json"
    if not alerts_path.exists():
        return []
    with open(alerts_path, encoding="utf-8") as f:
        return json.load(f)


def _alert_for(site_id: str) -> dict | None:
    for a in _load_alerts():
        if a["site_id"] == site_id:
            return a
    return None


def _sources_for(site, is_t: bool) -> list[str]:
    """Lista surselor de date pentru acest site (afișată în UI)."""
    if is_t:
        return [
            "Convergometre wireless",
            "LiDAR periodic",
            "EGMS Sentinel-1 (hook)",
            "EMSC catalog seismic",
            "Open-Meteo ERA5",
        ]
    sources = ["EGMS Sentinel-1 (hook)", "EMSC catalog seismic", "Open-Meteo ERA5"]
    if site.mine_type == "carbune":
        sources.append("Senzori CH4 (planificat)")
    if site.mine_type in ("sare", "sare_inchisa"):
        sources.append("INHGA buletine (planificat)")
    return sources


# ─────────────────────────── API endpoints ───────────────────────────

@app.route("/")
def index():
    """Servește UI-ul HTML."""
    if not STATIC_HTML.exists():
        return (
            "HTML-ul UI nu a fost găsit. "
            f"Așteptat la: {STATIC_HTML}", 500,
        )
    return send_file(STATIC_HTML)


@app.route("/api/sites")
def api_sites():
    """
    Lista tuturor site-urilor cu metadata pentru hartă și detalii.
    Mapează la structura MAP_SITES din HTML.
    """
    alerts = {a["site_id"]: a for a in _load_alerts()}
    result = []

    for site in SITES:
        alert = alerts.get(site.id)
        sev = alert["overall_severity"] if alert else "info"
        is_t = is_tunnel(site)
        ui_sev = SEVERITY_TO_UI[sev]

        signals_ui = []
        if alert:
            for s in alert["signals"]:
                sig_ui = SIGNAL_SEV_TO_UI[s["severity"]]
                signals_ui.append({
                    "label": s["name"],
                    "value": f"{s['value']} {s['unit']}",
                    "threshold": s["threshold_hit"],
                    "color": sig_ui["color"],
                    "alert": sig_ui["alert"],
                })

        # Tunelurile au culori orange (#ff7d3b) pentru alarm, minele roșu
        if is_t:
            risk_color = ui_sev["color_tunnel"]
            risk_label = ui_sev["label_tunnel"]
        else:
            risk_color = ui_sev["color_mine"]
            risk_label = ui_sev["label_mine"]

        alarm_text = None
        if sev in ("alarm", "warning") and alert:
            # Compunem un text cu cel mai sever semnal
            worst = max(
                alert["signals"],
                key=lambda s: {"info": 0, "watch": 1, "warning": 2, "alarm": 3}[s["severity"]]
            )
            alarm_text = (
                f"Scor anomalie ML: {alert['ml_anomaly_score']:.2f} — "
                f"{worst['name']}: {worst['value']} {worst['unit']}"
            )

        item = {
            "id": site.id,
            "name": site.name,
            "lat": site.lat,
            "lng": site.lon,
            "type": "tunnel" if is_t else "mine",
            "risk": ui_sev["risk"] if sev != "info" else "low",
            "riskLabel": risk_label,
            "riskColor": risk_color,
            "operator": site.operator,
            "tip": _humanize_type(site.mine_type),
            "status": site.status.capitalize(),
            "adancime": (
                f"{site.length_m}m lungime"
                if is_t and site.length_m
                else f"{site.depth_m}m"
            ),
            "alarm": sev in ("alarm", "warning"),
            "alarmText": alarm_text,
            "signals": signals_ui,
            "sources": _sources_for(site, is_t),
            "severity": sev,
            "mlScore": alert["ml_anomaly_score"] if alert else 0.0,
        }
        if is_t:
            item["excavationProgress"] = site.excavation_progress_pct
        result.append(item)

    return jsonify(result)


def _humanize_type(t: str) -> str:
    return {
        "sare": "Sare",
        "sare_inchisa": "Sare (închisă)",
        "carbune": "Cărbune",
        "uraniu": "Uraniu",
        "metal_neferos": "Metale neferoase",
        "tunel_autostrada": "Tunel autostradă",
        "tunel_feroviar": "Tunel feroviar",
    }.get(t, t)


@app.route("/api/timeseries/<site_id>")
def api_timeseries(site_id: str):
    """
    Întoarce seriile temporale pentru un site, pregătite pentru Plotly.

    Pentru mine: insar (deplasare cumulată), seismic (magnitudine), hydro (infiltrație).
    Pentru tuneluri: convergence (mm/zi), pgv (mm/s), humidity (%).
    """
    try:
        site = get_site(site_id)
    except KeyError:
        abort(404)

    is_t = is_tunnel(site)

    # InSAR e comun la toate
    insar_df = pd.read_csv(
        DATA_DIR / f"{site_id}_insar.csv", parse_dates=["date"]
    )
    insar_data = {
        "dates": insar_df["date"].dt.strftime("%Y-%m-%d").tolist(),
        "displacement_mm": insar_df["displacement_mm"].round(2).tolist(),
    }

    # Seismic e comun — pd.to_datetime() explicit e robust indiferent de versiunea pandas.
    # parse_dates=["datetime"] poate lăsa coloana ca object/str în pandas >= 2.0
    # dacă formatul conține microsecunde (2025-11-21 20:38:20.775837).
    seismic_df = pd.read_csv(DATA_DIR / f"{site_id}_seismic.csv")
    if not seismic_df.empty and "datetime" in seismic_df.columns:
        seismic_df["datetime"] = pd.to_datetime(
            seismic_df["datetime"], errors="coerce"
        )
        seismic_df = seismic_df.dropna(subset=["datetime"])
        seismic_dates = seismic_df["datetime"].dt.strftime("%Y-%m-%d %H:%M").tolist()
        seismic_mags  = seismic_df["magnitude"].fillna(0).round(2).tolist()
    else:
        seismic_dates, seismic_mags = [], []

    seismic_data = {
        "dates": seismic_dates,
        "magnitudes": seismic_mags,
    }

    response = {
        "site_id": site_id,
        "site_name": site.name,
        "is_tunnel": is_t,
        "insar": insar_data,
        "seismic": seismic_data,
    }

    if is_t:
        # Pentru tuneluri: convergence + pgv + humidity
        try:
            conv_df = pd.read_csv(
                DATA_DIR / f"{site_id}_convergence.csv", parse_dates=["date"]
            )
            response["convergence"] = {
                "dates": conv_df["date"].dt.strftime("%Y-%m-%d").tolist(),
                "mm_per_day": conv_df["convergence_mm_per_day"].round(3).tolist(),
                "cumulative_mm": conv_df["convergence_cumulative_mm"].round(2).tolist(),
            }

            pgv_df = pd.read_csv(
                DATA_DIR / f"{site_id}_pgv.csv", parse_dates=["date"]
            )
            response["pgv"] = {
                "dates": pgv_df["date"].dt.strftime("%Y-%m-%d").tolist(),
                "values": pgv_df["pgv_mm_per_s"].round(2).tolist(),
            }

            hum_df = pd.read_csv(
                DATA_DIR / f"{site_id}_humidity.csv", parse_dates=["date"]
            )
            response["humidity"] = {
                "dates": hum_df["date"].dt.strftime("%Y-%m-%d").tolist(),
                "values": hum_df["humidity_pct"].round(1).tolist(),
                "cracks_cumulative": hum_df["cracks_cumulative"].astype(int).tolist(),
            }
        except FileNotFoundError:
            pass

        # Infiltrație apă tunel
        try:
            inflow_df = pd.read_csv(
                DATA_DIR / f"{site_id}_inflow.csv", parse_dates=["date"]
            )
            response["inflow"] = {
                "dates": inflow_df["date"].dt.strftime("%Y-%m-%d").tolist(),
                "values": inflow_df["water_inflow_l_per_min"].round(1).tolist(),
            }
        except FileNotFoundError:
            pass
    else:
        # Pentru mine: infiltrație din hydro
        hydro_df = pd.read_csv(
            DATA_DIR / f"{site_id}_hydro.csv", parse_dates=["date"]
        )
        response["hydro"] = {
            "dates": hydro_df["date"].dt.strftime("%Y-%m-%d").tolist(),
            "infiltration_l_per_hour": hydro_df["infiltration_l_per_hour"].tolist(),
            "precipitation_mm": hydro_df["precipitation_mm"].tolist(),
        }

    # Calitatea aerului — comună la mine și tuneluri
    try:
        air_df = pd.read_csv(
            DATA_DIR / f"{site_id}_air.csv", parse_dates=["date"]
        )
        response["air"] = {
            "dates": air_df["date"].dt.strftime("%Y-%m-%d").tolist(),
            "co_mg_m3": air_df["co_mg_m3"].round(2).tolist(),
            "no2_mg_m3": air_df["no2_mg_m3"].round(2).tolist(),
            "pm10_mg_m3": air_df["pm10_mg_m3"].round(2).tolist(),
            "ch4_pct_vol": air_df["ch4_pct_vol"].round(3).tolist(),
        }
    except FileNotFoundError:
        pass

    return jsonify(response)


@app.route("/api/alerts")
def api_alerts():
    """Toate alertele curente (raw output al detection-ului)."""
    return jsonify(_load_alerts())


@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "sites_count": len(SITES),
        "alerts_count": len(_load_alerts()),
        "data_dir": str(DATA_DIR),
        "timestamp": datetime.now().isoformat(),
    })


if __name__ == "__main__":
    print(f"GeoSentinel backend pornit pe http://localhost:5000")
    print(f"  Endpoint-uri:")
    print(f"    GET /                       (UI HTML)")
    print(f"    GET /api/sites              ({len(SITES)} site-uri)")
    print(f"    GET /api/timeseries/<id>")
    print(f"    GET /api/alerts")
    print(f"    GET /api/health")
    app.run(host="0.0.0.0", port=5000, debug=True)
