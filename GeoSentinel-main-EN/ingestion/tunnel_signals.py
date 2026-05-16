"""
Tunnel-specific signal ingestion.

Unlike mines, tunnels are monitored through lining convergence, dynamic PGV
vibrations, wall humidity, LiDAR crack detection, surface subsidence and water
inflow. This module generates synthetic demo data with clear hooks for real
sensors in production.
"""

from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from config import MineSite


def generate_synthetic_tunnel_convergence(
    site: MineSite,
    start: datetime,
    end: datetime,
    *,
    event_acceleration: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate tunnel convergence (mm/day at measurement points).

    Model:
    - 0 mm/day baseline for a stable tunnel
    - small drift around zero
    - active excavation produces higher convergence
    - event_acceleration simulates a weakened support zone
    """
    rng = np.random.default_rng(seed + hash(site.id) % 1000)

    dates = pd.date_range(start, end, freq="D")
    n = len(dates)

    # Convergența de bază depinde de stadiul excavației
    if site.status == "constructie" and site.excavation_progress_pct > 0:
        baseline_mm_per_day = -0.2  # tunel în excavație, adaptare elastică normală
    elif site.status == "operare":
        baseline_mm_per_day = -0.02  # tunel finalizat, mișcări reziduale
    else:
        baseline_mm_per_day = -0.05  # baseline / pre-construcție

    convergence = np.full(n, baseline_mm_per_day, dtype=float)
    convergence += rng.normal(0, 0.08, n)  # zgomot măsurare

    if event_acceleration:
        accel_start = int(n * 0.80)
        days = np.arange(n - accel_start)
        # Accelerație neliniară pentru pilier slăbit
        convergence[accel_start:] -= 0.04 * (1 + days / 8) ** 1.3

    df = pd.DataFrame({
        "date": dates,
        "convergence_mm_per_day": convergence.round(3),
        "site_id": site.id,
    })
    # Cumulat (cumulative displacement)
    df["convergence_cumulative_mm"] = df["convergence_mm_per_day"].cumsum().round(2)
    return df


def generate_synthetic_pgv(
    site: MineSite,
    start: datetime,
    end: datetime,
    *,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate daily PGV (Peak Ground Velocity, mm/s).

    For tunnels, vibrations come from excavation, overhead traffic and local seismic activity.
    """
    rng = np.random.default_rng(seed + hash(site.id) % 1000 + 1)

    dates = pd.date_range(start, end, freq="D")
    n = len(dates)

    if site.status == "constructie":
        # Vibrații din pușcături controlate / TBM
        base_pgv = 1.5  # mm/s mediu zilnic
        spike_prob = 0.20  # zile cu pușcătură mai mare
        spike_amplitude = 8.0
    elif site.status == "operare":
        base_pgv = 0.8  # trafic
        spike_prob = 0.05
        spike_amplitude = 3.0
    else:
        base_pgv = 0.3
        spike_prob = 0.02
        spike_amplitude = 2.0

    pgv = rng.exponential(base_pgv, n)
    spikes = rng.random(n) < spike_prob
    pgv[spikes] += rng.uniform(2, spike_amplitude, spikes.sum())

    return pd.DataFrame({
        "date": dates,
        "pgv_mm_per_s": pgv.round(2),
        "site_id": site.id,
    })


def generate_synthetic_humidity_cracks(
    site: MineSite,
    start: datetime,
    end: datetime,
    *,
    event_acceleration: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate wall humidity (%) and cumulative new LiDAR crack count.
    """
    rng = np.random.default_rng(seed + hash(site.id) % 1000 + 2)

    dates = pd.date_range(start, end, freq="D")
    n = len(dates)

    # Umiditate de bază + sezonalitate
    day_of_year = dates.dayofyear.to_numpy()
    seasonal = 5 * np.sin(2 * np.pi * (day_of_year - 100) / 365)

    if site.status == "constructie":
        base_humidity = 55  # mediu pentru excavație activă
    elif site.status == "operare":
        base_humidity = 35
    else:
        base_humidity = 40

    humidity = base_humidity + seasonal + rng.normal(0, 3, n)

    # Fisuri noi LiDAR (cumulative count, scanări la 7 zile)
    new_cracks_per_scan = rng.poisson(0.3, n // 7 + 1)
    cracks_cumulative = np.zeros(n)
    for i in range(n):
        scan_idx = i // 7
        cracks_cumulative[i] = new_cracks_per_scan[:scan_idx + 1].sum()

    if event_acceleration:
        # Creștere umiditate + spike fisuri în pre-eveniment
        accel_start = int(n * 0.85)
        days = np.arange(n - accel_start)
        humidity[accel_start:] += 2 * (1 + days / 15)
        # Mai multe fisuri în ultima parte
        cracks_cumulative[accel_start:] += np.arange(n - accel_start) * 0.3

    return pd.DataFrame({
        "date": dates,
        "humidity_pct": humidity.round(1),
        "cracks_cumulative": cracks_cumulative.round(0).astype(int),
        "site_id": site.id,
    })


def generate_synthetic_tunnel_inflow(
    site: MineSite,
    start: datetime,
    end: datetime,
    precipitation_mm: np.ndarray | None = None,
    *,
    event_acceleration: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate tunnel water inflow (l/min).

    Water enters the gallery through lining cracks and through groundwater intercepted by the tunnel.
    If real precipitation is provided, inflow reflects it, just like in mines.
    """
    rng = np.random.default_rng(seed + hash(site.id) % 1000 + 5)
    dates = pd.date_range(start, end, freq="D")
    n = len(dates)

    # Debit de bază — depinde de adâncimea acoperirii și stadiu
    if site.status == "constructie":
        base_inflow = 12.0  # l/min — excavație activă interceptează pânze
    elif site.status == "operare":
        base_inflow = 4.0   # tunel finalizat cu hidroizolație
    else:
        base_inflow = 6.0

    inflow = np.full(n, base_inflow, dtype=float)

    # Dacă avem precipitații reale, infiltrația le reflectă (decalaj 7 zile)
    if precipitation_mm is not None and len(precipitation_mm) == n:
        for i in range(n):
            window = precipitation_mm[max(0, i - 10):i + 1]
            weights = np.exp(-np.arange(len(window))[::-1] / 4.0)
            rain_contribution = (
                0.4 * np.sum(window * weights) / weights.sum()
            )
            inflow[i] += rain_contribution
    else:
        # Sezonalitate sintetică
        day_of_year = dates.dayofyear.to_numpy()
        inflow += 3 * np.sin(2 * np.pi * (day_of_year - 100) / 365)

    inflow += rng.normal(0, 1.0, n)

    if event_acceleration:
        # Fisură nouă → infiltrație crescută brusc
        accel_start = int(n * 0.85)
        days = np.arange(n - accel_start)
        inflow[accel_start:] += 4 * (1 + days / 12) ** 1.3

    return pd.DataFrame({
        "date": dates,
        "water_inflow_l_per_min": np.clip(inflow, 0, None).round(1),
        "site_id": site.id,
    })


def fetch_tunnel_signals(
    site: MineSite, start: datetime, end: datetime,
    precipitation_mm: np.ndarray | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Public hook — return all signals for a tunnel.

    Args:
        precipitation_mm: optional real precipitation for coupling inflow.

    Returns:
        Dict with keys: 'convergence', 'pgv', 'humidity_cracks', 'inflow'
    """
    has_event = site.id == "margina_holdea_t2"

    return {
        "convergence": generate_synthetic_tunnel_convergence(
            site, start, end, event_acceleration=has_event
        ),
        "pgv": generate_synthetic_pgv(site, start, end),
        "humidity_cracks": generate_synthetic_humidity_cracks(
            site, start, end, event_acceleration=has_event
        ),
        "inflow": generate_synthetic_tunnel_inflow(
            site, start, end, precipitation_mm,
            event_acceleration=has_event
        ),
    }


if __name__ == "__main__":
    from config import get_site
    site = get_site("margina_holdea_t2")
    end = datetime(2026, 5, 1)
    start = end - timedelta(days=180)
    signals = fetch_tunnel_signals(site, start, end)
    print(f"=== {site.name} ===")
    for name, df in signals.items():
        print(f"\n{name}:")
        print(df.tail(5))
