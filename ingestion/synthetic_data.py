"""
Orchestrator: rulează toate sursele și salvează în data/.
Rulează cu: python -m ingestion.synthetic_data
"""

from datetime import datetime, timedelta
from pathlib import Path

from config import SITES
from ingestion.insar import fetch_insar
from ingestion.seismic import fetch_seismic
from ingestion.hydro_weather import fetch_hydro_weather


DATA_DIR = Path(__file__).parent.parent / "data"


def run(end: datetime | None = None, days_back: int = 180) -> None:
    if end is None:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = today - timedelta(days=1)
    start = end - timedelta(days=days_back)

    DATA_DIR.mkdir(exist_ok=True)

    for site in SITES:
        print(f"→ {site.name} ({site.id})")
        insar = fetch_insar(site, start, end)
        seismic = fetch_seismic(site, start, end)
        hydro = fetch_hydro_weather(site, start, end)

        insar.to_csv(DATA_DIR / f"{site.id}_insar.csv", index=False)
        seismic.to_csv(DATA_DIR / f"{site.id}_seismic.csv", index=False)
        hydro.to_csv(DATA_DIR / f"{site.id}_hydro.csv", index=False)

    print(f"\n✓ Date salvate în {DATA_DIR}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generator date sintetice MineGuard")
    parser.add_argument("--end", type=str, default=None,
                        help="Data finală (YYYY-MM-DD). Default: ieri.")
    parser.add_argument("--days", type=int, default=180,
                        help="Zile înapoi. Default: 180.")
    args = parser.parse_args()
    end_dt = datetime.fromisoformat(args.end) if args.end else None
    run(end=end_dt, days_back=args.days)
