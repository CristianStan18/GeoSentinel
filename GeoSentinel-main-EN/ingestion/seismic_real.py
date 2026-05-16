"""
Microseismicity ingestion FROM REAL DATA — USGS FDSN Earthquake Catalog.

USGS is free and requires no API key. EMSC is preferred for Europe because it
indexes more local events, including some INFP data. If real data is sparse, the
pipeline can fall back to synthetic microseismicity for demo purposes.
"""

from datetime import datetime, timedelta

import pandas as pd
import requests

from config import MineSite


USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
EMSC_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
TIMEOUT = 30


def _build_emsc_params(site: MineSite, start: datetime, end: datetime,
                       radius_km: float, min_magnitude: float) -> dict:
    """EMSC uses different parameter names than USGS.
    - start/end instead of starttime/endtime
    - minmag instead of minmagnitude
    - maxradius in degrees instead of maxradiuskm
    """
    # Conversie km → grade (aprox 111 km pe grad la ecuator)
    radius_deg = radius_km / 111.0
    return {
        "format": "json",
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "lat": site.lat,
        "lon": site.lon,
        "maxradius": round(radius_deg, 3),
        "minmag": min_magnitude,
        "orderby": "time-asc",
    }


def _build_usgs_params(site: MineSite, start: datetime, end: datetime,
                       radius_km: float, min_magnitude: float) -> dict:
    """USGS uses the classic FDSN standard."""
    return {
        "format": "geojson",
        "starttime": start.date().isoformat(),
        "endtime": end.date().isoformat(),
        "latitude": site.lat,
        "longitude": site.lon,
        "maxradiuskm": radius_km,
        "minmagnitude": min_magnitude,
        "orderby": "time-asc",
    }


def fetch_earthquakes_real(
    site: MineSite,
    start: datetime,
    end: datetime,
    *,
    radius_km: float = 50,
    min_magnitude: float = 1.5,
    use_emsc: bool = True,
) -> pd.DataFrame:
    """
    Download real earthquakes around the site.

    use_emsc=True uses EMSC, which is better for Europe and indexes INFP data.
    use_emsc=False uses USGS, which is global but has fewer small events in Romania.
    """
    if use_emsc:
        url = EMSC_URL
        params = _build_emsc_params(site, start, end, radius_km, min_magnitude)
    else:
        url = USGS_URL
        params = _build_usgs_params(site, start, end, radius_km, min_magnitude)

    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        # EMSC poate întoarce 204 (No Content) când nu sunt evenimente — îl tratăm
        if r.status_code == 204:
            return pd.DataFrame()
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        # EMSC poate fi fluctuant — încearcă USGS ca fallback
        if use_emsc:
            print(f"    EMSC failed ({e}), trying USGS...")
            return fetch_earthquakes_real(
                site, start, end,
                radius_km=radius_km,
                min_magnitude=min_magnitude,
                use_emsc=False,
            )
        raise

    events = []
    for feature in data.get("features", []):
        props = feature["properties"]
        geom = feature["geometry"]
        # GeoJSON coords: [lon, lat, depth_km]
        lon, lat, depth_km = geom["coordinates"]
        # EMSC: "time" = string ISO ("2024-12-15T10:30:00.0Z")
        # USGS: "time" = milisecunde de la epoch (int)
        time_field = props.get("time") or props.get("origintime")
        if isinstance(time_field, (int, float)):
            ts = pd.Timestamp(time_field, unit="ms")
        else:
            ts = pd.Timestamp(time_field)
        # Normalizăm la naive UTC: convertim la UTC dacă e tz-aware, apoi strip tz
        # Asta evită problemele de comparare cu Timestamp-uri naive din pipeline
        if ts.tz is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        # EMSC: "mag", USGS: "mag" — comun
        magnitude = props.get("mag") or props.get("magnitude")
        # Place: EMSC = "flynn_region", USGS = "place"
        place = props.get("place") or props.get("flynn_region")
        events.append({
            "datetime": ts,
            "magnitude": magnitude,
            "depth_km": depth_km,
            "place": place,
            "site_id": site.id,
        })

    df = pd.DataFrame(events)
    if not df.empty:
        df = df.dropna(subset=["magnitude"]).sort_values("datetime")
    else:
        # IMPORTANT: returnăm DataFrame cu coloanele așteptate, chiar dacă e gol
        # Altfel pd.read_csv eșuează cu EmptyDataError la pasul de detecție
        df = pd.DataFrame(columns=[
            "datetime", "magnitude", "depth_km", "place", "site_id"
        ])
    return df.reset_index(drop=True)


def fetch_seismic(site: MineSite, start: datetime, end: datetime) -> pd.DataFrame:
    """Hook public — date reale cu fallback la sintetic."""
    try:
        df = fetch_earthquakes_real(site, start, end)
        # Pentru un demo convingător, completăm cu microseismicitate
        # sintetică DOAR pentru site-ul cu eveniment Praid, pentru că
        # USGS/EMSC nu ar avea micro-evenimentele induse local
        if site.id == "praid" and len(df) < 20:
            from ingestion.seismic import generate_synthetic_seismic
            synthetic = generate_synthetic_seismic(
                site, start, end, event_acceleration=True
            )
            # Marcăm sursa pentru transparență
            if not df.empty:
                df["source"] = "EMSC/USGS"
            synthetic["source"] = "modeled (micro-induced)"
            df = pd.concat([df, synthetic], ignore_index=True)
            df = df.sort_values("datetime").reset_index(drop=True)
        else:
            df["source"] = "EMSC/USGS" if not df.empty else "none"

        # Garantăm schema minimă chiar și pentru DataFrame gol
        required_cols = ["datetime", "magnitude", "depth_km", "site_id", "source"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception as e:
        print(f"  ⚠ Eroare seismic real pentru {site.id}: {e}")
        print(f"    Folosesc fallback sintetic.")
        from ingestion.seismic import generate_synthetic_seismic
        df = generate_synthetic_seismic(
            site, start, end,
            event_acceleration=(site.id == "praid"),
        )
        df["source"] = "synthetic (fallback)"
        return df


if __name__ == "__main__":
    from config import get_site
    end = datetime(2025, 6, 1)
    start = end - timedelta(days=180)
    df = fetch_seismic(get_site("praid"), start, end)
    print(f"\nPraid — REAL seismic data (EMSC/USGS):")
    print(f"  Evenimente totale: {len(df)}")
    if not df.empty:
        print(f"  Magnitudine max: {df['magnitude'].max():.2f}")
        if "source" in df.columns:
            print(f"  Surse: {df['source'].value_counts().to_dict()}")
        # Print ultimele evenimente cu coloanele disponibile
        cols = [c for c in ["datetime", "magnitude", "depth_km", "place", "source"]
                if c in df.columns]
        print(f"\n  Ultimele 10 evenimente:")
        print(df.tail(10)[cols])
