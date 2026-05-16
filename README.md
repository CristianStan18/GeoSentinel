# GeoSentinel — Early Warning Intelligence for Critical Infrastructure



## Site-uri monitorizate

**Mine (7):** Praid (eveniment 2025), Ocna Dej, Cacica, Slănic, Târgu Ocna,
Lupeni, Livezeni.

**Tuneluri autostradă (5):** Margina-Holdea T1+T2 (A1), Curtea de Argeș (A1),
Poiana (A1, TBM), Meseș (A3, în proiectare).

## Quickstart

```bash
# 1. Setup
python -m venv .venv
source .venv/bin/activate              # Linux/macOS
# .venv\Scripts\activate.bat               # Windows PowerShell
pip install -r requirements.txt

# 2. Date + detecție
python -m ingestion.real_data
python -m detection.detect

# 3. UI Premium (recomandat)
python -m api.server
# → http://localhost:5000
```

## Comenzi utile

```bash
python -m ingestion.real_data --only mines       # doar mine
python -m ingestion.real_data --only tunnels     # doar tuneluri
python -m ingestion.real_data --end 2025-06-01   # backtest Praid

python -m detection.detect                       # alerte (toate site-urile)
python -m agent.brief_offline praid              # brief operațional (no API)
python -m agent.brief praid                      # brief LLM (necesită cheie)
```

**Frontend (`api/server.py`):** dark cyberpunk, Plotly+Leaflet, recomandat
pentru demo. Rulează pe http://localhost:5000.


## Surse de date

| Sursă | Status |
|---|---|
| Open-Meteo Weather (precipitații real) | ✅ |
| Open-Meteo Air Quality (PM10, CO, NO2 suprafață real) | ✅ |
| EMSC/USGS (catalog seismic real) | ✅ |
| EGMS Sentinel-1 (subsidență InSAR) | 🟡 Hook gata, necesită download manual |
| Aer subteran (CO, NO2, PM10, CH4) | 🟡 Modelat din aer suprafață real + activitate |
| Convergometre + PGV + LiDAR + infiltrație tuneluri | 🟡 Sintetic, hook senzori în prod |

Toate sursele reale au **fallback automat la sintetic** dacă API-ul nu răspunde.

### Semnale monitorizate

**Mine:** subsidență InSAR, microseismicitate, infiltrație apă, CO, praf PM10,
plus CH4 (metan) pentru minele de cărbune.

**Tuneluri:** subsidență suprafață, seismicitate regională, convergență lining,
vibrații dinamice (PGV), umiditate perete, fisuri LiDAR, infiltrație apă, CO, PM10.

## Disclaimer

GeoSentinel e un **decision support system**. Nu înlocuiește decizia inspectorilor
autorizați (ITM, ANRM, CNAIR).
