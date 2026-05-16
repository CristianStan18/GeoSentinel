"""
Configurarea site-urilor monitorizate: MINE și TUNELURI.

Mine: Salrom (sare), CEH (cărbune)
Tuneluri: CNAIR + constructori (autostradă în execuție)

Sursele datelor pentru tuneluri sunt comunicate publice CNAIR 2024-2026
și documentații tehnice (economedia.ro, arenaconstructiilor.ro).
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
    """Site monitorizat — mină SAU tunel.

    Numele clasei rămâne MineSite pentru compatibilitate cu codul existent,
    dar acoperă acum și infrastructură suprateran/subteran (tuneluri).
    """
    id: str
    name: str
    operator: str
    mine_type: SiteType
    lat: float
    lon: float
    status: SiteStatus
    depth_m: int  # Pentru tuneluri: acoperirea maximă deasupra tunelului
    notes: str = ""
    # Câmpuri opționale pentru tuneluri
    length_m: int = 0
    excavation_progress_pct: float = 0.0


# ─────────────────────────── MINE ───────────────────────────
MINES: list[MineSite] = [
    MineSite(
        id="praid", name="Salina Praid", operator="Salrom",
        mine_type="sare", lat=46.5503, lon=25.1300,
        status="inchisa", depth_m=240,
        notes="Eveniment de referință 2025. Folosit pentru backtest.",
    ),
    MineSite(
        id="ocna_dej", name="Salina Ocna Dej", operator="Salrom",
        mine_type="sare", lat=47.1336, lon=23.8744,
        status="activa", depth_m=220,
    ),
    MineSite(
        id="cacica", name="Salina Cacica", operator="Salrom",
        mine_type="sare", lat=47.6500, lon=25.8833,
        status="activa", depth_m=80,
    ),
    MineSite(
        id="slanic", name="Salina Slănic Prahova", operator="Salrom",
        mine_type="sare", lat=45.2392, lon=25.9419,
        status="activa", depth_m=210,
    ),
    MineSite(
        id="targu_ocna", name="Salina Târgu Ocna", operator="Salrom",
        mine_type="sare", lat=46.2761, lon=26.6181,
        status="activa", depth_m=240,
    ),
    MineSite(
        id="lupeni", name="Mina Lupeni", operator="CEH",
        mine_type="carbune", lat=45.3567, lon=23.2389,
        status="activa", depth_m=600,
        notes="Risc seismic indus + emisii metan.",
    ),
    MineSite(
        id="livezeni", name="Mina Livezeni", operator="CEH",
        mine_type="carbune", lat=45.4083, lon=23.3833,
        status="activa", depth_m=550,
    ),
]

# ─────────────────────────── TUNELURI ───────────────────────────
# Date publice CNAIR 2026
TUNNELS: list[MineSite] = [
    MineSite(
        id="margina_holdea_t2",
        name="Tunel Margina-Holdea T2 (A1)",
        operator="CNAIR / UMB-EuroAsfalt",
        mine_type="tunel_autostrada",
        lat=45.7900, lon=22.3500,
        status="constructie",
        depth_m=80, length_m=1985,
        excavation_progress_pct=56.0,
        notes=(
            "Cel mai lung tunel contractat în România (2x ~1.9km galerii). "
            "Excavație NATM + cut&cover. Termen finalizare: 2026."
        ),
    ),
    MineSite(
        id="margina_holdea_t1",
        name="Tunel Margina-Holdea T1 (A1)",
        operator="CNAIR / UMB-EuroAsfalt",
        mine_type="tunel_autostrada",
        lat=45.7820, lon=22.3380,
        status="constructie",
        depth_m=40, length_m=415,
        excavation_progress_pct=95.0,
        notes="Tunel scurt. Excavații finalizate, torcretare în curs.",
    ),
    MineSite(
        id="poiana_a1",
        name="Tunel Poiana (A1 Sibiu-Pitești)",
        operator="CNAIR / WeBuild",
        mine_type="tunel_autostrada",
        lat=45.5800, lon=24.3700,
        status="constructie",
        depth_m=120, length_m=1700,
        excavation_progress_pct=15.0,
        notes=(
            "Tunel forat cu TBM (Tunnel Boring Machine). "
            "Inițiat ianuarie 2025. Lot 3 A1 Sibiu-Pitești."
        ),
    ),
    MineSite(
        id="curtea_arges",
        name="Tunel Curtea de Argeș (A1)",
        operator="CNAIR / PORR",
        mine_type="tunel_autostrada",
        lat=45.1700, lon=24.6700,
        status="constructie",
        depth_m=90, length_m=1350,
        excavation_progress_pct=70.0,
        notes="Tunel forat complet NATM. Lot 4 A1 Sibiu-Pitești.",
    ),
    MineSite(
        id="meses_a3",
        name="Tunel Meseș (A3)",
        operator="CNAIR / Makyol-Ozaltin",
        mine_type="tunel_autostrada",
        lat=47.1900, lon=23.0100,
        status="proiectare",
        depth_m=150, length_m=2890,
        excavation_progress_pct=0.0,
        notes=(
            "Va deveni cel mai lung tunel autostradă din România (~2.9km). "
            "Contract Makyol-Ozaltin semnat mai 2025. "
            "Monitorizare baseline pre-construcție."
        ),
    ),
]


SITES: list[MineSite] = MINES + TUNNELS


def get_site(site_id: str) -> MineSite:
    for s in SITES:
        if s.id == site_id:
            return s
    raise KeyError(f"Site necunoscut: {site_id}")


def is_tunnel(site: MineSite) -> bool:
    return site.mine_type in ("tunel_autostrada", "tunel_feroviar")


def get_mines() -> list[MineSite]:
    return MINES


def get_tunnels() -> list[MineSite]:
    return TUNNELS
