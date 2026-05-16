# GeoSentinel — Early Warning Intelligence for Critical Infrastructure



## Monitored Sites

**Mines (7):** Praid (2025 event), Ocna Dej, Cacica, Slanic, Targu Ocna,
Lupeni, Livezeni.

**Highway tunnels (5):** Margina-Holdea T1+T2 (A1), Curtea de Arges (A1),
Poiana (A1, TBM), Meses (A3, under design).

## Quickstart

```bash
# 1. Setup
python -m venv .venv
source .venv/bin/activate              # Linux/macOS
# .venv\Scripts\activate.bat               # Windows PowerShell
pip install -r requirements.txt

# 2. Data + detection
python -m ingestion.real_data
python -m detection.detect

# 3. Premium UI (recommended)
python -m api.server
# → http://localhost:5000
```

## Useful commands

```bash
python -m ingestion.real_data --only mines       # mines only
python -m ingestion.real_data --only tunnels     # tunnels only
python -m ingestion.real_data --end 2025-06-01   # Praid backtest

python -m detection.detect                       # alerts (all sites)
python -m agent.brief_offline praid              # operational brief (no API)
python -m agent.brief praid                      # LLM brief (requires key)
```

**Frontend (`api/server.py`):** dark cyberpunk, Plotly+Leaflet, recommended
for the demo. Runs at http://localhost:5000.


## Data Sources

| Source | Status |
|---|---|
| Open-Meteo Weather (real precipitation) | ✅ |
| Open-Meteo Air Quality (real surface PM10, CO, NO2) | ✅ |
| EMSC/USGS (real seismic catalog) | ✅ |
| EGMS Sentinel-1 (InSAR subsidence) | 🟡 Hook ready, requires manual download |
| Underground air (CO, NO2, PM10, CH4) | 🟡 Modeled from real surface air + activity |
| Convergometers + PGV + LiDAR + tunnel infiltration | 🟡 Synthetic, production sensor hook |

All real sources have an **automatic synthetic fallback** if the API does not respond.

### Monitored Signals

**Mines:** InSAR subsidence, microseismicity, water infiltration, CO, PM10 dust,
plus CH4 (methane) for coal mines.

**Tunnels:** surface subsidence, regional seismicity, lining convergence,
dynamic vibrations (PGV), wall humidity, LiDAR cracks, water infiltration, CO, PM10.

## Disclaimer

GeoSentinel is a **decision support system**. It does not replace decisions made by
authorized inspectors (ITM, ANRM, CNAIR).
