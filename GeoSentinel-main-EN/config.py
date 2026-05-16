"""
Configuration for monitored sites: MINES and TUNNELS.

Mines: Salrom (salt), CEH (coal)
Tunnels: CNAIR + contractors (motorway under construction)

Tunnel data sources are CNAIR public communications from 2024-2026
and technical documentation (economedia.ro, arenaconstructiilor.ro).
"""

from dataclasses import dataclass
from typing import Literal

SiteType = Literal[
    "sare", "carbune", "uraniu", "metal_neferos", "sare_inchisa",
    "tunel_autostrada", "tunel_feroviar",
]

SiteStatus = Literal[
    "activa", "inchisa", "conservare",
    "constructie", "proiectare", "operare",
]


@dataclass(frozen=True)
class MineSite:
    """Monitored site — mine OR tunnel.

    The class name remains MineSite for compatibility with existing code,
    but it now also covers surface/underground infrastructure such as tunnels.
    """
    id: str
    name: str
    operator: str
    mine_type: SiteType
    lat: float
    lon: float
    status: SiteStatus
    depth_m: int  # For tunnels: maximum cover above the tunnel
    notes: str = ""
    # Optional fields for tunnels
    length_m: int = 0
    excavation_progress_pct: float = 0.0


# ─────────────────────────── MINES ───────────────────────────
MINES: list[MineSite] = [
    MineSite(
        id="praid", name="Praid Salt Mine", operator="Salrom",
        mine_type="sare", lat=46.5503, lon=25.1300,
        status="inchisa", depth_m=240,
        notes="2025 reference event. Used for backtesting.",
    ),
    MineSite(
        id="ocna_dej", name="Ocna Dej Salt Mine", operator="Salrom",
        mine_type="sare", lat=47.1336, lon=23.8744,
        status="activa", depth_m=220,
    ),
    MineSite(
        id="cacica", name="Cacica Salt Mine", operator="Salrom",
        mine_type="sare", lat=47.6500, lon=25.8833,
        status="activa", depth_m=80,
    ),
    MineSite(
        id="slanic", name="Slanic Prahova Salt Mine", operator="Salrom",
        mine_type="sare", lat=45.2392, lon=25.9419,
        status="activa", depth_m=210,
    ),
    MineSite(
        id="targu_ocna", name="Targu Ocna Salt Mine", operator="Salrom",
        mine_type="sare", lat=46.2761, lon=26.6181,
        status="activa", depth_m=240,
    ),
    MineSite(
        id="lupeni", name="Lupeni Mine", operator="CEH",
        mine_type="carbune", lat=45.3567, lon=23.2389,
        status="activa", depth_m=600,
        notes="Induced seismic risk + methane emissions.",
    ),
    MineSite(
        id="livezeni", name="Livezeni Mine", operator="CEH",
        mine_type="carbune", lat=45.4083, lon=23.3833,
        status="activa", depth_m=550,
    ),
]

# ─────────────────────────── TUNNELS ───────────────────────────
# CNAIR public data 2026
TUNNELS: list[MineSite] = [
    MineSite(
        id="margina_holdea_t2",
        name="Margina-Holdea T2 Tunnel (A1)",
        operator="CNAIR / UMB-EuroAsfalt",
        mine_type="tunel_autostrada",
        lat=45.7900, lon=22.3500,
        status="constructie",
        depth_m=80, length_m=1985,
        excavation_progress_pct=56.0,
        notes=(
            "The longest contracted tunnel in Romania (2x ~1.9km galleries). "
            "NATM excavation + cut-and-cover. Completion target: 2026."
        ),
    ),
    MineSite(
        id="margina_holdea_t1",
        name="Margina-Holdea T1 Tunnel (A1)",
        operator="CNAIR / UMB-EuroAsfalt",
        mine_type="tunel_autostrada",
        lat=45.7820, lon=22.3380,
        status="constructie",
        depth_m=40, length_m=415,
        excavation_progress_pct=95.0,
        notes="Short tunnel. Excavation completed, shotcreting in progress.",
    ),
    MineSite(
        id="poiana_a1",
        name="Poiana Tunnel (A1 Sibiu-Pitesti)",
        operator="CNAIR / WeBuild",
        mine_type="tunel_autostrada",
        lat=45.5800, lon=24.3700,
        status="constructie",
        depth_m=120, length_m=1700,
        excavation_progress_pct=15.0,
        notes=(
            "Tunnel bored with TBM (Tunnel Boring Machine). "
            "Started in January 2025. Lot 3 A1 Sibiu-Pitesti."
        ),
    ),
    MineSite(
        id="curtea_arges",
        name="Curtea de Arges Tunnel (A1)",
        operator="CNAIR / PORR",
        mine_type="tunel_autostrada",
        lat=45.1700, lon=24.6700,
        status="constructie",
        depth_m=90, length_m=1350,
        excavation_progress_pct=70.0,
        notes="Fully NATM-bored tunnel. Lot 4 A1 Sibiu-Pitesti.",
    ),
    MineSite(
        id="meses_a3",
        name="Meses Tunnel (A3)",
        operator="CNAIR / Makyol-Ozaltin",
        mine_type="tunel_autostrada",
        lat=47.1900, lon=23.0100,
        status="proiectare",
        depth_m=150, length_m=2890,
        excavation_progress_pct=0.0,
        notes=(
            "Will become the longest motorway tunnel in Romania (~2.9km). "
            "Makyol-Ozaltin contract signed in May 2025. "
            "Pre-construction baseline monitoring."
        ),
    ),
]


SITES: list[MineSite] = MINES + TUNNELS


def get_site(site_id: str) -> MineSite:
    for s in SITES:
        if s.id == site_id:
            return s
    raise KeyError(f"Unknown site: {site_id}")


def is_tunnel(site: MineSite) -> bool:
    return site.mine_type in ("tunel_autostrada", "tunel_feroviar")


def get_mines() -> list[MineSite]:
    return MINES


def get_tunnels() -> list[MineSite]:
    return TUNNELS
