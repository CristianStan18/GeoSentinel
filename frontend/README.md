# GeoSentinel Frontend

UI dark cyberpunk pentru sistemul de monitorizare mine + tuneluri.

## Cum funcționează

`index.html` se conectează automat la Flask backend (port 5000) prin fetch():

- `GET /api/sites` → harta Leaflet și panoul de detaliu
- `GET /api/timeseries/<site_id>` → graficul Plotly cu 3 subplot-uri
- `GET /api/alerts` → starea alertelor

## Pentru a rula

```bash
# 1. Generează date (la rădăcina proiectului)
python -m ingestion.real_data
python -m detection.detect

# 2. Pornește backend-ul Flask
python -m api.server

# 3. Deschide în browser
http://localhost:5000
```

Frontend-ul rulează de pe același server Flask, deci nu există probleme CORS.

## Personalizare

Designul cyberpunk e tot în `<style>` din `index.html`. Variabilele de
culoare sunt în `:root` (`--accent-mine`, `--accent-tunnel`, etc.).
