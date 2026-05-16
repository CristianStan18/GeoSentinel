"""
Bază minimală de cazuri istorice pentru RAG.

În producție: indexezi vectorial PDF-uri de la ITM, ANRM, literatură
academică (Berest et al. pe solution mining failures, lucrările despre
Solikamsk II 1995, Retsof 1994, Wieliczka, etc.).

Pentru hackathon: dicționar curat cu cazuri-cheie. Agentul poate
referenția precedentele relevante.
"""

CASE_DATABASE = [
    {
        "id": "praid_2025",
        "name": "Prăbușirea Salinei Praid (2025)",
        "country": "România",
        "mine_type": "sare",
        "outcome": "catastrofă",
        "precursors": [
            "creștere progresivă a infiltrațiilor în orizonturile inferioare",
            "microseismicitate locală raportată în lunile premergătoare",
            "subsidență accelerată vizibilă în Sentinel-1 InSAR",
            "raportări publice despre fisuri și prăbușiri locale",
        ],
        "root_cause": (
            "Infiltrația de apă dulce din pârâul Corund a dizolvat progresiv "
            "pilierii de susținere, conducând la prăbușirea cavităților."
        ),
        "lessons": [
            "Infiltrația de apă dulce în mine de sare este existențială.",
            "Triada InSAR + microseismicitate + creștere infiltrație trebuie "
            "tratată ca prag de evacuare, nu de monitorizare.",
        ],
    },
    {
        "id": "solikamsk_1995",
        "name": "Prăbușirea minei Solikamsk-2 (Rusia, 1995)",
        "country": "Rusia",
        "mine_type": "sare",
        "outcome": "prăbușire majoră, fără victime (evacuare)",
        "precursors": [
            "cutremur indus M=4.7",
            "subsidență la suprafață",
            "creștere a debitelor de infiltrație",
        ],
        "root_cause": (
            "Pilieri subdimensionați + infiltrație. Două prăbușiri ulterioare "
            "(2014, 2018) au repetat scenariul."
        ),
        "lessons": [
            "Microseismicitatea indusă > M=2 într-o mină de sare e abnormală.",
            "După un eveniment major, riscul rămâne ridicat decenii.",
        ],
    },
    {
        "id": "retsof_1994",
        "name": "Prăbușirea minei de sare Retsof (NY, SUA, 1994)",
        "country": "SUA",
        "mine_type": "sare",
        "outcome": "inundare totală, pierderi economice mari",
        "precursors": [
            "cutremur indus M=3.6 (12 martie 1994)",
            "creștere bruscă a debitelor de apă în mină",
            "subsidență la suprafață",
        ],
        "root_cause": "Prăbușirea unui pilier a deschis cale apei subterane.",
        "lessons": [
            "Inundarea unei mine de sare este ireversibilă o dată începută.",
            "Decizia de evacuare trebuie să se ia înainte de creșterea brutală "
            "a debitului — la primele semne, nu la apogeu.",
        ],
    },
    {
        "id": "lupeni_1994",
        "name": "Accidentul de la Mina Lupeni (1994)",
        "country": "România",
        "mine_type": "carbune",
        "outcome": "victime",
        "precursors": [
            "concentrații crescute de metan",
            "ventilație insuficientă",
        ],
        "root_cause": "Explozie de metan în Valea Jiului.",
        "lessons": [
            "Pentru cărbune, riscul dominant este metanul, nu stabilitatea.",
            "Monitorizarea atmosferică continuă e indispensabilă.",
        ],
    },
    {
        "id": "barry_arm_alaska",
        "name": "Versantul Barry Arm, Alaska (monitorizare 2020-prezent)",
        "country": "SUA",
        "mine_type": "alunecare_post_glaciara",
        "outcome": "monitorizare activă, fără eveniment major încă",
        "precursors": [
            "subsidență accelerată InSAR post-retragere glaciară",
            "fracturi vizibile crescute",
        ],
        "root_cause": (
            "Decompresia versantului după retragerea ghețarului expune masa "
            "instabilă la risc de prăbușire bruscă în fjord (potențial mega-tsunami)."
        ),
        "lessons": [
            "InSAR detectează semnal mult înainte de prăbușire.",
            "Monitorizarea preventivă cu evacuare condiționată funcționează.",
        ],
    },
]


def find_relevant_cases(
    mine_type: str, signals_names: list[str], top_k: int = 2
) -> list[dict]:
    """
    Caută cazuri similare — filtrare simplă pe tip de mină + match pe semnale.
    Pentru producție: înlocuiește cu căutare vectorială.
    """
    scored = []
    for case in CASE_DATABASE:
        score = 0
        if case["mine_type"] == mine_type:
            score += 5
        # Bonus dacă precursorii overlap cu semnalele detectate
        all_text = " ".join(case["precursors"] + [case["root_cause"]]).lower()
        for sig in signals_names:
            if any(word in all_text for word in sig.lower().split()):
                score += 1
        scored.append((score, case))

    scored.sort(key=lambda x: -x[0])
    return [c for s, c in scored[:top_k] if s > 0]
