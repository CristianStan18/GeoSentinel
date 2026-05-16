"""
Praguri fizice de avertizare per tip de mină.

Aceste valori sunt orientative — la implementare reală se calibrează
per concesiune cu baseline-ul istoric al fiecărui site. Surse:
- Cosma & Enescu, "Seismicitatea indusă în minele românești"
- Cygan & Hardy, "Mechanical behavior of rock salt"
- USGS InSAR guidance pentru subsidență minieră
"""

from typing import Literal


Severity = Literal["info", "watch", "warning", "alarm"]


# Subsidență (mm/lună) — praguri pe magnitudine
INSAR_VELOCITY_THRESHOLDS = {
    "sare":             {"watch": 5,  "warning": 10, "alarm": 20},
    "sare_inchisa":     {"watch": 3,  "warning": 8,  "alarm": 15},
    "carbune":          {"watch": 10, "warning": 20, "alarm": 40},
    "uraniu":           {"watch": 5,  "warning": 10, "alarm": 20},
    "metal_neferos":    {"watch": 5,  "warning": 10, "alarm": 20},
    # Pentru tuneluri: subsidență suprafață deasupra aliniamentului
    "tunel_autostrada": {"watch": 3,  "warning": 6,  "alarm": 12},
    "tunel_feroviar":   {"watch": 3,  "warning": 6,  "alarm": 12},
}

# Microseismicitate — evenimente/zi în fereastră de 7 zile
SEISMIC_RATE_THRESHOLDS = {
    "sare":             {"watch": 1.0,  "warning": 2.5, "alarm": 5.0},
    "sare_inchisa":     {"watch": 0.3,  "warning": 1.0, "alarm": 2.5},
    "carbune":          {"watch": 3.0,  "warning": 6.0, "alarm": 12.0},
    "uraniu":           {"watch": 0.5,  "warning": 1.5, "alarm": 3.0},
    "metal_neferos":    {"watch": 1.0,  "warning": 2.5, "alarm": 5.0},
    # Tuneluri: cutremure regionale care pot afecta lining-ul
    "tunel_autostrada": {"watch": 0.5,  "warning": 1.5, "alarm": 3.0},
    "tunel_feroviar":   {"watch": 0.5,  "warning": 1.5, "alarm": 3.0},
}

# Infiltrație (l/h) — creștere procentuală față de baseline 90 zile
INFILTRATION_PCT_THRESHOLDS = {
    "watch": 25,
    "warning": 50,
    "alarm": 100,
}

# ─── PRAGURI SPECIFICE TUNELURI ───

# Convergență lining (mm/zi, magnitudine — absolută)
# Standard EN 1997 / NATM: -1.0 mm/zi = atenție, -2.0 mm/zi = critic
TUNNEL_CONVERGENCE_THRESHOLDS = {
    "watch": 0.5,    # mm/zi (magnitudine)
    "warning": 1.0,
    "alarm": 2.0,
}

# PGV peak în fereastră 7 zile (mm/s)
# DIN 4150 / structuri sensibile: 5 mm/s prag, 20 mm/s ridicat
TUNNEL_PGV_THRESHOLDS = {
    "watch": 5,
    "warning": 10,
    "alarm": 20,
}

# Umiditate perete (%) — prag absolut
TUNNEL_HUMIDITY_THRESHOLDS = {
    "watch": 65,
    "warning": 75,
    "alarm": 85,
}

# Fisuri noi LiDAR — număr în ultimele 30 zile (delta)
TUNNEL_NEW_CRACKS_THRESHOLDS = {
    "watch": 2,
    "warning": 5,
    "alarm": 10,
}

# Infiltrație apă tunel (l/min) — creștere procentuală vs baseline 60z
TUNNEL_INFLOW_PCT_THRESHOLDS = {
    "watch": 30,
    "warning": 60,
    "alarm": 120,
}

# ─── PRAGURI CALITATE AER (subteran) ───

# CO — monoxid de carbon (mg/m³). OSHA: ~35 mg/m³ limită ocupațională (8h)
AIR_CO_THRESHOLDS = {
    "watch": 15,
    "warning": 25,
    "alarm": 35,
}

# NO2 — dioxid de azot (mg/m³). Limită ocupațională ~5-9 mg/m³
AIR_NO2_THRESHOLDS = {
    "watch": 3,
    "warning": 6,
    "alarm": 9,
}

# PM10 — praf (mg/m³). Limită praf minier ~4-5 mg/m³
AIR_PM10_THRESHOLDS = {
    "watch": 2.5,
    "warning": 4,
    "alarm": 6,
}

# CH4 — metan (% volum). CRITIC pentru cărbune!
# 1% = atenție, 1.5% = oprire lucru (normă minieră), 5% = LEL (explozie)
AIR_CH4_THRESHOLDS = {
    "watch": 0.5,
    "warning": 1.0,
    "alarm": 1.5,
}


def classify(value: float, thresholds: dict) -> Severity:
    """Întoarce nivelul cel mai sever depășit."""
    if value >= thresholds.get("alarm", float("inf")):
        return "alarm"
    if value >= thresholds.get("warning", float("inf")):
        return "warning"
    if value >= thresholds.get("watch", float("inf")):
        return "watch"
    return "info"


# Ordinea de prioritate
SEVERITY_RANK = {"info": 0, "watch": 1, "warning": 2, "alarm": 3}


def max_severity(severities: list[Severity]) -> Severity:
    return max(severities, key=lambda s: SEVERITY_RANK[s])
