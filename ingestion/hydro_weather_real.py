"""
Ingestie meteo + hidro DIN DATE REALE — Open-Meteo Historical API.

Open-Meteo:
    - Gratuit, fără cheie API, fără limită rezonabilă de rate
    - Endpoint: https://archive-api.open-meteo.com/v1/archive
    - Date din ERA5 reanalysis: precise, validate, până la 1940
    - Latență: ~5 zile (deci pentru ultimele zile folosim forecast historical)

Conceptual: înlocuim partea SINTETICĂ de precipitații cu date reale.
Infiltrația rămâne modelată (pentru că nu există date publice instituționale),
DAR se calculează din precipitațiile REALE. Asta înseamnă că dacă prin
Praid a plouat mult în primăvara 2025, infiltrația modelată va reflecta asta.
"""

from datetime import datetime, timedelta
import time

import numpy as np
import pandas as pd
import requests

from config import MineSite


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEOUT = 30


def fetch_openmeteo_real(
    site: MineSite,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """
    Descarcă precipitații zilnice reale din ERA5 pentru locația site-ului.

    Returns:
        DataFrame cu coloane: date, precipitation_mm, temperature_mean_c
    """
    params = {
        "latitude": site.lat,
        "longitude": site.lon,
        "start_date": start.date().isoformat(),
        "end_date": end.date().isoformat(),
        "daily": "precipitation_sum,temperature_2m_mean",
        "timezone": "Europe/Bucharest",
    }
    r = requests.get(ARCHIVE_URL, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    daily = data["daily"]
    df = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "precipitation_mm": daily["precipitation_sum"],
        "temperature_mean_c": daily["temperature_2m_mean"],
    })
    # Open-Meteo poate întoarce None pentru zile fără date
    df["precipitation_mm"] = df["precipitation_mm"].fillna(0)
    df["temperature_mean_c"] = df["temperature_mean_c"].ffill()
    return df


def model_infiltration_from_precip(
    precip_mm: np.ndarray,
    site: MineSite,
    *,
    event_acceleration: bool = False,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Modelează infiltrația și nivelul freatic pornind de la precipitații REALE.

    Modelul:
        infiltration(t) = baseline + k * sum(precip[t-14..t] * decay_weights)

    Pentru site cu eveniment: adăugăm accelerație în ultimele 45 zile
    (simulând fisura nouă care apare în pre-eveniment).
    """
    rng = np.random.default_rng(seed + hash(site.id) % 1000)
    n = len(precip_mm)
    infiltration_lph = np.zeros(n)

    for i in range(n):
        window = precip_mm[max(0, i - 14):i + 1]
        weights = np.exp(-np.arange(len(window))[::-1] / 5.0)
        infiltration_lph[i] = (
            150 + 30 * np.sum(window * weights) / weights.sum()
        )

    if event_acceleration:
        accel_start = int(n * 0.85)
        days = np.arange(n - accel_start)
        infiltration_lph[accel_start:] += 50 * (1 + days / 10) ** 1.4

    # Nivel freatic
    water_table_m = -8 - 0.001 * (
        infiltration_lph - infiltration_lph.mean()
    )
    water_table_m += rng.normal(0, 0.1, n)

    return infiltration_lph, water_table_m


def fetch_hydro_weather(
    site: MineSite, start: datetime, end: datetime
) -> pd.DataFrame:
    """
    Hook public — date hibride: meteo REAL + infiltrație modelată din meteo real.

    Notă: dacă endpoint-ul Open-Meteo nu răspunde, întoarcem fallback sintetic.
    """
    try:
        meteo = fetch_openmeteo_real(site, start, end)
    except Exception as e:
        print(f"  ⚠ Open-Meteo a eșuat pentru {site.id}: {e}")
        print(f"    Folosesc fallback sintetic.")
        from ingestion.hydro_weather import generate_synthetic_hydro_weather
        return generate_synthetic_hydro_weather(
            site, start, end,
            event_acceleration=(site.id == "praid"),
        )

    has_event = site.id == "praid"
    infiltration, water_table = model_infiltration_from_precip(
        meteo["precipitation_mm"].to_numpy(),
        site,
        event_acceleration=has_event,
    )

    return pd.DataFrame({
        "date": meteo["date"],
        "precipitation_mm": meteo["precipitation_mm"].round(1),
        "temperature_mean_c": meteo["temperature_mean_c"].round(1),
        "infiltration_l_per_hour": infiltration.round(0),
        "water_table_m": water_table.round(2),
        "site_id": site.id,
    })


if __name__ == "__main__":
    from config import get_site
    site = get_site("praid")
    end = datetime(2025, 6, 1)
    start = end - timedelta(days=180)

    # Test direct pe Open-Meteo (date pure, fără modelare suplimentară)
    print("=== Test 1: Open-Meteo raw ===")
    raw = fetch_openmeteo_real(site, start, end)
    print(f"  Înregistrări: {len(raw)}")
    print(f"  Precipitații totale: {raw['precipitation_mm'].sum():.1f} mm")
    print(f"  Temperatură medie: {raw['temperature_mean_c'].mean():.1f}°C")
    print(f"  Zile cu ploaie >5mm: {(raw['precipitation_mm'] > 5).sum()}")

    # Test pe pipeline-ul complet (cu infiltrație modelată)
    print("\n=== Test 2: Pipeline complet (Praid) ===")
    df = fetch_hydro_weather(site, start, end)
    print(f"  Înregistrări: {len(df)}")
    print(f"  Coloane: {list(df.columns)}")
    print(f"\n  Ultimele 5 zile:")
    print(df.tail())
