"""
Offline briefing generator — no API call required.

It uses conditional templates, alert data and the historical case database.
The output follows the same structure as the LLM variant: Situation → Physical
reading → Precedents → Recommendations → Confidence level.

For a hackathon demo this is enough. For more natural text, switch back to
agent.brief with the Claude API.
"""

import json
from pathlib import Path

from config import get_site, MineSite
from agent.case_database import find_relevant_cases


ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"


SITUATION_OPENERS = {
    "info": (
        "Site **{name}** ({operator}) shows a **normal** monitoring profile. "
        "No signal exceeded warning thresholds during the analysis window."
    ),
    "watch": (
        "Site **{name}** ({operator}) is classified as **WATCH** — one or more "
        "signals are slightly above baseline, without yet justifying urgent "
        "operational measures. Increased monitoring is required."
    ),
    "warning": (
        "Site **{name}** ({operator}) is at **WARNING** level. Telemetry indicates "
        "a significant deviation from normal behaviour, with possible implications "
        "for structural stability."
    ),
    "alarm": (
        "⚠️ Site **{name}** ({operator}) is at **ALARM** level. The fused signals "
        "show a pattern consistent with pre-event conditions documented in other "
        "mine-collapse cases. Immediate intervention by authorized inspectors is "
        "recommended."
    ),
}

CONFIDENCE_RATIONALE = {
    "info": (
        "low",
        "All signals are within normal limits. The system has no evidence suggesting immediate risk.",
    ),
    "watch": (
        "medium",
        "A single signal exceeded its threshold; seasonality or noise may explain it. Confirmation is needed within the next 7-14 days.",
    ),
    "warning": (
        "medium-high",
        "Two or more signals converge, or one signal is severe. Independent confirmation through manual measurements is recommended before major operational action.",
    ),
    "alarm": (
        "high",
        "Three convergent signals (subsidence + microseismicity + infiltration) replicate the pattern seen in historical catastrophic events. The probability of a major event in the next 30-90 days is substantially above baseline.",
    ),
}


def _physical_reading(site: MineSite, signals: list[dict]) -> str:
    """Generate the physical interpretation based on site type and active signals."""
    sev_map = {s["name"]: s["severity"] for s in signals}
    val_map = {s["name"]: s["value"] for s in signals}

    insar_sev = sev_map.get("InSAR subsidence", "info")
    seis_sev = sev_map.get("Microseismicity", "info")
    infl_sev = sev_map.get("Water infiltration", "info")

    active = [n for n, s in sev_map.items() if s != "info"]

    if not active:
        return (
            "All three data sources (InSAR deformation, microseismicity and the "
            "hydrological regime) show variations consistent with background noise. "
            "There is no evidence of abnormal geomechanical processes in progress."
        )

    lines = []

    if site.mine_type in ("sare", "sare_inchisa"):
        if infl_sev in ("warning", "alarm") and seis_sev in ("warning", "alarm"):
            lines.append(
                "**Critical combination for salt mines:** The increase in infiltration "
                f"({val_map.get('Water infiltration', 0):.0f}% above baseline) combined "
                f"with elevated microseismicity ({val_map.get('Microseismicity', 0):.1f} events/day) "
                "suggests active salt dissolution accompanied by stress redistribution. "
                "The plausible physical mechanism is freshwater dissolving support pillars, "
                "generating seismically detectable microfractures until structural failure."
            )
        elif infl_sev in ("warning", "alarm"):
            lines.append(
                f"Water infiltration increased by {val_map.get('Water infiltration', 0):.0f}% "
                "against baseline. In salt mines, freshwater is the dominant risk factor — "
                "it dissolves salt and compromises pillar integrity. The source of the increase "
                "must be identified urgently (recent precipitation, new crack or drainage-pipe failure)."
            )
        elif insar_sev in ("warning", "alarm"):
            lines.append(
                f"The subsidence rate ({val_map.get('InSAR subsidence', 0):.1f} mm/month) "
                "is above the normal threshold for an active salt mine. Possible causes include "
                "accelerated cavity convergence, progressive pillar failure or accelerated extraction "
                "without restoring equilibrium."
            )

    elif site.mine_type == "carbune":
        if seis_sev in ("warning", "alarm"):
            lines.append(
                f"The microseismic rate ({val_map.get('Microseismicity', 0):.1f} events/day) "
                "is elevated even for an active coal mine. At depths of "
                f"{site.depth_m}m, elevated microseismicity can precede a roof failure or rockburst. "
                "Checking associated methane concentrations is a priority."
            )
        if insar_sev in ("warning", "alarm"):
            lines.append(
                "Accelerated surface subsidence indicates rapid underground convergence — "
                "check the progression of the working face and the condition of support pillars."
            )

    if not lines:
        signal_list = ", ".join(f"{n} ({sev_map[n]})" for n in active)
        lines.append(
            f"The active signals are: {signal_list}. Their combination exceeds the site baseline, "
            "although it does not match a classic pattern. Correlation with a local visual inspection is recommended."
        )

    return "\n\n".join(lines)


def _precedents_section(cases: list[dict]) -> str:
    if not cases:
        return (
            "No historical cases with a close match were identified in the database. "
            "Consulting specialized ANRM/ITM literature is recommended."
        )
    parts = []
    for c in cases:
        precursors = "\n".join(f"  - {p}" for p in c["precursors"])
        lessons = "\n".join(f"  - {l}" for l in c["lessons"])
        parts.append(
            f"**{c['name']}** ({c['country']}) — *{c['outcome']}*\n\n"
            f"Observed precursors:\n{precursors}\n\n"
            f"Root cause: {c['root_cause']}\n\n"
            f"Transferable lessons:\n{lessons}"
        )
    return "\n\n---\n\n".join(parts)


def _recommendations(severity: str, site: MineSite, signals: list[dict]) -> str:
    sev_map = {s["name"]: s["severity"] for s in signals}

    if severity == "info":
        return (
            "1. **Continue routine monitoring** — collect data at standard intervals "
            "(InSAR every 12 days, hydro daily, seismic continuously).\n"
            "2. **Review threshold calibration** — verify that the current baseline still reflects the site’s operational reality."
        )

    if severity == "watch":
        return (
            "1. **Increase monitoring intensity** — check active signals daily rather than weekly.\n"
            "2. **Local visual inspection** — a technical team should verify the areas corresponding to abnormal signals "
            "(new cracks, visible infiltration, deformation).\n"
            f"3. **Internal operator notification** — inform {site.operator} management to prepare for possible escalation."
        )

    if severity == "warning":
        lines = [
            "1. **Additional manual measurements** — total stations, extensometers and additional piezometers in affected areas.",
            "2. **Access restriction** — limit personnel in active-signal areas to strictly necessary staff.",
            "3. **Updated evacuation plan** — verify routes, communications and assembly points.",
            f"4. **Notify ANRM and ITM** — formally report the status of site {site.name}.",
        ]
        if sev_map.get("Water infiltration") in ("warning", "alarm") and site.mine_type in ("sare", "sare_inchisa"):
            lines.append(
                "5. **Investigate infiltration source** — dye tracing, hydraulic-pipe checks and examination of nearby watercourses."
            )
        return "\n".join(lines)

    lines = [
        "1. **🚨 EVACUATE PERSONNEL** from affected mine areas — absolute priority.",
        "2. **Immediately stop excavation operations** on site.",
        f"3. **Urgently notify ANRM, ITM and ISU** — site {site.name} must be reported as showing a pre-event pattern.",
        f"4. **Activate the operator crisis team** ({site.operator}).",
        "5. **Restrict public access** in potential surface-subsidence areas with a minimum 500m radius.",
        "6. **Prepare public communication** — local authorities should be informed in case broader evacuation becomes necessary.",
        "7. **Intensive confirmation measurements** — high-resolution InSAR, denser seismic network and continuous hydrological monitoring.",
    ]
    return "\n".join(lines)


def generate_brief_offline(site_id: str) -> str:
    """Generate a full briefing without an API call."""
    with open(DATA_DIR / "alerts.json", encoding="utf-8") as f:
        alerts = json.load(f)

    alert = next((a for a in alerts if a["site_id"] == site_id), None)
    if not alert:
        raise ValueError(f"No alert found for {site_id}")

    site = get_site(site_id)
    severity = alert["overall_severity"]
    signal_names = [s["name"] for s in alert["signals"]]
    cases = find_relevant_cases(site.mine_type, signal_names, top_k=2)

    situation = SITUATION_OPENERS[severity].format(name=site.name, operator=site.operator)

    metrics_lines = []
    for s in alert["signals"]:
        if s["severity"] != "info":
            metrics_lines.append(f"  - {s['name']}: **{s['value']} {s['unit']}** ({s['severity']})")
    if metrics_lines:
        situation += "\n\nKey metrics:\n" + "\n".join(metrics_lines)
    situation += f"\n\nML anomaly score (Isolation Forest): **{alert['ml_anomaly_score']:.2f}** / 1.00"

    physical = _physical_reading(site, alert["signals"])
    precedents = _precedents_section(cases)
    recommendations = _recommendations(severity, site, alert["signals"])
    conf_level, conf_text = CONFIDENCE_RATIONALE[severity]

    brief = f"""## 1. Situation

{situation}

## 2. Physical reading (plausible mechanism)

{physical}

## 3. Relevant historical precedents

{precedents}

## 4. Operational recommendations

{recommendations}

## 5. Confidence level

**{conf_level.upper()}** — {conf_text}

---

*Brief automatically generated by GeoSentinel from telemetry data at {alert['as_of']}. This document is decision-support material and does not replace the analysis of authorized inspectors.*
"""
    return brief


def main():
    import sys
    site_id = sys.argv[1] if len(sys.argv) > 1 else "praid"
    print(f"\n{'='*70}\n  GeoSentinel offline brief for: {site_id}\n{'='*70}\n")
    brief = generate_brief_offline(site_id)
    print(brief)
    out = DATA_DIR / f"brief_{site_id}.md"
    out.write_text(brief, encoding="utf-8")
    print(f"\n✓ Saved to {out}")


if __name__ == "__main__":
    main()
