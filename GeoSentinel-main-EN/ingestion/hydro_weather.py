"""
Hydro/weather ingestion for infiltration, groundwater level and precipitation.

SYNTHETIC: seasonal sinusoid + noise + pre-event spikes.
REAL: see hydro_weather_real.py for Open-Meteo historical data.
"""

from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from config import MineSite


def generate_synthetic_hydro_weather(
    site: MineSite,
    start: datetime,
    end: datetime,
    *,
    event_acceleration: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed + hash(site.id) % 1000 + 2)
    dates = pd.date_range(start, end, freq="D")
    n = len(dates)

    # Precipitații zilnice — exponențială + sezonalitate
    day_of_year = dates.dayofyear.to_numpy()
    seasonal = 2 + 1.5 * np.sin(2 * np.pi * (day_of_year - 100) / 365)
    precip = rng.exponential(seasonal, n)
    precip[precip < 0.1] = 0

    # Infiltrație în mină = funcție întârziată de precipitații
    infiltration_lph = np.zeros(n)
    for i in range(n):
        # Suma precipitațiilor ultimelor 14 zile, atenuat
        window = precip[max(0, i - 14):i + 1]
        weights = np.exp(-np.arange(len(window))[::-1] / 5.0)
        infiltration_lph[i] = (
            150 + 30 * np.sum(window * weights) / weights.sum()
        )

    if event_acceleration:
        # Infiltrație crește dramatic în ultimele 45 zile (caz Praid)
        accel_start = int(n * 0.85)
        days = np.arange(n - accel_start)
        infiltration_lph[accel_start:] += 50 * (1 + days / 10) ** 1.4

    # Nivel freatic — invers proporțional cu infiltrația (apa pleacă în mină)
    water_table_m = -8 - 0.001 * (infiltration_lph - infiltration_lph.mean())
    water_table_m += rng.normal(0, 0.1, n)

    return pd.DataFrame({
        "date": dates,
        "precipitation_mm": precip.round(1),
        "infiltration_l_per_hour": infiltration_lph.round(0),
        "water_table_m": water_table_m.round(2),
        "site_id": site.id,
    })


def fetch_hydro_weather(
    site: MineSite, start: datetime, end: datetime
) -> pd.DataFrame:
    has_event = site.id == "praid"
    return generate_synthetic_hydro_weather(
        site, start, end, event_acceleration=has_event
    )


if __name__ == "__main__":
    from config import get_site
    end = datetime(2025, 6, 1)
    start = end - timedelta(days=180)
    df = fetch_hydro_weather(get_site("praid"), start, end)
    print(f"Praid hidro:\n{df.tail()}")
