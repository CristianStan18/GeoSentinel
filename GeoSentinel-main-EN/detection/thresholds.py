"""
Physical warning thresholds by site type.

These values are indicative. In a real deployment they should be calibrated per
concession using each site’s historical baseline. Sources:
- Cosma & Enescu, induced seismicity in Romanian mines
- Cygan & Hardy, "Mechanical behavior of rock salt"
- USGS InSAR guidance for mining subsidence
"""

from typing import Literal


Severity = Literal["info", "watch", "warning", "alarm"]


# Subsidence (mm/month) — thresholds by magnitude
INSAR_VELOCITY_THRESHOLDS = {
    "sare":             {"watch": 5,  "warning": 10, "alarm": 20},
    "sare_inchisa":     {"watch": 3,  "warning": 8,  "alarm": 15},
    "carbune":          {"watch": 10, "warning": 20, "alarm": 40},
    "uraniu":           {"watch": 5,  "warning": 10, "alarm": 20},
    "metal_neferos":    {"watch": 5,  "warning": 10, "alarm": 20},
    # Tunnels: surface subsidence above the alignment
    "tunel_autostrada": {"watch": 3,  "warning": 6,  "alarm": 12},
    "tunel_feroviar":   {"watch": 3,  "warning": 6,  "alarm": 12},
}

# Microseismicity — events/day in a 7-day window
SEISMIC_RATE_THRESHOLDS = {
    "sare":             {"watch": 1.0,  "warning": 2.5, "alarm": 5.0},
    "sare_inchisa":     {"watch": 0.3,  "warning": 1.0, "alarm": 2.5},
    "carbune":          {"watch": 3.0,  "warning": 6.0, "alarm": 12.0},
    "uraniu":           {"watch": 0.5,  "warning": 1.5, "alarm": 3.0},
    "metal_neferos":    {"watch": 1.0,  "warning": 2.5, "alarm": 5.0},
    # Tunnels: regional earthquakes that may affect the lining
    "tunel_autostrada": {"watch": 0.5,  "warning": 1.5, "alarm": 3.0},
    "tunel_feroviar":   {"watch": 0.5,  "warning": 1.5, "alarm": 3.0},
}

# Infiltration (l/h) — percentage increase versus 90-day baseline
INFILTRATION_PCT_THRESHOLDS = {
    "watch": 25,
    "warning": 50,
    "alarm": 100,
}

# ─── TUNNEL-SPECIFIC THRESHOLDS ───

# Lining convergence (mm/day, absolute magnitude)
# Standard EN 1997 / NATM: -1.0 mm/day = attention, -2.0 mm/day = critical
TUNNEL_CONVERGENCE_THRESHOLDS = {
    "watch": 0.5,    # mm/zi (magnitudine)
    "warning": 1.0,
    "alarm": 2.0,
}

# Peak PGV in a 7-day window (mm/s)
# DIN 4150 / sensitive structures: 5 mm/s threshold, 20 mm/s high
TUNNEL_PGV_THRESHOLDS = {
    "watch": 5,
    "warning": 10,
    "alarm": 20,
}

# Wall humidity (%) — absolute threshold
TUNNEL_HUMIDITY_THRESHOLDS = {
    "watch": 65,
    "warning": 75,
    "alarm": 85,
}

# New LiDAR cracks — count in the last 30 days (delta)
TUNNEL_NEW_CRACKS_THRESHOLDS = {
    "watch": 2,
    "warning": 5,
    "alarm": 10,
}

# Tunnel water inflow (l/min) — percentage increase vs 60-day baseline
TUNNEL_INFLOW_PCT_THRESHOLDS = {
    "watch": 30,
    "warning": 60,
    "alarm": 120,
}

# ─── AIR-QUALITY THRESHOLDS (underground) ───

# CO — carbon monoxide (mg/m³). OSHA: ~35 mg/m³ occupational limit (8h)
AIR_CO_THRESHOLDS = {
    "watch": 15,
    "warning": 25,
    "alarm": 35,
}

# NO2 — nitrogen dioxide (mg/m³). Occupational limit ~5-9 mg/m³
AIR_NO2_THRESHOLDS = {
    "watch": 3,
    "warning": 6,
    "alarm": 9,
}

# PM10 — dust (mg/m³). Mining dust limit ~4-5 mg/m³
AIR_PM10_THRESHOLDS = {
    "watch": 2.5,
    "warning": 4,
    "alarm": 6,
}

# CH4 — methane (% volume). CRITICAL for coal!
# 1% = attention, 1.5% = stop work (mining norm), 5% = LEL (explosion)
AIR_CH4_THRESHOLDS = {
    "watch": 0.5,
    "warning": 1.0,
    "alarm": 1.5,
}


def classify(value: float, thresholds: dict) -> Severity:
    """Return the most severe exceeded level."""
    if value >= thresholds.get("alarm", float("inf")):
        return "alarm"
    if value >= thresholds.get("warning", float("inf")):
        return "warning"
    if value >= thresholds.get("watch", float("inf")):
        return "watch"
    return "info"


# Priority order
SEVERITY_RANK = {"info": 0, "watch": 1, "warning": 2, "alarm": 3}


def max_severity(severities: list[Severity]) -> Severity:
    return max(severities, key=lambda s: SEVERITY_RANK[s])
