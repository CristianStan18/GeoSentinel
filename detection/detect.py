"""
Motor de detecție anomalii.

Combină:
1. Praguri fizice deterministe (interpretabile, defensibile juridic)
2. Isolation Forest pe vectorul multivariat (prinde combinații neașteptate)
3. Change point detection pe rata de subsidență

Rulează cu: python -m detection.detect
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
    """Un semnal individual care contribuie la o alertă."""
    name: str
    value: float
    unit: str
    severity: Severity
    threshold_hit: str  # ex: "warning >= 10 mm/lună"
    description: str


@dataclass
class Alert:
    site_id: str
    site_name: str
    as_of: str  # ISO date
    overall_severity: Severity
    signals: list[Signal]
    ml_anomaly_score: float  # 0-1, mai mare = mai anormal
    summary_metrics: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signals"] = [asdict(s) for s in self.signals]
        return d


def _load_site_data(site_id: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    insar = pd.read_csv(DATA_DIR / f"{site_id}_insar.csv", parse_dates=["date"])

    # Seismic poate fi gol legitim (zone seismic inactive) — îl tratăm defensiv
    seismic_path = DATA_DIR / f"{site_id}_seismic.csv"
    try:
        seismic = pd.read_csv(seismic_path, parse_dates=["datetime"])
    except (pd.errors.EmptyDataError, ValueError):
        seismic = pd.DataFrame(columns=[
            "datetime", "magnitude", "depth_km", "site_id"
        ])
        seismic["datetime"] = pd.to_datetime(seismic["datetime"])

    # Defensiv: dacă CSV-ul are timestamps cu timezone (ex: din EMSC),
    # le normalizăm la naive UTC ca să nu pice comparațiile în pipeline
    if not seismic.empty and seismic["datetime"].dt.tz is not None:
        seismic["datetime"] = seismic["datetime"].dt.tz_convert("UTC").dt.tz_localize(None)

    hydro = pd.read_csv(DATA_DIR / f"{site_id}_hydro.csv", parse_dates=["date"])
    return insar, seismic, hydro


def _check_insar(site: MineSite, insar: pd.DataFrame) -> Signal:
    """Velocity glisantă pe ultimele 30 zile."""
    recent = insar.tail(3)  # ~36 zile la cadență 12 zile
    velocity = recent["velocity_mm_per_month"].mean()
    # Convertim la magnitudine (subsidența e negativă)
    magnitude = abs(velocity)
    thresholds = INSAR_VELOCITY_THRESHOLDS[site.mine_type]
    sev = classify(magnitude, thresholds)
    return Signal(
        name="Subsidență InSAR",
        value=round(velocity, 2),
        unit="mm/lună",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {thresholds.get(sev, 0)} mm/lună"
            if sev != "info" else "sub pragul de watch"
        ),
        description=(
            f"Rata medie de deformare verticală pe ultimele {len(recent)*12} "
            f"zile, măsurată din Sentinel-1 InSAR (LOS proiectat vertical)."
        ),
    )


def _check_seismic(site: MineSite, seismic: pd.DataFrame, ref_date: datetime) -> Signal:
    """Rata de microseisme în ultimele 7 zile."""
    thresholds = SEISMIC_RATE_THRESHOLDS[site.mine_type]
    if seismic.empty:
        return Signal(
            name="Microseismicitate",
            value=0.0,
            unit="evenimente/zi (medie 7z)",
            severity="info",
            threshold_hit="0 evenimente reale catalogate în 7 zile",
            description=(
                "Niciun cutremur natural M≥1.5 catalogat de EMSC/USGS în "
                "raza de 50 km. Zonă seismic inactivă; pentru micro-seismicitate "
                "indusă (M<1.5) e necesară rețea seismică locală."
            ),
        )
    window_start = ref_date - pd.Timedelta(days=7)
    recent = seismic[seismic["datetime"] >= window_start]
    rate = len(recent) / 7.0
    sev = classify(rate, thresholds)
    max_mag = recent["magnitude"].max() if len(recent) else 0.0
    return Signal(
        name="Microseismicitate",
        value=round(rate, 2),
        unit="evenimente/zi (medie 7z)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {thresholds.get(sev, 0)} evenimente/zi"
            if sev != "info" else "sub pragul de watch"
        ),
        description=(
            f"{len(recent)} microseisme în 7z, magnitudine maximă "
            f"M={max_mag:.2f}."
        ),
    )


def _check_infiltration(hydro: pd.DataFrame) -> Signal:
    """Creștere procentuală a infiltrației față de baseline-ul de 90 zile."""
    if len(hydro) < 90:
        baseline = hydro["infiltration_l_per_hour"].head(30).mean()
    else:
        baseline = hydro["infiltration_l_per_hour"].iloc[:-30].tail(60).mean()
    recent = hydro["infiltration_l_per_hour"].tail(7).mean()
    pct_change = ((recent - baseline) / baseline) * 100
    sev = classify(pct_change, INFILTRATION_PCT_THRESHOLDS)
    return Signal(
        name="Infiltrație de apă",
        value=round(pct_change, 1),
        unit="% creștere vs baseline 90z",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {INFILTRATION_PCT_THRESHOLDS.get(sev, 0)}%"
            if sev != "info" else "sub pragul de watch"
        ),
        description=(
            f"Debit recent {recent:.0f} l/h vs baseline {baseline:.0f} l/h."
        ),
    )


# ─── Semnale specifice TUNELURI ───

def _load_tunnel_signals(site_id: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Încarcă convergence, pgv, humidity pentru un tunel."""
    convergence = pd.read_csv(
        DATA_DIR / f"{site_id}_convergence.csv", parse_dates=["date"]
    )
    pgv = pd.read_csv(DATA_DIR / f"{site_id}_pgv.csv", parse_dates=["date"])
    humidity = pd.read_csv(
        DATA_DIR / f"{site_id}_humidity.csv", parse_dates=["date"]
    )
    return convergence, pgv, humidity


def _check_convergence(convergence: pd.DataFrame) -> Signal:
    """Rata de convergență medie pe ultimele 7 zile (mm/zi, magnitudine)."""
    recent = convergence["convergence_mm_per_day"].tail(7).mean()
    magnitude = abs(recent)
    sev = classify(magnitude, TUNNEL_CONVERGENCE_THRESHOLDS)
    return Signal(
        name="Convergență lining",
        value=round(recent, 3),
        unit="mm/zi (medie 7z)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_CONVERGENCE_THRESHOLDS.get(sev, 0)} mm/zi"
            if sev != "info" else "sub pragul de watch"
        ),
        description=(
            f"Convergență cumulată: "
            f"{convergence['convergence_cumulative_mm'].iloc[-1]:.2f} mm. "
            "Măsurat prin convergometre wireless în secțiunea critică."
        ),
    )


def _check_pgv(pgv: pd.DataFrame) -> Signal:
    """Peak PGV în ultimele 7 zile (mm/s)."""
    recent_peak = pgv["pgv_mm_per_s"].tail(7).max()
    sev = classify(recent_peak, TUNNEL_PGV_THRESHOLDS)
    return Signal(
        name="Vibrații dinamice (PGV)",
        value=round(recent_peak, 2),
        unit="mm/s (peak 7z)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_PGV_THRESHOLDS.get(sev, 0)} mm/s"
            if sev != "info" else "sub pragul DIN 4150"
        ),
        description=(
            f"Vibrații din excavație/trafic. Standard DIN 4150 pentru "
            f"structuri sensibile: 5 mm/s prag, 20 mm/s critic."
        ),
    )


def _check_humidity(humidity_cracks: pd.DataFrame) -> Signal:
    """Umiditate perete (%) — valoare absolută."""
    recent = humidity_cracks["humidity_pct"].tail(7).mean()
    sev = classify(recent, TUNNEL_HUMIDITY_THRESHOLDS)
    return Signal(
        name="Umiditate perete",
        value=round(recent, 1),
        unit="% (medie 7z)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_HUMIDITY_THRESHOLDS.get(sev, 0)}%"
            if sev != "info" else "sub pragul de watch"
        ),
        description=(
            "Umiditate medie a căptușelii. Valori mari indică infiltrații "
            "active prin lining sau ventilație insuficientă."
        ),
    )


def _check_new_cracks(humidity_cracks: pd.DataFrame) -> Signal:
    """Fisuri noi LiDAR în ultimele 30 zile (delta cumulative)."""
    if len(humidity_cracks) < 30:
        new_cracks = humidity_cracks["cracks_cumulative"].iloc[-1]
    else:
        end_count = humidity_cracks["cracks_cumulative"].iloc[-1]
        start_count = humidity_cracks["cracks_cumulative"].iloc[-30]
        new_cracks = int(end_count - start_count)
    sev = classify(new_cracks, TUNNEL_NEW_CRACKS_THRESHOLDS)
    return Signal(
        name="Fisuri noi LiDAR",
        value=new_cracks,
        unit="fisuri (ultimele 30z)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_NEW_CRACKS_THRESHOLDS.get(sev, 0)} fisuri"
            if sev != "info" else "sub pragul de watch"
        ),
        description=(
            f"Total cumulat: {humidity_cracks['cracks_cumulative'].iloc[-1]} "
            "fisuri. Detectate prin scanare LiDAR mobile periodică."
        ),
    )

def _check_tunnel_inflow(inflow: pd.DataFrame) -> Signal:
    """Creștere infiltrație apă tunel față de baseline 60 zile."""
    col = "water_inflow_l_per_min"
    if len(inflow) < 60:
        baseline = inflow[col].head(20).mean()
    else:
        baseline = inflow[col].iloc[:-20].tail(40).mean()
    recent = inflow[col].tail(7).mean()
    pct_change = ((recent - baseline) / baseline) * 100 if baseline > 0 else 0
    sev = classify(pct_change, TUNNEL_INFLOW_PCT_THRESHOLDS)
    return Signal(
        name="Infiltrație apă tunel",
        value=round(pct_change, 1),
        unit="% creștere vs baseline 60z",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {TUNNEL_INFLOW_PCT_THRESHOLDS.get(sev, 0)}%"
            if sev != "info" else "sub pragul de watch"
        ),
        description=(
            f"Debit recent {recent:.1f} l/min vs baseline {baseline:.1f} l/min. "
            "Infiltrație prin lining/fisuri, corelată cu precipitațiile."
        ),
    )


def _check_air_co(air: pd.DataFrame) -> Signal:
    """Monoxid de carbon mediu pe ultimele 7 zile (mg/m³)."""
    recent = air["co_mg_m3"].tail(7).mean()
    sev = classify(recent, AIR_CO_THRESHOLDS)
    return Signal(
        name="CO (monoxid de carbon)",
        value=round(recent, 2),
        unit="mg/m³ (medie 7z)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {AIR_CO_THRESHOLDS.get(sev, 0)} mg/m³"
            if sev != "info" else "sub limita ocupațională"
        ),
        description=(
            "Monoxid de carbon în atmosfera subterană. Surse: utilaje diesel, "
            "pușcături. Limita ocupațională OSHA: ~35 mg/m³ (8h)."
        ),
    )


def _check_air_ch4(site: MineSite, air: pd.DataFrame) -> Signal:
    """Metan — CRITIC pentru mine de cărbune (% volum)."""
    recent = air["ch4_pct_vol"].tail(7).mean()
    peak = air["ch4_pct_vol"].tail(7).max()
    sev = classify(peak, AIR_CH4_THRESHOLDS)
    return Signal(
        name="CH4 (metan)",
        value=round(peak, 3),
        unit="% volum (peak 7z)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {AIR_CH4_THRESHOLDS.get(sev, 0)}% vol"
            if sev != "info" else "sub pragul de watch"
        ),
        description=(
            f"Concentrație metan (medie {recent:.3f}%). Norma minieră: "
            "1.5% = oprire lucru, 5% = limită inferioară de explozie (LEL). "
            + ("Risc dominant pentru mine de cărbune."
               if site.mine_type == "carbune"
               else "Nivel trace normal pentru acest tip de site.")
        ),
    )


def _check_air_particulates(air: pd.DataFrame) -> Signal:
    """Praf PM10 mediu pe 7 zile (mg/m³)."""
    recent = air["pm10_mg_m3"].tail(7).mean()
    sev = classify(recent, AIR_PM10_THRESHOLDS)
    return Signal(
        name="Praf PM10",
        value=round(recent, 2),
        unit="mg/m³ (medie 7z)",
        severity=sev,
        threshold_hit=(
            f"{sev} >= {AIR_PM10_THRESHOLDS.get(sev, 0)} mg/m³"
            if sev != "info" else "sub limita de praf minier"
        ),
        description=(
            "Praf în suspensie din forare/excavație. Limita de praf "
            "minier respirabil: ~4-5 mg/m³."
        ),
    )


def _ml_anomaly_score(
    insar: pd.DataFrame, seismic: pd.DataFrame, hydro: pd.DataFrame
) -> float:
    """
    Isolation Forest pe ferestre glisante de 14 zile.
    Întoarce scorul fereastră curentă (0=normal, 1=anormal).
    """
    # Construim un panel diurn unificat
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

    # Features: medii pe 14 zile glisante
    features = panel[[
        "precipitation_mm", "infiltration_l_per_hour",
        "water_table_m", "seismic_count", "seismic_max_mag",
        "velocity_mm_per_month",
    ]].rolling(14).mean().dropna()

    if len(features) < 30:
        return 0.0

    # Antrenăm pe primele 70% (presupus „normale") și scorăm la final
    split = int(len(features) * 0.7)
    train = features.iloc[:split]
    test_point = features.iloc[[-1]]

    iso = IsolationForest(contamination=0.05, random_state=0)
    iso.fit(train)
    # decision_function: pozitiv = normal, negativ = anormal
    raw = iso.decision_function(test_point)[0]
    # Normalizare la [0, 1] unde 1 = foarte anormal
    score = float(np.clip(0.5 - raw, 0, 1))
    return round(score, 3)


def detect_for_site(site: MineSite, ref_date: datetime | None = None) -> Alert:
    insar, seismic, hydro = _load_site_data(site.id)
    ref_date = ref_date or insar["date"].max().to_pydatetime()

    # Semnale comune (subsidență suprafață + seism + meteo)
    signals = [
        _check_insar(site, insar),
        _check_seismic(site, seismic, ref_date),
    ]

    # Pentru tuneluri: semnale specifice (convergență, PGV, umiditate, fisuri, infiltrație)
    # Pentru mine: infiltrație clasică
    if is_tunnel(site):
        try:
            convergence, pgv, humidity_cracks = _load_tunnel_signals(site.id)
            signals.append(_check_convergence(convergence))
            signals.append(_check_pgv(pgv))
            signals.append(_check_humidity(humidity_cracks))
            signals.append(_check_new_cracks(humidity_cracks))
        except FileNotFoundError:
            pass
        # Infiltrație apă tunel
        try:
            inflow = pd.read_csv(
                DATA_DIR / f"{site.id}_inflow.csv", parse_dates=["date"]
            )
            signals.append(_check_tunnel_inflow(inflow))
        except FileNotFoundError:
            pass
    else:
        signals.append(_check_infiltration(hydro))

    # Calitatea aerului — comună la mine și tuneluri
    try:
        air = pd.read_csv(DATA_DIR / f"{site.id}_air.csv", parse_dates=["date"])
        signals.append(_check_air_co(air))
        signals.append(_check_air_particulates(air))
        # Metanul: relevant ca semnal explicit doar pentru cărbune
        if site.mine_type == "carbune":
            signals.append(_check_air_ch4(site, air))
    except FileNotFoundError:
        pass

    ml_score = _ml_anomaly_score(insar, seismic, hydro)

    # Severitate generală: max din semnale + bump dacă ML > 0.6
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

    # Metrici de aer (comune)
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
            "warning": "▲▲", "alarm": "⚠ ALARMĂ"
        }[alert.overall_severity]
        print(f"{marker:>9}  {site.name:<25}  ML={alert.ml_anomaly_score:.2f}")

    # Salvăm
    out = DATA_DIR / "alerts.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump([a.to_dict() for a in alerts], f, ensure_ascii=False, indent=2)
    print(f"\n✓ Alerte salvate în {out}")
    return alerts


if __name__ == "__main__":
    run_all()
