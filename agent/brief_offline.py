"""
Generator de briefing OFFLINE — fără apel API.

Folosește template-uri condiționale + datele alertei + baza de cazuri istorice.
Output-ul respectă aceeași structură ca varianta LLM (Situație → Citire fizică →
Precedente → Recomandări → Nivel de încredere).

Pentru demo de hackathon e suficient. Dacă vrei text mai natural, comută înapoi
pe agent.brief (cu Claude API).
"""

from datetime import datetime
import json
from pathlib import Path

from config import get_site, MineSite
from agent.case_database import find_relevant_cases


ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"


# ─── Texte per nivel de severitate ────────────────────────────────────────

SITUATION_OPENERS = {
    "info": (
        "Site-ul **{name}** ({operator}) prezintă un profil de monitorizare "
        "**normal**. Niciun semnal nu a depășit pragurile de avertizare în "
        "fereastra de analiză."
    ),
    "watch": (
        "Site-ul **{name}** ({operator}) este clasificat la nivel **WATCH** — "
        "există unul sau mai multe semnale ușor peste baseline, fără a justifica "
        "încă măsuri operaționale urgente. Se impune monitorizare intensificată."
    ),
    "warning": (
        "Site-ul **{name}** ({operator}) este la nivel **WARNING**. Semnalele "
        "telemetrice indică o deviație semnificativă de la comportamentul "
        "normal, cu posibile implicații pentru stabilitatea structurală."
    ),
    "alarm": (
        "⚠️ Site-ul **{name}** ({operator}) este la nivel **ALARMĂ**. Semnalele "
        "fuzionate prezintă un tipar consistent cu condiții pre-eveniment "
        "documentate în alte cazuri de prăbușire minieră. Se recomandă "
        "intervenție imediată din partea inspectorilor autorizați."
    ),
}

CONFIDENCE_RATIONALE = {
    "info": ("low", "Toate semnalele sunt în limite normale. Sistemul nu are "
             "elemente care să sugereze risc imediat."),
    "watch": ("medium", "Un singur semnal a depășit pragul; cauza poate fi "
              "sezonalitate sau zgomot. Necesită confirmare în următoarele 7-14 zile."),
    "warning": ("medium-high", "Două sau mai multe semnale converg, sau un "
                "semnal este sever. Confirmarea independentă prin măsurători "
                "manuale este recomandată înainte de acțiune operațională majoră."),
    "alarm": ("high", "Trei semnale convergente (subsidență + microseismicitate + "
              "infiltrație) replică tiparul evenimentelor istorice catastrofale. "
              "Probabilitatea unui eveniment major în următoarele 30-90 zile este "
              "substanțial mai mare decât baseline-ul."),
}


# ─── Citire fizică (mecanism) per tip de mină + semnale ───────────────────

def _physical_reading(site: MineSite, signals: list[dict]) -> str:
    """Generează interpretarea fizică în funcție de tip + semnale active."""
    sev_map = {s["name"]: s["severity"] for s in signals}
    val_map = {s["name"]: s["value"] for s in signals}

    insar_sev = sev_map.get("Subsidență InSAR", "info")
    seis_sev = sev_map.get("Microseismicitate", "info")
    infl_sev = sev_map.get("Infiltrație de apă", "info")

    # Semnale active = orice peste info
    active = [n for n, s in sev_map.items() if s != "info"]

    if not active:
        return (
            "Toate cele trei surse de date (deformare InSAR, microseismicitate, "
            "regim hidrologic) prezintă variații consistente cu zgomotul de fond. "
            "Nu există indicii de procese geomecanice anormale în desfășurare."
        )

    # Cazuri speciale: combinații semnificative
    lines = []

    if site.mine_type in ("sare", "sare_inchisa"):
        if infl_sev in ("warning", "alarm") and seis_sev in ("warning", "alarm"):
            lines.append(
                "**Combinație critică pentru mine de sare:** Creșterea infiltrației "
                f"({val_map.get('Infiltrație de apă', 'N/A'):.0f}% peste baseline) "
                "combinată cu microseismicitate elevată "
                f"({val_map.get('Microseismicitate', 'N/A'):.1f} ev/zi) sugerează "
                "dizolvare activă a sării însoțită de redistribuire tensională. "
                "Mecanismul fizic plauzibil: apa dulce infiltrată dizolvă pilierii "
                "de susținere, generând micro-fracturi detectabile seismic, până "
                "la cedare structurală."
            )
        elif infl_sev in ("warning", "alarm"):
            lines.append(
                f"Infiltrația de apă a crescut cu {val_map.get('Infiltrație de apă', 0):.0f}% "
                "față de baseline. În minele de sare, apa dulce este factorul de risc "
                "dominant — dizolvă sarea și compromite integritatea pilierilor. "
                "Sursa creșterii trebuie identificată urgent (precipitații recente, "
                "fisură nouă, pierdere conductă de drenaj)."
            )
        elif insar_sev in ("warning", "alarm"):
            lines.append(
                f"Rata de subsidență ({val_map.get('Subsidență InSAR', 0):.1f} mm/lună) "
                "este peste pragul normal pentru o salină activă. Posibile cauze: "
                "convergență accelerată a cavităților, cedare progresivă a unui pilier "
                "sau extragere accelerată fără refacerea echilibrului."
            )

    elif site.mine_type == "carbune":
        if seis_sev in ("warning", "alarm"):
            lines.append(
                f"Rata microseismică ({val_map.get('Microseismicitate', 0):.1f} ev/zi) "
                "este elevată chiar și pentru o mină de cărbune activă. La adâncimi "
                f"de {site.depth_m}m, microseismicitatea elevată poate fi precursor "
                "al unei rupturi de tavan sau a unui rockburst. Verificarea "
                "concentrațiilor de metan asociate e prioritară."
            )
        if insar_sev in ("warning", "alarm"):
            lines.append(
                "Subsidența accelerată la suprafață indică convergență subterană "
                "rapidă — verificați progresia frontului de exploatare și starea "
                "pilierilor de protecție."
            )

    if not lines:
        # Fallback generic
        signal_list = ", ".join(
            f"{n} ({sev_map[n]})" for n in active
        )
        lines.append(
            f"Semnalele active sunt: {signal_list}. Combinația lor depășește "
            f"baseline-ul site-ului, deși nu corespunde unui tipar clasic. "
            f"Recomandăm corelarea cu inspecția vizuală locală."
        )

    return "\n\n".join(lines)


def _precedents_section(cases: list[dict]) -> str:
    if not cases:
        return ("Nu am identificat cazuri istorice cu match strâns în baza de date. "
                "Recomandăm consultarea literaturii specializate ANRM/ITM.")
    parts = []
    for c in cases:
        precursori = "\n".join(f"  - {p}" for p in c["precursors"])
        lectii = "\n".join(f"  - {l}" for l in c["lessons"])
        parts.append(
            f"**{c['name']}** ({c['country']}) — *{c['outcome']}*\n\n"
            f"Precursori observați:\n{precursori}\n\n"
            f"Cauză rădăcină: {c['root_cause']}\n\n"
            f"Lecții transferabile:\n{lectii}"
        )
    return "\n\n---\n\n".join(parts)


def _recommendations(severity: str, site: MineSite, signals: list[dict]) -> str:
    sev_map = {s["name"]: s["severity"] for s in signals}

    if severity == "info":
        return (
            "1. **Continuare monitorizare de rutină** — recolectare date la "
            "intervalele standard (InSAR 12 zile, hidro zilnic, seismic continuu).\n"
            "2. **Revizuire calibrare praguri** — analizați dacă baseline-ul "
            "actual reflectă încă realitatea operațională a site-ului."
        )

    if severity == "watch":
        return (
            "1. **Intensificare monitorizare** — verificare zilnică (nu săptămânală) "
            "a semnalelor active.\n"
            "2. **Inspecție vizuală locală** — echipă tehnică să verifice zonele "
            "corespunzătoare semnalelor anormale (fisuri noi, infiltrații vizibile, "
            "deformări).\n"
            "3. **Notificare internă operator** — informare conducere "
            f"{site.operator} pentru pregătire în caz de escaladare."
        )

    if severity == "warning":
        lines = [
            "1. **Măsurători manuale suplimentare** — totalstații, extensometre, "
            "piezometre suplimentare în zonele afectate.",
            "2. **Restricționare acces** — limitare a personalului în zonele "
            "cu semnale active la strict necesar.",
            "3. **Plan de evacuare actualizat** — verificare rute, comunicații, "
            "puncte de adunare.",
            f"4. **Notificare ANRM și ITM** — raportare formală a stării "
            f"site-ului {site.name}.",
        ]
        if sev_map.get("Infiltrație de apă") in ("warning", "alarm") and \
           site.mine_type in ("sare", "sare_inchisa"):
            lines.append(
                "5. **Investigare sursă infiltrație** — trasare cu coloranți, "
                "verificare conducte hidrotehnice, examinare cursuri de apă "
                "din apropiere."
            )
        return "\n".join(lines)

    # alarm
    lines = [
        "1. **🚨 EVACUARE PERSONAL** din zonele afectate ale minei — prioritate absolută.",
        "2. **Oprire imediată a operațiunilor de excavare** în site.",
        f"3. **Notificare urgentă ANRM, ITM și ISU** — site-ul {site.name} "
        "trebuie raportat ca având tipar pre-eveniment.",
        "4. **Activare echipă de criză** la nivelul operatorului "
        f"({site.operator}).",
        "5. **Restricționare acces public** în zonele de potențială subsidență "
        "la suprafață (raza de minim 500m).",
        "6. **Comunicare publică pregătită** — autoritățile locale să fie "
        "informate pentru eventualitatea unei evacuări extinse.",
        "7. **Măsurători intensive de confirmare** — InSAR de înaltă rezoluție, "
        "rețea seismică densificată, monitorizare hidrologică continuă.",
    ]
    return "\n".join(lines)


# ─── Public API ───────────────────────────────────────────────────────────

def generate_brief_offline(site_id: str) -> str:
    """Generează briefing complet fără apel API."""
    with open(DATA_DIR / "alerts.json", encoding="utf-8") as f:
        alerts = json.load(f)

    alert = next((a for a in alerts if a["site_id"] == site_id), None)
    if not alert:
        raise ValueError(f"Nicio alertă pentru {site_id}")

    site = get_site(site_id)
    severity = alert["overall_severity"]
    signal_names = [s["name"] for s in alert["signals"]]
    cases = find_relevant_cases(site.mine_type, signal_names, top_k=2)

    # Construim brief-ul
    sit = SITUATION_OPENERS[severity].format(
        name=site.name, operator=site.operator
    )

    # Adăugăm metrici-cheie la situație
    metrics_lines = []
    for s in alert["signals"]:
        if s["severity"] != "info":
            metrics_lines.append(
                f"  - {s['name']}: **{s['value']} {s['unit']}** ({s['severity']})"
            )
    if metrics_lines:
        sit += "\n\nMetrici-cheie:\n" + "\n".join(metrics_lines)
    sit += f"\n\nScor anomalie ML (Isolation Forest): **{alert['ml_anomaly_score']:.2f}** / 1.00"

    physical = _physical_reading(site, alert["signals"])
    precedents = _precedents_section(cases)
    recommendations = _recommendations(severity, site, alert["signals"])
    conf_level, conf_text = CONFIDENCE_RATIONALE[severity]

    brief = f"""## 1. Situație

{sit}

## 2. Citire fizică (mecanism plauzibil)

{physical}

## 3. Precedente istorice relevante

{precedents}

## 4. Recomandări operaționale

{recommendations}

## 5. Nivel de încredere

**{conf_level.upper()}** — {conf_text}

---

*Brief generat automat de MineGuard pe baza datelor telemetrice la {alert['as_of']}. Acest document este suport decizional și nu înlocuiește analiza inspectorilor autorizați.*
"""
    return brief


def main():
    import sys
    site_id = sys.argv[1] if len(sys.argv) > 1 else "praid"
    print(f"\n{'='*70}\n  Brief MineGuard (offline) pentru: {site_id}\n{'='*70}\n")
    brief = generate_brief_offline(site_id)
    print(brief)
    out = DATA_DIR / f"brief_{site_id}.md"
    out.write_text(brief, encoding="utf-8")
    print(f"\n✓ Salvat în {out}")


if __name__ == "__main__":
    main()
