"""
Ingestie date de subsidență InSAR.

SINTETIC (acum):
    Random walk cu drift accelerat în ultimele 30 zile pentru site-urile
    marcate cu eveniment (ex: Praid). Restul: random walk staționar.

REAL (la hackathon final):
    EGMS (European Ground Motion Service) — https://egms.land.copernicus.eu/
    Endpoint: descarcă CSV cu serii temporale per punct de măsurare.
    Documentație: https://land.copernicus.eu/en/products/european-ground-motion-service

    Înlocuiește `generate_synthetic_insar` cu:

    def fetch_egms(lat, lon, radius_m=500, start, end):
        # 1. Identifică PS-urile (Persistent Scatterers) din raza dată
        # 2. Descarcă seria temporală LOS (Line of Sight) pentru fiecare
        # 3. Mediază sau ia maximul de deformare → o serie agregată
        ...
"""

from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from config import MineSite


def generate_synthetic_insar(
    site: MineSite,
    start: datetime,
    end: datetime,
    *,
    event_acceleration: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generează o serie temporală InSAR sintetică dar plauzibilă.

    Returns:
        DataFrame cu coloane: date, displacement_mm, velocity_mm_per_month
        displacement = deplasare cumulată față de t0 (negativ = subsidență)
    """
    rng = np.random.default_rng(seed + hash(site.id) % 1000)

    # Sentinel-1 are revizita la 6 zile; EGMS livrează ~12 zile
    dates = pd.date_range(start, end, freq="12D")
    n = len(dates)

    # Drift de bază (mm/an): rate tipice pentru subsidență
    baseline_rate_mm_per_year = {
        "sare": -3.5,
        "sare_inchisa": -1.5,
        "carbune": -8.0,
        "uraniu": -2.0,
        "metal_neferos": -2.5,
        # Tuneluri: subsidență suprafață deasupra aliniamentului
        # Tunel forat în execuție: -2 până la -4 mm/an local
        "tunel_autostrada": -2.5,
        "tunel_feroviar": -2.5,
    }[site.mine_type]
    daily_drift = baseline_rate_mm_per_year / 365.0
    drift = np.arange(n) * 12 * daily_drift

    # Zgomot atmosferic InSAR ~ 2-4 mm std
    noise = rng.normal(0, 2.5, n)

    displacement = drift + noise

    # Dacă site-ul are eveniment apropiat, accelerează în ultima parte
    if event_acceleration:
        # Ultima 1/4 din serie: accelerație neliniară
        accel_start = int(n * 0.75)
        days_into_accel = np.arange(n - accel_start) * 12
        # Curbă exponențială: subsidență accelerată în pre-eveniment
        accel = -0.02 * days_into_accel**1.9
        displacement[accel_start:] += accel

    # Calculează velocity glisant (mm/lună)
    df = pd.DataFrame({
        "date": dates,
        "displacement_mm": displacement,
        "site_id": site.id,
    })
    df["velocity_mm_per_month"] = (
        df["displacement_mm"].diff(periods=3) / (3 * 12 / 30)
    )
    return df


def fetch_insar(site: MineSite, start: datetime, end: datetime) -> pd.DataFrame:
    """Hook public — în prod îți pluggezi EGMS aici."""
    # Site cu eveniment cunoscut → simulează accelerație
    has_event = site.id == "praid"
    return generate_synthetic_insar(
        site, start, end, event_acceleration=has_event
    )


if __name__ == "__main__":
    from config import SITES
    end = datetime(2025, 6, 1)
    start = end - timedelta(days=180)
    for s in SITES[:3]:
        df = fetch_insar(s, start, end)
        print(f"{s.name}: {len(df)} măsurători, "
              f"deplasare finală {df['displacement_mm'].iloc[-1]:.1f} mm")
