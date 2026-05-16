"""
Microseismicity ingestion.

SYNTHETIC: Poisson process with increasing pre-event rate.
REAL: INFP/EMSC/USGS catalog hook can replace this generator.
"""

from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from config import MineSite


def generate_synthetic_seismic(
    site: MineSite,
    start: datetime,
    end: datetime,
    *,
    event_acceleration: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate seismic events as a Poisson process.

    The baseline rate depends on mine type and is higher for active coal/salt mines.
    """
    rng = np.random.default_rng(seed + hash(site.id) % 1000 + 1)

    base_rate_per_day = {
        "sare": 0.3,
        "sare_inchisa": 0.05,
        "carbune": 1.2,
        "uraniu": 0.1,
        "metal_neferos": 0.4,
        "tunel_autostrada": 0.05,
        "tunel_feroviar": 0.05,
    }[site.mine_type]

    total_days = (end - start).days
    events = []

    for day in range(total_days):
        current_date = start + timedelta(days=day)
        rate = base_rate_per_day

        if event_acceleration:
            # Rata crește exponențial în ultimele 60 zile
            days_to_end = total_days - day
            if days_to_end < 60:
                rate = base_rate_per_day * (1 + (60 - days_to_end) / 10) ** 1.5

        n_events = rng.poisson(rate)
        for _ in range(n_events):
            # Magnitudine din distribuție Gutenberg-Richter trunchiată
            mag = -np.log(rng.uniform(0.01, 1)) / 1.8
            mag = min(mag, 2.8)
            depth = rng.uniform(0.1, site.depth_m / 1000.0 + 0.5)
            events.append({
                "datetime": current_date + timedelta(
                    hours=float(rng.uniform(0, 24))
                ),
                "magnitude": round(mag, 2),
                "depth_km": round(depth, 2),
                "site_id": site.id,
            })

    return pd.DataFrame(events).sort_values("datetime").reset_index(drop=True)


def fetch_seismic(site: MineSite, start: datetime, end: datetime) -> pd.DataFrame:
    """Hook public — pluggezi INFP aici."""
    has_event = site.id == "praid"
    return generate_synthetic_seismic(
        site, start, end, event_acceleration=has_event
    )


if __name__ == "__main__":
    from config import get_site
    end = datetime(2025, 6, 1)
    start = end - timedelta(days=180)
    df = fetch_seismic(get_site("praid"), start, end)
    print(f"Praid: {len(df)} microseisme, "
          f"max M={df['magnitude'].max():.2f}")
