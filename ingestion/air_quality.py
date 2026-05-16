"""
Ingestie CALITATEA AERULUI.

Două straturi:
1. **Aer suprafață (REAL)** — Open-Meteo Air Quality API.
   Gratuit, fără cheie. PM10, PM2.5, CO, NO2, O3.
   Endpoint: https://air-quality-api.open-meteo.com/v1/air-quality

2. **Aer subteran (MODELAT)** — aerul din galerie/tunel.
   Calculat ca: aer_suprafață (real) + contribuție din activitate.
   - Praf (PM10) crescut de forare/excavație
   - CO crescut de utilaje diesel și pușcături
   - NO2 de la motoarele utilajelor
   - Pentru mine de cărbune: CH4 (metan) — 100% senzor local, modelat separat

De ce hibrid: calitatea aerului subteran NU există ca sursă publică —
depinde de ventilație, utilaje, geologie. Dar aerul de suprafață e un
baseline real, iar contribuția din activitate e modelabilă fizic.

Praguri (vezi detection/thresholds.py):
- CO: 30 ppm = limită expunere ocupațională (OSHA)
- NO2: 5 ppm
- CH4: 1% vol = alarmă, 5% = limită inferioară de explozie (LEL)
- PM10: 5 mg/m³ = limită praf minier
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
    Descarcă calitatea aerului de SUPRAFAȚĂ de la Open-Meteo (REAL).

    Returns:
        DataFrame zilnic: date, pm10_surface, pm25_surface,
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
    """Fallback sintetic pentru aerul de suprafață când API-ul pică."""
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
    Modelează aerul SUBTERAN pornind de la aerul de suprafață real.

    underground = surface + activity_contribution

    Contribuția din activitate depinde de:
    - tipul site-ului (mină activă / tunel în construcție)
    - utilaje diesel (CO, NO2)
    - forare/excavație (PM10 praf)
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
    Hook public — aer subteran modelat din aer suprafață real.

    Returns:
        DataFrame zilnic cu calitatea aerului subteran (în galerie/tunel).
    """
    try:
        surface = fetch_surface_air_quality(site, start, end)
    except Exception as e:
        print(f"  ⚠ Open-Meteo Air Quality a eșuat pentru {site.id}: {e}")
        print(f"    Folosesc fallback sintetic pentru aer suprafață.")
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
        print(f"  Înregistrări: {len(df)}")
        print(f"  CO mediu: {df['co_mg_m3'].mean():.2f} mg/m³ "
              f"(max {df['co_mg_m3'].max():.2f})")
        print(f"  NO2 mediu: {df['no2_mg_m3'].mean():.2f} mg/m³")
        print(f"  PM10 mediu: {df['pm10_mg_m3'].mean():.2f} mg/m³")
        print(f"  CH4 mediu: {df['ch4_pct_vol'].mean():.3f}% vol "
              f"(max {df['ch4_pct_vol'].max():.3f})")
