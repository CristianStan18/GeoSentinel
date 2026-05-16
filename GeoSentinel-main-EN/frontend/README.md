# GeoSentinel Frontend

Dark cyberpunk UI for the mine and tunnel monitoring system.

## How it works

`index.html` connects automatically to the Flask backend on port 5000 using `fetch()`:

- `GET /api/sites` → Leaflet map and detail panel
- `GET /api/timeseries/<site_id>` → Plotly chart with multiple signal panels
- `GET /api/alerts` → current alert status

## How to run

```bash
# 1. Generate data from the project root
python -m ingestion.real_data
python -m detection.detect

# 2. Start the Flask backend
python -m api.server

# 3. Open in browser
http://localhost:5000
```

The frontend is served from the same Flask server, so there are no CORS issues.

## Customization

The cyberpunk design is contained in the `<style>` section of `index.html`. Color variables are defined in `:root` (`--accent-mine`, `--accent-tunnel`, etc.).
