"""
Air-quality ingestion.

Two layers:
1. **Surface air (REAL)** — Open-Meteo Air Quality API.
   Free, no API key required. PM10, PM2.5, CO, NO2, O3.
   Endpoint: https://air-quality-api.open-meteo.com/v1/air-quality

2. **Underground air (MODELED)** — air inside the gallery/tunnel.
   Calculated as: surface_air (real) + activity contribution.
   - PM10 dust increased by drilling/excavation
   - CO increased by diesel equipment and blasting
   - NO2 from equipment engines
   - For coal mines: CH4 (methane) — 100% local-sensor signal, separately modeled

Hybrid rationale: underground air quality does not exist as a public data source;
it depends on ventilation, equipment and geology. Surface air is a real baseline,
while the activity contribution can be physically modeled.

Thresholds (see detection/thresholds.py):
- CO: 30 ppm = occupational exposure limit (OSHA)
- NO2: 5 ppm
- CH4: 1% vol = alarm, 5% = lower explosive limit (LEL)
- PM10: 5 mg/m³ = mining dust limit
"""

from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests

from config import MineSite, is_tunnel


AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
ARCHIVE_AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEOUT = 30


def fetch_surface_air_quality(
    site: MineSite, start: datetime, end: datetime
) -> pd.DataFrame:
    """
    Download SURFACE air quality from Open-Meteo (REAL).

    Returns:
        Daily DataFrame: date, pm10_surface, pm25_surface,
                         co_surface, no2_surface (μg/m³)
    """
    params = {
        "latitude": site.lat,
        "longitude": site.lon,
        "start_date": start.date().isoformat(),
        "end_date": end.date().isoformat(),
        "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide",
        "timezone": "Europe/Bucharest",
    }
    r = requests.get(AIR_QUALITY_URL, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    hourly = data["hourly"]
    df = pd.DataFrame({
        "datetime": pd.to_datetime(hourly["time"]),
        "pm10": hourly["pm10"],
        "pm25": hourly["pm2_5"],
        "co": hourly["carbon_monoxide"],
        "no2": hourly["nitrogen_dioxide"],
    })
    # Agregăm la zi (medie)
    df["date"] = df["datetime"].dt.normalize()
    daily = df.groupby("date").agg(
        pm10_surface=("pm10", "mean"),
        pm25_surface=("pm25", "mean"),
        co_surface=("co", "mean"),
        no2_surface=("no2", "mean"),
    ).reset_index()
    # Open-Meteo poate avea None — completăm
    for col in ["pm10_surface", "pm25_surface", "co_surface", "no2_surface"]:
        daily[col] = daily[col].ffill().bfill()
    return daily


def _generate_synthetic_surface_air(
    site: MineSite, start: datetime, end: datetime, seed: int = 42
) -> pd.DataFrame:
    """Synthetic fallback for surface air when the API fails."""
    rng = np.random.default_rng(seed + hash(site.id) % 1000 + 7)
    dates = pd.date_range(start, end, freq="D")
    n = len(dates)
    # Valori plauzibile pentru aer rural/semi-urban România
    return pd.DataFrame({
        "date": dates,
        "pm10_surface": np.clip(rng.normal(18, 6, n), 2, None).round(1),
        "pm25_surface": np.clip(rng.normal(11, 4, n), 1, None).round(1),
        "co_surface": np.clip(rng.normal(180, 40, n), 50, None).round(0),
        "no2_surface": np.clip(rng.normal(9, 4, n), 1, None).round(1),
    })


def model_underground_air(
    surface: pd.DataFrame,
    site: MineSite,
    *,
    event_acceleration: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Model UNDERGROUND air starting from real surface air.

    underground = surface + activity_contribution

    The activity contribution depends on:
    - site type (active mine / tunnel under construction)
    - diesel equipment (CO, NO2)
    - drilling/excavation (PM10 dust)
    """
    rng = np.random.default_rng(seed + hash(site.id) % 1000 + 8)
    n = len(surface)

    # Factori de contribuție din activitate
    if site.status in ("activa", "constructie"):
        # Excavație/extracție activă → contribuție mare
        co_activity = 8.0       # mg/m³ adițional (utilaje diesel)
        no2_activity = 2.5
        pm10_activity = 2.0     # mg/m³ praf de forare
    elif site.status == "operare":
        co_activity = 2.0       # tunel în operare → trafic
        no2_activity = 1.5
        pm10_activity = 0.5
    else:
        co_activity = 0.5       # mină închisă / tunel în proiectare
        no2_activity = 0.3
        pm10_activity = 0.3

    # Convertim surface de la μg/m³ la mg/m³ pentru consistență
    co_underground = surface["co_surface"].to_numpy() / 1000.0 + co_activity
    co_underground += rng.normal(0, 1.0, n)
    no2_underground = surface["no2_surface"].to_numpy() / 1000.0 + no2_activity
    no2_underground += rng.normal(0, 0.4, n)
    pm10_underground = surface["pm10_surface"].to_numpy() / 1000.0 + pm10_activity
    pm10_underground += rng.normal(0, 0.3, n)

    # Metan: doar pentru cărbune (emisie din strat)
    # Pentru sare/tuneluri: ~0, doar trace
    if site.mine_type == "carbune":
        ch4_base = 0.3  # % vol — emisie continuă din cărbune
        ch4 = rng.normal(ch4_base, 0.08, n)
    else:
        ch4 = rng.normal(0.02, 0.01, n)  # trace

    if event_acceleration:
        # Pre-eveniment: ventilație compromisă → acumulare gaze
        accel_start = int(n * 0.82)
        days = np.arange(n - accel_start)
        co_underground[accel_start:] += 1.5 * (1 + days / 12)
        if site.mine_type == "carbune":
            # Acumulare metan periculoasă
            ch4[accel_start:] += 0.15 * (1 + days / 10)
        pm10_underground[accel_start:] += 0.3 * (1 + days / 15)

    return pd.DataFrame({
        "date": surface["date"],
        "co_mg_m3": np.clip(co_underground, 0, None).round(2),
        "no2_mg_m3": np.clip(no2_underground, 0, None).round(2),
        "pm10_mg_m3": np.clip(pm10_underground, 0, None).round(2),
        "ch4_pct_vol": np.clip(ch4, 0, None).round(3),
        "site_id": site.id,
    })


def fetch_air_quality(
    site: MineSite, start: datetime, end: datetime
) -> pd.DataFrame:
    """
    Public hook — underground air modeled from real surface air.

    Returns:
        Daily DataFrame with underground air quality inside the gallery/tunnel.
    """
    try:
        surface = fetch_surface_air_quality(site, start, end)
    except Exception as e:
        print(f"  ⚠ Open-Meteo Air Quality failed for {site.id}: {e}")
        print(f"    Using synthetic fallback for surface air.")
        surface = _generate_synthetic_surface_air(site, start, end)

    # Site cu eveniment: ventilație compromisă în pre-eveniment
    event_sites = {"praid", "margina_holdea_t2"}
    has_event = site.id in event_sites

    underground = model_underground_air(
        surface, site, event_acceleration=has_event
    )
    return underground


if __name__ == "__main__":
    from config import get_site
    end = datetime(2026, 5, 1)
    start = end - timedelta(days=180)

    for site_id in ["praid", "lupeni", "margina_holdea_t2"]:
        site = get_site(site_id)
        df = fetch_air_quality(site, start, end)
        print(f"\n=== {site.name} ({site.mine_type}) ===")
        print(f"  Records: {len(df)}")
        print(f"  CO mediu: {df['co_mg_m3'].mean():.2f} mg/m³ "
              f"(max {df['co_mg_m3'].max():.2f})")
        print(f"  NO2 mediu: {df['no2_mg_m3'].mean():.2f} mg/m³")
        print(f"  PM10 mediu: {df['pm10_mg_m3'].mean():.2f} mg/m³")
        print(f"  CH4 mediu: {df['ch4_pct_vol'].mean():.3f}% vol "
              f"(max {df['ch4_pct_vol'].max():.3f})")
