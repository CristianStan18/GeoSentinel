"""
LLM agent that turns numerical alerts into operational briefings.

Run with: python -m agent.brief [site_id]
Without an argument, it runs on the site with the highest severity.
"""

import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from config import get_site
from agent.case_database import find_relevant_cases


load_dotenv()
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
PROMPTS_DIR = ROOT / "prompts"

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
SYSTEM_PROMPT = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")


def _load_alerts() -> list[dict]:
    with open(DATA_DIR / "alerts.json", encoding="utf-8") as f:
        return json.load(f)


def _format_alert_for_llm(alert: dict, site) -> str:
    """Build textual context for the LLM."""
    lines = [
        f"# Monitored-site telemetry: {alert['site_name']}",
        f"Operator: {site.operator} | Type: {site.mine_type} | "
        f"Status: {site.status} | Depth/cover: {site.depth_m}m",
        f"Location: lat={site.lat}, lon={site.lon}",
        f"Report date: {alert['as_of']}",
        f"Calculated overall severity: **{alert['overall_severity'].upper()}**",
        f"ML anomaly score (Isolation Forest): {alert['ml_anomaly_score']:.2f}",
        "",
        "## Individual signals",
    ]
    for s in alert["signals"]:
        lines.append(
            f"- **{s['name']}**: {s['value']} {s['unit']} "
            f"→ severity `{s['severity']}` ({s['threshold_hit']})"
        )
        lines.append(f"  _{s['description']}_")
    lines.append("")
    lines.append("## Summary metrics")
    for k, v in alert["summary_metrics"].items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def _format_cases(cases: list[dict]) -> str:
    if not cases:
        return "No close historical precedent was identified in the case database."
    lines = ["## Relevant historical precedents"]
    for c in cases:
        lines.append(f"\n### {c['name']} ({c['country']})")
        lines.append(f"**Type:** {c['mine_type']} | **Outcome:** {c['outcome']}")
        lines.append("**Observed precursors:**")
        for p in c["precursors"]:
            lines.append(f"  - {p}")
        lines.append(f"**Root cause:** {c['root_cause']}")
        lines.append("**Lessons:**")
        for l in c["lessons"]:
            lines.append(f"  - {l}")
    return "\n".join(lines)


def generate_brief(site_id: str) -> str:
    alerts = _load_alerts()
    alert = next((a for a in alerts if a["site_id"] == site_id), None)
    if not alert:
        raise ValueError(f"No alert found for site {site_id}")

    site = get_site(site_id)
    signal_names = [s["name"] for s in alert["signals"]]
    cases = find_relevant_cases(site.mine_type, signal_names, top_k=2)

    context = _format_alert_for_llm(alert, site)
    cases_text = _format_cases(cases)

    user_message = (
        f"{context}\n\n{cases_text}\n\n"
        "Generate the operational briefing following the structure in the instructions. "
        "Be precise, concrete and honest about uncertainty."
    )

    client = Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    return text


def auto_select_site(alerts: list[dict]) -> str:
    """Select the site with the highest severity."""
    rank = {"info": 0, "watch": 1, "warning": 2, "alarm": 3}
    sorted_alerts = sorted(
        alerts, key=lambda a: (rank[a["overall_severity"]], a["ml_anomaly_score"]),
        reverse=True,
    )
    return sorted_alerts[0]["site_id"]


def main() -> None:
    alerts = _load_alerts()
    site_id = sys.argv[1] if len(sys.argv) > 1 else auto_select_site(alerts)
    print(f"\n{'=' * 70}\n  GeoSentinel brief for: {site_id}\n{'=' * 70}\n")
    brief = generate_brief(site_id)
    print(brief)
    print(f"\n{'=' * 70}\n")

    out = DATA_DIR / f"brief_{site_id}.md"
    out.write_text(brief, encoding="utf-8")
    print(f"✓ Saved to {out}")


if __name__ == "__main__":
    main()
