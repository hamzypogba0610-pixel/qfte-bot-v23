"""
qfte_engine/mvp.py
------------------
Moteur d'analyse MVP — QFTE V23.0 (simplifié)
+ Filtres de discipline V23.0
"""

import math


# =========================================================
# 1. POISSON
# =========================================================
def poisson_pmf(k, lam):
    if lam <= 0:
        lam = 0.01
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def compute_lambdas(home_bp, home_bc, away_bp, away_bc):
    lambda_home = max((home_bp + away_bc) / 2.0, 0.1)
    lambda_away = max((away_bp + home_bc) / 2.0, 0.1)
    return lambda_home, lambda_away


def compute_score_matrix(lambda_home, lambda_away, max_goals=8):
    matrix = {}
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            matrix[(i, j)] = poisson_pmf(i, lambda_home) * poisson_pmf(j, lambda_away)
    return matrix


def compute_1x2(matrix):
    p1 = px = p2 = 0.0
    for (i, j), p in matrix.items():
        if i > j:
            p1 += p
        elif i == j:
            px += p
        else:
            p2 += p
    total = p1 + px + p2
    if total > 0:
        p1, px, p2 = p1 / total, px / total, p2 / total
    return p1, px, p2


# =========================================================
# 2. EV
# =========================================================
def compute_ev(p, cote):
    if cote <= 0:
        return 0.0
    return p * cote - 1.0


# =========================================================
# 3. FIABILITÉ
# =========================================================
def compute_reliability(p, cote, ev):
    f_proba = p
    f_value = 0.0 if ev < 0 else min(ev / 0.15, 1.0)
    if cote < 1.3:
        f_cote = 0.7
    elif cote > 8.0:
        f_cote = 0.5
    else:
        f_cote = 1.0
    fiabilite = 0.50 * f_proba + 0.30 * f_value + 0.20 * f_cote
    return round(min(max(fiabilite, 0.0), 1.0), 3)


# =========================================================
# 4. KELLY FRACTIONNÉ
# =========================================================
def compute_stake(p, cote, fiabilite, ev):
    """
    Kelly fractionné adaptatif (QFTE V23.0).
    Retourne le stake en % de bankroll (0 si pas de pari).
    """
    if ev <= 0 or cote <= 1:
        return 0.0

    # Kelly plein
    f_star = (p * cote - 1.0) / (cote - 1.0)

    # λ selon le niveau de fiabilité
    if fiabilite >= 0.85:
        lam = 0.30
        plafond = 1.5
    elif fiabilite >= 0.75:
        lam = 0.25
        plafond = 1.0
    elif fiabilite >= 0.65:
        lam = 0.15
        plafond = 0.5
    else:
        lam = 0.10
        plafond = 0.25

    stake = f_star * lam * 100  # en %
    stake = min(stake, plafond)
    stake = max(stake, 0.0)
    return round(stake, 2)


# =========================================================
# 5. FILTRES DE DISCIPLINE V23.0
# =========================================================
SEUIL_FIABILITE = 0.75
SEUIL_VALUE_1X2 = 0.05   # 5% pour 1X2
SEUIL_CONFIANCE = 0.70


def appliquer_filtres_discipline(p, cote, ev, fiabilite):
    """
    Vérifie les filtres obligatoires V23.0.
    Retourne (passe: bool, raisons_rejet: list)
    """
    raisons = []

    if fiabilite < SEUIL_FIABILITE:
        raisons.append(f"Fiabilité {fiabilite} < {SEUIL_FIABILITE}")

    if ev < SEUIL_VALUE_1X2:
        raisons.append(f"Value {ev*100:.2f}% < {SEUIL_VALUE_1X2*100:.0f}%")

    if p < SEUIL_CONFIANCE:
        raisons.append(f"Confiance {p*100:.2f}% < {SEUIL_CONFIANCE*100:.0f}%")

    return (len(raisons) == 0, raisons)


# =========================================================
# 6. CLASSIFICATION
# =========================================================
def classify_decision(fiabilite, ev):
    if fiabilite >= 0.85 and ev >= SEUIL_VALUE_1X2:
        return "🔥 ATTAQUE FORTE", "ELITE"
    elif fiabilite >= 0.75 and ev >= SEUIL_VALUE_1X2:
        return "✅ ATTAQUE", "PREMIUM"
    elif fiabilite >= 0.65:
        return "🤔 LEAN", "GOOD"
    elif fiabilite >= 0.55:
        return "👀 SURVEILLANCE", "SURVEILLANCE"
    else:
        return "❌ ÉVITER", "AVOID"


# =========================================================
# 7. ANALYSE COMPLÈTE FOOTBALL
# =========================================================
def analyser_match_football(
    home_bp, home_bc, away_bp, away_bc,
    open_1, open_x, open_2,
    curr_1, curr_x, curr_2
):
    lambda_home, lambda_away = compute_lambdas(home_bp, home_bc, away_bp, away_bc)
    matrix = compute_score_matrix(lambda_home, lambda_away)
    p1, px, p2 = compute_1x2(matrix)

    ev1 = compute_ev(p1, curr_1)
    evx = compute_ev(px, curr_x) if curr_x > 0 else -1.0
    ev2 = compute_ev(p2, curr_2)

    f1 = compute_reliability(p1, curr_1, ev1)
    fx = compute_reliability(px, curr_x, evx) if curr_x > 0 else 0.0
    f2 = compute_reliability(p2, curr_2, ev2)

    # Construction des 3 candidats
    candidats = [
        {"selection": "1 (Domicile)",  "p": p1, "cote": curr_1, "ev": ev1, "fiabilite": f1},
        {"selection": "X (Nul)",       "p": px, "cote": curr_x, "ev": evx, "fiabilite": fx},
        {"selection": "2 (Extérieur)", "p": p2, "cote": curr_2, "ev": ev2, "fiabilite": f2},
    ]

    # Appliquer les filtres
    for c in candidats:
        passe, raisons = appliquer_filtres_discipline(c["p"], c["cote"], c["ev"], c["fiabilite"])
        c["passe_filtres"] = passe
        c["raisons_rejet"] = raisons
        dec, niv = classify_decision(c["fiabilite"], c["ev"])
        c["decision"] = dec
        c["niveau"] = niv
        c["stake"] = compute_stake(c["p"], c["cote"], c["fiabilite"], c["ev"]) if passe else 0.0

    # Trier par fiabilité
    candidats.sort(key=lambda x: x["fiabilite"], reverse=True)

    # Règle de corrélation : UN SEUL pari retenu (le meilleur qui passe les filtres)
    pari_retenu = None
    for c in candidats:
        if c["passe_filtres"] and c["stake"] > 0:
            pari_retenu = c
            break

    # Top 3 scores
    top_scores = sorted(matrix.items(), key=lambda x: x[1], reverse=True)[:3]
    top_3 = [
        {"rank": i + 1, "score": f"{sc[0]}-{sc[1]}", "probability": round(pr, 4)}
        for i, (sc, pr) in enumerate(top_scores)
    ]

    return {
        "lambda_home": round(lambda_home, 2),
        "lambda_away": round(lambda_away, 2),
        "p1": round(p1, 4), "px": round(px, 4), "p2": round(p2, 4),
        "ev1": round(ev1, 4), "evx": round(evx, 4), "ev2": round(ev2, 4),
        "f1": f1, "fx": fx, "f2": f2,
        "candidats": candidats,
        "pari_retenu": pari_retenu,
        "top_3_scores": top_3,
    }
