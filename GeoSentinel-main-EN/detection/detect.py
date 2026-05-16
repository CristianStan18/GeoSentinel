"""
Anomaly detection engine.

Combines:
1. Deterministic physical thresholds (interpretable and legally defensible)
2. Isolation Forest on the multivariate vector (captures unexpected combinations)
3. Change-point detection on the subsidence rate

Run with: python -m detection.detect
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from config import SITES, MineSite, get_site, is_tunnel
from detection.thresholds import (
    INSAR_VELOCITY_THRESHOLDS,
    SEISMIC_RATE_THRESHOLDS,
    INFILTRATION_PCT_THRESHOLDS,
    TUNNEL_CONVERGENCE_THRESHOLDS,
    TUNNEL_PGV_THRESHOLDS,
    TUNNEL_HUMIDITY_THRESHOLDS,
    TUNNEL_NEW_CRACKS_THRESHOLDS,
    TUNNEL_INFLOW_PCT_THRESHOLDS,
    AIR_CO_THRESHOLDS,
    AIR_NO2_THRESHOLDS,
    AIR_PM10_THRESHOLDS,
    AIR_CH4_THRESHOLDS,
    classify,
    max_severity,
    Severity,
)


DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class Signal:
    """An individual signal contributing to an alert."""
    name: str
    value: float
    unit: str
    severity: Severity
    threshold_hit: str  # e.g. "warning >= 10 mm/month"
    description: str


@dataclass
class Alert:
    site_id: str
    site_name: str
    as_of: str  # ISO date
    overall_severity: Severity
    signals: list[Signal]
    ml_anomaly_score: float  # 0-1, higher = more abnormal
    summary_metrics: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signals"] = [asdict(s) for s in self.signals]
        return d


def _load_site_data(site_id: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    insar = pd.read_csv(DATA_DIR / f"{site_id}_insar.csv", parse_dates=["date"])

    # Seismic can legitimately be empty in inactive zones, so handle it defensively
    seismic_path = DATA_DIR / f"{site_id}_seismic.csv"
    try:
        seismic = pd.read_csv(seismic_path, parse_dates=["datetime"])
    except (pd.errors.EmptyDataError, ValueError):
        seismic = pd.DataFrame(columns=[
            "datetime", "magnitude", "depth_km", "site_id"
        ])
        seismic["datetime"] = pd.to_datetime(seismic["datetime"])

    # Defensive handling: if the CSV contains timezone-aware timestamps (for example from EMSC),
    # normalize them to naive UTC so pipeline comparisons do not fail
    if not seismic.empty and seismic["datetime"].dt.tz is not None:
        seismic["datetime"] = seismic["datetime"].dt.tz_convert("UTC").dt.tz_localize(None)

    hydro = pd.read_csv(DATA_DIR / f"{site_id}_hydro.csv", parse_dates=["date"])
    return insar, seismic, hydro


def _check_insar(site: MineSite, insar: pd.DataFrame) -> Signal:
    """Rolling velocity over the last 30 days."""
    recent = insar.tail(3)  # ~36 days at a 12-day cadence
    velocity = recent["velocity_mm_per_month"].mean()
    # Convert to magnitude because subsidence is negative
    magnitude = abs(velocity)
    thresholds = INSAR_VELOCITY_THRESHOLDS[site.mine_type]
    sev = classify(magnitude, thresholds)
    return Signal(
        name="InSAR subsidence",
        value=round(velocity, 2),
        unit="mm/month",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {thresholds.get(sev, 0)} mm/month"
            if sev != "info" else "below watch threshold"
        ),
        description=(
            f"Average vertical deformation rate over the last {len(recent)*12} "
            f"days, measured from Sentinel-1 InSAR with LOS projected vertically."
        ),
    )


def _check_seismic(site: MineSite, seismic: pd.DataFrame, ref_date: datetime) -> Signal:
    """Microseismic event rate over the last 7 days."""
    thresholds = SEISMIC_RATE_THRESHOLDS[site.mine_type]
    if seismic.empty:
        return Signal(
            name="Microseismicity",
            value=0.0,
            unit="events/day (7d avg)",
            severity="info",
            threshold_hit="0 real catalogued events in 7 days",
            description=(
                "No natural M≥1.5 earthquake catalogued by EMSC/USGS within "
                "a 50 km radius. Seismically inactive area; induced microseismicity "
                "below M<1.5 requires a local seismic network."
            ),
        )
    window_start = ref_date - pd.Timedelta(days=7)
    recent = seismic[seismic["datetime"] >= window_start]
    rate = len(recent) / 7.0
    sev = classify(rate, thresholds)
    max_mag = recent["magnitude"].max() if len(recent) else 0.0
    return Signal(
        name="Microseismicity",
        value=round(rate, 2),
        unit="events/day (7d avg)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {thresholds.get(sev, 0)} events/day"
            if sev != "info" else "below watch threshold"
        ),
        description=(
            f"{len(recent)} microseismic events in 7 days, maximum magnitude "
            f"M={max_mag:.2f}."
        ),
    )


def _check_infiltration(hydro: pd.DataFrame) -> Signal:
    """Percentage increase in infiltration versus the 90-day baseline."""
    if len(hydro) < 90:
        baseline = hydro["infiltration_l_per_hour"].head(30).mean()
    else:
        baseline = hydro["infiltration_l_per_hour"].iloc[:-30].tail(60).mean()
    recent = hydro["infiltration_l_per_hour"].tail(7).mean()
    pct_change = ((recent - baseline) / baseline) * 100
    sev = classify(pct_change, INFILTRATION_PCT_THRESHOLDS)
    return Signal(
        name="Water infiltration",
        value=round(pct_change, 1),
        unit="% increase vs 90d baseline",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {INFILTRATION_PCT_THRESHOLDS.get(sev, 0)}%"
            if sev != "info" else "below watch threshold"
        ),
        description=(
            f"Recent flow {recent:.0f} l/h vs baseline {baseline:.0f} l/h."
        ),
    )


# ─── TUNNEL-SPECIFIC SIGNALS ───

def _load_tunnel_signals(site_id: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load convergence, PGV and humidity for a tunnel."""
    convergence = pd.read_csv(
        DATA_DIR / f"{site_id}_convergence.csv", parse_dates=["date"]
    )
    pgv = pd.read_csv(DATA_DIR / f"{site_id}_pgv.csv", parse_dates=["date"])
    humidity = pd.read_csv(
        DATA_DIR / f"{site_id}_humidity.csv", parse_dates=["date"]
    )
    return convergence, pgv, humidity


def _check_convergence(convergence: pd.DataFrame) -> Signal:
    """Average convergence rate over the last 7 days (mm/day, magnitude)."""
    recent = convergence["convergence_mm_per_day"].tail(7).mean()
    magnitude = abs(recent)
    sev = classify(magnitude, TUNNEL_CONVERGENCE_THRESHOLDS)
    return Signal(
        name="Lining convergence",
        value=round(recent, 3),
        unit="mm/day (7d avg)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_CONVERGENCE_THRESHOLDS.get(sev, 0)} mm/day"
            if sev != "info" else "below watch threshold"
        ),
        description=(
            f"Cumulative convergence: "
            f"{convergence['convergence_cumulative_mm'].iloc[-1]:.2f} mm. "
            "Measured with wireless convergometers in the critical section."
        ),
    )


def _check_pgv(pgv: pd.DataFrame) -> Signal:
    """Peak PGV over the last 7 days (mm/s)."""
    recent_peak = pgv["pgv_mm_per_s"].tail(7).max()
    sev = classify(recent_peak, TUNNEL_PGV_THRESHOLDS)
    return Signal(
        name="Dynamic vibrations (PGV)",
        value=round(recent_peak, 2),
        unit="mm/s (7d peak)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_PGV_THRESHOLDS.get(sev, 0)} mm/s"
            if sev != "info" else "below DIN 4150 threshold"
        ),
        description=(
            f"Vibrations from excavation/traffic. DIN 4150 standard for "
            f"sensitive structures: 5 mm/s threshold, 20 mm/s critical."
        ),
    )


def _check_humidity(humidity_cracks: pd.DataFrame) -> Signal:
    """Wall humidity (%) — absolute value."""
    recent = humidity_cracks["humidity_pct"].tail(7).mean()
    sev = classify(recent, TUNNEL_HUMIDITY_THRESHOLDS)
    return Signal(
        name="Wall humidity",
        value=round(recent, 1),
        unit="% (7d avg)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_HUMIDITY_THRESHOLDS.get(sev, 0)}%"
            if sev != "info" else "below watch threshold"
        ),
        description=(
            "Average lining humidity. High values indicate active infiltration "
            "through the lining or insufficient ventilation."
        ),
    )


def _check_new_cracks(humidity_cracks: pd.DataFrame) -> Signal:
    """New LiDAR cracks over the last 30 days (cumulative delta)."""
    if len(humidity_cracks) < 30:
        new_cracks = humidity_cracks["cracks_cumulative"].iloc[-1]
    else:
        end_count = humidity_cracks["cracks_cumulative"].iloc[-1]
        start_count = humidity_cracks["cracks_cumulative"].iloc[-30]
        new_cracks = int(end_count - start_count)
    sev = classify(new_cracks, TUNNEL_NEW_CRACKS_THRESHOLDS)
    return Signal(
        name="New LiDAR cracks",
        value=new_cracks,
        unit="cracks (last 30d)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_NEW_CRACKS_THRESHOLDS.get(sev, 0)} cracks"
            if sev != "info" else "below watch threshold"
        ),
        description=(
            f"Total cumulat: {humidity_cracks['cracks_cumulative'].iloc[-1]} "
            "cracks. Detected through periodic mobile LiDAR scanning."
        ),
    )

def _check_tunnel_inflow(inflow: pd.DataFrame) -> Signal:
    """Increase in tunnel water inflow compared with the 60-day baseline."""
    col = "water_inflow_l_per_min"
    if len(inflow) < 60:
        baseline = inflow[col].head(20).mean()
    else:
        baseline = inflow[col].iloc[:-20].tail(40).mean()
    recent = inflow[col].tail(7).mean()
    pct_change = ((recent - baseline) / baseline) * 100 if baseline > 0 else 0
    sev = classify(pct_change, TUNNEL_INFLOW_PCT_THRESHOLDS)
    return Signal(
        name="Tunnel water inflow",
        value=round(pct_change, 1),
        unit="% increase vs 60d baseline",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_INFLOW_PCT_THRESHOLDS.get(sev, 0)}%"
            if sev != "info" else "below watch threshold"
        ),
        description=(
            f"Debit recent {recent:.1f} l/min vs baseline {baseline:.1f} l/min. "
            "Infiltration through lining/cracks, correlated with precipitation."
        ),
    )


def _check_air_co(air: pd.DataFrame) -> Signal:
    """Average carbon monoxide over the last 7 days (mg/m³)."""
    recent = air["co_mg_m3"].tail(7).mean()
    sev = classify(recent, AIR_CO_THRESHOLDS)
    return Signal(
        name="CO (carbon monoxide)",
        value=round(recent, 2),
        unit="mg/m³ (7d avg)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {AIR_CO_THRESHOLDS.get(sev, 0)} mg/m³"
            if sev != "info" else "below occupational limit"
        ),
        description=(
            "Carbon monoxide in the underground atmosphere. Sources: diesel equipment "
            "and blasting. OSHA occupational limit: ~35 mg/m³ (8h)."
        ),
    )


def _check_air_ch4(site: MineSite, air: pd.DataFrame) -> Signal:
    """Methane — CRITICAL for coal mines (% volume)."""
    recent = air["ch4_pct_vol"].tail(7).mean()
    peak = air["ch4_pct_vol"].tail(7).max()
    sev = classify(peak, AIR_CH4_THRESHOLDS)
    return Signal(
        name="CH4 (methane)",
        value=round(peak, 3),
        unit="% volume (7d peak)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {AIR_CH4_THRESHOLDS.get(sev, 0)}% vol"
            if sev != "info" else "below watch threshold"
        ),
        description=(
            f"Methane concentration (average {recent:.3f}%). Mining standard: "
            "1.5% = work stoppage, 5% = lower explosive limit (LEL). "
            + ("Dominant risk for coal mines."
               if site.mine_type == "carbune"
               else "Normal trace level for this site type.")
        ),
    )


def _check_air_particulates(air: pd.DataFrame) -> Signal:
    """Average PM10 dust over 7 days (mg/m³)."""
    recent = air["pm10_mg_m3"].tail(7).mean()
    sev = classify(recent, AIR_PM10_THRESHOLDS)
    return Signal(
        name="PM10 dust",
        value=round(recent, 2),
        unit="mg/m³ (7d avg)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {AIR_PM10_THRESHOLDS.get(sev, 0)} mg/m³"
            if sev != "info" else "below mining dust limit"
        ),
        description=(
            "Suspended dust from drilling/excavation. Respirable mining dust "
            "limit: ~4-5 mg/m³."
        ),
    )


def _ml_anomaly_score(
    insar: pd.DataFrame, seismic: pd.DataFrame, hydro: pd.DataFrame
) -> float:
    """
    Isolation Forest on 14-day rolling windows.
    Returns the current-window score (0=normal, 1=abnormal).
    """
    # Build a unified daily panel
    hydro_indexed = hydro.set_index("date")
    if not seismic.empty:
        seismic_daily = (
            seismic.assign(date=seismic["datetime"].dt.normalize())
            .groupby("date")
            .agg(seismic_count=("magnitude", "count"),
                 seismic_max_mag=("magnitude", "max"))
        )
    else:
        seismic_daily = pd.DataFrame(columns=["seismic_count", "seismic_max_mag"])
    insar_resampled = (
        insar.set_index("date")[["displacement_mm", "velocity_mm_per_month"]]
        .resample("D").ffill()
    )

    panel = hydro_indexed.join(seismic_daily, how="left").join(
        insar_resampled, how="left"
    )
    panel["seismic_count"] = panel["seismic_count"].fillna(0)
    panel["seismic_max_mag"] = panel["seismic_max_mag"].fillna(0)
    panel = panel.ffill().dropna()

    # Features: 14-day rolling averages
    features = panel[[
        "precipitation_mm", "infiltration_l_per_hour",
        "water_table_m", "seismic_count", "seismic_max_mag",
        "velocity_mm_per_month",
    ]].rolling(14).mean().dropna()

    if len(features) < 30:
        return 0.0

    # Train on the first 70% (assumed normal) and score the final point
    split = int(len(features) * 0.7)
    train = features.iloc[:split]
    test_point = features.iloc[[-1]]

    iso = IsolationForest(contamination=0.05, random_state=0)
    iso.fit(train)
    # decision_function: positive = normal, negative = abnormal
    raw = iso.decision_function(test_point)[0]
    # Normalize to [0, 1], where 1 = highly abnormal
    score = float(np.clip(0.5 - raw, 0, 1))
    return round(score, 3)


def detect_for_site(site: MineSite, ref_date: datetime | None = None) -> Alert:
    insar, seismic, hydro = _load_site_data(site.id)
    ref_date = ref_date or insar["date"].max().to_pydatetime()

    # Common signals (surface subsidence + seismic + weather)
    signals = [
        _check_insar(site, insar),
        _check_seismic(site, seismic, ref_date),
    ]

    # Tunnels: specific signals (convergence, PGV, humidity, cracks, inflow)
    # Mines: classic infiltration signal
    if is_tunnel(site):
        try:
            convergence, pgv, humidity_cracks = _load_tunnel_signals(site.id)
            signals.append(_check_convergence(convergence))
            signals.append(_check_pgv(pgv))
            signals.append(_check_humidity(humidity_cracks))
            signals.append(_check_new_cracks(humidity_cracks))
        except FileNotFoundError:
            pass
        # Tunnel water inflow
        try:
            inflow = pd.read_csv(
                DATA_DIR / f"{site.id}_inflow.csv", parse_dates=["date"]
            )
            signals.append(_check_tunnel_inflow(inflow))
        except FileNotFoundError:
            pass
    else:
        signals.append(_check_infiltration(hydro))

    # Air quality — shared by mines and tunnels
    try:
        air = pd.read_csv(DATA_DIR / f"{site.id}_air.csv", parse_dates=["date"])
        signals.append(_check_air_co(air))
        signals.append(_check_air_particulates(air))
        # Methane: relevant as an explicit signal only for coal mines
        if site.mine_type == "carbune":
            signals.append(_check_air_ch4(site, air))
    except FileNotFoundError:
        pass

    ml_score = _ml_anomaly_score(insar, seismic, hydro)

    # Overall severity: maximum signal severity + bump if ML > 0.6
    overall = max_severity([s.severity for s in signals])
    if ml_score > 0.6 and overall == "info":
        overall = "watch"
    elif ml_score > 0.8 and overall == "watch":
        overall = "warning"

    summary_metrics = {
        "insar_total_displacement_mm": round(
            insar["displacement_mm"].iloc[-1], 1
        ),
        "seismic_events_last_30d": int(
            (seismic["datetime"] >= ref_date - pd.Timedelta(days=30)).sum()
        ),
    }
    if is_tunnel(site):
        try:
            convergence, _, humidity_cracks = _load_tunnel_signals(site.id)
            summary_metrics["convergence_cumulative_mm"] = round(
                convergence["convergence_cumulative_mm"].iloc[-1], 2
            )
            summary_metrics["total_cracks_lidar"] = int(
                humidity_cracks["cracks_cumulative"].iloc[-1]
            )
            summary_metrics["tunnel_length_m"] = site.length_m
            summary_metrics["excavation_progress_pct"] = site.excavation_progress_pct
        except FileNotFoundError:
            pass
    else:
        summary_metrics["infiltration_current_lph"] = round(
            hydro["infiltration_l_per_hour"].iloc[-1], 0
        )

    # Air metrics (shared)
    try:
        air = pd.read_csv(DATA_DIR / f"{site.id}_air.csv", parse_dates=["date"])
        summary_metrics["air_co_current_mg_m3"] = round(
            air["co_mg_m3"].iloc[-1], 2
        )
        if site.mine_type == "carbune":
            summary_metrics["air_ch4_current_pct"] = round(
                air["ch4_pct_vol"].iloc[-1], 3
            )
    except FileNotFoundError:
        pass

    return Alert(
        site_id=site.id,
        site_name=site.name,
        as_of=ref_date.isoformat(),
        overall_severity=overall,
        signals=signals,
        ml_anomaly_score=ml_score,
        summary_metrics=summary_metrics,
    )


def run_all() -> list[Alert]:
    alerts = []
    for site in SITES:
        alert = detect_for_site(site)
        alerts.append(alert)
        marker = {
            "info": "·", "watch": "▲",
            "warning": "▲▲", "alarm": "⚠ ALARM"
        }[alert.overall_severity]
        print(f"{marker:>9}  {site.name:<25}  ML={alert.ml_anomaly_score:.2f}")

    # Save
    out = DATA_DIR / "alerts.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump([a.to_dict() for a in alerts], f, ensure_ascii=False, indent=2)
    print(f"\n✓ Alerts saved to {out}")
    return alerts


if __name__ == "__main__":
    run_all()
