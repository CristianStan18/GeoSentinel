"""
Orchestrator HIBRID extins: mine + tuneluri.

Run with:
    python -m ingestion.real_data
    python -m ingestion.real_data --end 2025-06-01     # backtest Praid
    python -m ingestion.real_data --only mines         # mines only
    python -m ingestion.real_data --only tunnels       # tunnels only
"""

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from config import SITES, MINES, TUNNELS, is_tunnel, MineSite
from ingestion.insar import fetch_insar
from ingestion.seismic_real import fetch_seismic
from ingestion.hydro_weather_real import fetch_hydro_weather
from ingestion.tunnel_signals import fetch_tunnel_signals
from ingestion.air_quality import fetch_air_quality


DATA_DIR = Path(__file__).parent.parent / "data"
SEISMIC_COLS = ["datetime", "magnitude", "depth_km", "site_id"]


def _save_common_signals(site, insar, seismic, hydro):
    seismic_clean = (
        seismic.drop(columns=["source"], errors="ignore")
        if "source" in seismic.columns else seismic
    )
    if seismic_clean.empty:
        seismic_clean = pd.DataFrame(columns=SEISMIC_COLS)
    seismic_clean = seismic_clean.reindex(columns=SEISMIC_COLS)
    hydro_clean = hydro.drop(columns=["temperature_mean_c"], errors="ignore")

    insar.to_csv(DATA_DIR / f"{site.id}_insar.csv", index=False)
    seismic_clean.to_csv(DATA_DIR / f"{site.id}_seismic.csv", index=False)
    hydro_clean.to_csv(DATA_DIR / f"{site.id}_hydro.csv", index=False)


def _process_mine(site, start, end):
    insar = fetch_insar(site, start, end)
    print(f"    InSAR (synthetic): {len(insar)} measurements")

    seismic = fetch_seismic(site, start, end)
    sources = (
        seismic["source"].value_counts().to_dict()
        if not seismic.empty and "source" in seismic.columns else {}
    )
    print(f"    Seismic: {len(seismic)} evenimente — surse: {sources}")

    hydro = fetch_hydro_weather(site, start, end)
    print(f"    REAL weather: {len(hydro)} zile, "
          f"{hydro['precipitation_mm'].sum():.0f}mm precipitation")

    air = fetch_air_quality(site, start, end)
    ch4_note = (
        f", CH4 max {air['ch4_pct_vol'].max():.2f}%"
        if site.mine_type == "carbune" else ""
    )
    print(f"    Air quality: {len(air)} zile, "
          f"CO max {air['co_mg_m3'].max():.1f} mg/m³{ch4_note}")

    _save_common_signals(site, insar, seismic, hydro)
    air.to_csv(DATA_DIR / f"{site.id}_air.csv", index=False)


def _process_tunnel(site, start, end):
    insar = fetch_insar(site, start, end)
    print(f"    Surface InSAR (synthetic): {len(insar)} measurements")

    seismic = fetch_seismic(site, start, end)
    sources = (
        seismic["source"].value_counts().to_dict()
        if not seismic.empty and "source" in seismic.columns else {}
    )
    print(f"    Seismic regional: {len(seismic)} evenimente — surse: {sources}")

    hydro = fetch_hydro_weather(site, start, end)
    print(f"    REAL weather: {len(hydro)} zile, "
          f"{hydro['precipitation_mm'].sum():.0f}mm precipitation")

    # Trecem precipitațiile reale către semnalele de tunel (pentru infiltrație)
    precip = hydro["precipitation_mm"].to_numpy()
    tunnel_sigs = fetch_tunnel_signals(site, start, end, precipitation_mm=precip)
    print(f"    Lining convergence: {len(tunnel_sigs['convergence'])} measurements")
    print(f"    PGV (vibrations): {len(tunnel_sigs['pgv'])} records")
    print(f"    Humidity + cracks: {len(tunnel_sigs['humidity_cracks'])} scans")
    print(f"    Water inflow: {len(tunnel_sigs['inflow'])} measurements")

    air = fetch_air_quality(site, start, end)
    print(f"    Air quality: {len(air)} zile, "
          f"CO max {air['co_mg_m3'].max():.1f} mg/m³")

    _save_common_signals(site, insar, seismic, hydro)
    tunnel_sigs["convergence"].to_csv(
        DATA_DIR / f"{site.id}_convergence.csv", index=False
    )
    tunnel_sigs["pgv"].to_csv(DATA_DIR / f"{site.id}_pgv.csv", index=False)
    tunnel_sigs["humidity_cracks"].to_csv(
        DATA_DIR / f"{site.id}_humidity.csv", index=False
    )
    tunnel_sigs["inflow"].to_csv(
        DATA_DIR / f"{site.id}_inflow.csv", index=False
    )
    air.to_csv(DATA_DIR / f"{site.id}_air.csv", index=False)


def run(end=None, days_back=180, only=None):
    if end is None:
        # Truncăm la miez de noapte pentru aliniere zilnică
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = today - timedelta(days=1)
    start = end - timedelta(days=days_back)

    DATA_DIR.mkdir(exist_ok=True)
    print(f"Ingestie pentru perioada {start.date()} → {end.date()}\n")

    targets = SITES
    if only == "mines":
        targets = MINES
    elif only == "tunnels":
        targets = TUNNELS

    n_mines = n_tunnels = 0
    for site in targets:
        is_t = is_tunnel(site)
        kind = "TUNNEL" if is_t else "MINE"
        print(f"→ [{kind}] {site.name} ({site.id})")
        if is_t:
            _process_tunnel(site, start, end)
            n_tunnels += 1
        else:
            _process_mine(site, start, end)
            n_mines += 1
        print()

    print(f"✓ Processed: {n_mines} mines, {n_tunnels} tunnels")
    print(f"✓ Data saved to {DATA_DIR}")
    print(f"\nNext step: python -m detection.detect")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="GeoSentinel data ingestion (mines + tunnels)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--only", choices=["mines", "tunnels"], default=None)
    args = parser.parse_args()
    end_dt = datetime.fromisoformat(args.end) if args.end else None
    run(end=end_dt, days_back=args.days, only=args.only)
