"""
Minimal historical case database for RAG.

In production, this should be replaced by a vector index over ITM, ANRM and
academic PDFs (for example Berest et al. on solution-mining failures, papers on
Solikamsk II 1995, Retsof 1994, Wieliczka, etc.).

For the hackathon demo, this clean dictionary keeps the key precedents directly
available to the agent.
"""

CASE_DATABASE = [
    {
        "id": "praid_2025",
        "name": "Praid Salt Mine Collapse (2025)",
        "country": "Romania",
        "mine_type": "sare",
        "outcome": "catastrophic event",
        "precursors": [
            "progressive increase in infiltration in the lower horizons",
            "local microseismicity reported in the months before the event",
            "accelerated subsidence visible in Sentinel-1 InSAR",
            "public reports of cracks and local collapses",
        ],
        "root_cause": (
            "Freshwater infiltration from the Corund stream progressively dissolved "
            "the support pillars, leading to cavity collapse."
        ),
        "lessons": [
            "Freshwater infiltration in salt mines is an existential risk.",
            "The InSAR + microseismicity + infiltration triad should be treated as "
            "an evacuation threshold, not just a monitoring threshold.",
        ],
    },
    {
        "id": "solikamsk_1995",
        "name": "Solikamsk-2 Mine Collapse (Russia, 1995)",
        "country": "Russia",
        "mine_type": "sare",
        "outcome": "major collapse, no casualties after evacuation",
        "precursors": [
            "M=4.7 induced earthquake",
            "surface subsidence",
            "increased infiltration flows",
        ],
        "root_cause": (
            "Undersized pillars + infiltration. Two later collapses (2014, 2018) "
            "repeated the same scenario."
        ),
        "lessons": [
            "Induced microseismicity above M=2 in a salt mine is abnormal.",
            "After a major event, risk can remain elevated for decades.",
        ],
    },
    {
        "id": "retsof_1994",
        "name": "Retsof Salt Mine Collapse (NY, USA, 1994)",
        "country": "USA",
        "mine_type": "sare",
        "outcome": "complete flooding and major economic losses",
        "precursors": [
            "M=3.6 induced earthquake on March 12, 1994",
            "sudden increase in mine water inflow",
            "surface subsidence",
        ],
        "root_cause": "A pillar collapse opened a pathway for groundwater.",
        "lessons": [
            "Flooding in a salt mine is irreversible once it begins.",
            "Evacuation decisions must be made before the brutal increase in flow — "
            "at the first signs, not at the peak.",
        ],
    },
    {
        "id": "lupeni_1994",
        "name": "Lupeni Mine Accident (1994)",
        "country": "Romania",
        "mine_type": "carbune",
        "outcome": "fatalities",
        "precursors": [
            "increased methane concentrations",
            "insufficient ventilation",
        ],
        "root_cause": "Methane explosion in the Jiu Valley.",
        "lessons": [
            "For coal mines, the dominant risk is methane, not only stability.",
            "Continuous atmospheric monitoring is indispensable.",
        ],
    },
    {
        "id": "barry_arm_alaska",
        "name": "Barry Arm Slope, Alaska (monitoring 2020-present)",
        "country": "USA",
        "mine_type": "alunecare_post_glaciara",
        "outcome": "active monitoring, no major event yet",
        "precursors": [
            "accelerated InSAR subsidence after glacier retreat",
            "increased visible fracturing",
        ],
        "root_cause": (
            "Slope decompression after glacier retreat exposed the unstable mass "
            "to sudden fjord collapse risk and potential mega-tsunami generation."
        ),
        "lessons": [
            "InSAR detects the signal long before collapse.",
            "Preventive monitoring with conditional evacuation works.",
        ],
    },
]


def find_relevant_cases(
    mine_type: str, signals_names: list[str], top_k: int = 2
) -> list[dict]:
    """
    Search for similar cases using simple filtering by mine type and signal match.
    For production, replace this with vector search.
    """
    scored = []
    for case in CASE_DATABASE:
        score = 0
        if case["mine_type"] == mine_type:
            score += 5
        all_text = " ".join(case["precursors"] + [case["root_cause"]]).lower()
        for sig in signals_names:
            if any(word in all_text for word in sig.lower().split()):
                score += 1
        scored.append((score, case))

    scored.sort(key=lambda x: -x[0])
    return [c for s, c in scored[:top_k] if s > 0]
