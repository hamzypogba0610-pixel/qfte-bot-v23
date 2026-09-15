"""
qfte_engine/mvp.py
------------------
Moteur d'analyse MVP — QFTE V23.0 (simplifié)

Contient :
- Calcul Poisson (buts attendus, probas 1/X/2)
- Calcul EV (value nette)
- Calcul Fiabilité (formule V23.0 simplifiée)
- Classification décision (ATTAQUE / LEAN / ÉVITER)
"""

import math


# =========================================================
# 1. POISSON — Calcul des buts attendus et probabilités
# =========================================================
def poisson_pmf(k, lam):
    """Probabilité d'avoir exactement k buts sachant λ (lambda)."""
    if lam <= 0:
        lam = 0.01
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def compute_lambdas(home_bp, home_bc, away_bp, away_bc):
    """
    Calcule les buts attendus (λ) de chaque équipe.

    λ_domicile = (buts marqués dom. + buts encaissés ext.) / 2
    λ_extérieur = (buts marqués ext. + buts encaissés dom.) / 2
    """
    lambda_home = (home_bp + away_bc) / 2.0
    lambda_away = (away_bp + home_bc) / 2.0
    # Sécurité : minimum 0.1 pour éviter les λ nuls
    return max(lambda_home, 0.1), max(lambda_away, 0.1)


def compute_score_matrix(lambda_home, lambda_away, max_goals=8):
    """Matrice P(score exact) pour tous les scores de 0 à max_goals."""
    matrix = {}
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            matrix[(i, j)] = poisson_pmf(i, lambda_home) * poisson_pmf(j, lambda_away)
    return matrix


def compute_1x2(matrix):
    """Probabilités 1 (domicile gagne), X (nul), 2 (extérieur gagne)."""
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
# 2. EV — Espérance de gain (value)
# =========================================================
def compute_ev(p, cote):
    """EV_net = (p × cote) − 1."""
    if cote <= 0:
        return 0.0
    return p * cote - 1.0


# =========================================================
# 3. FIABILITÉ — Formule V23.0 simplifiée
# =========================================================
def compute_reliability(p, cote, ev):
    """
    Fiabilité = 0.50 × p
              + 0.30 × f_value (value normalisée, max à 15%)
              + 0.20 × f_cote (stabilité de la cote)
    """
    # Facteur 1 : probabilité
    f_proba = p

    # Facteur 2 : value (0 si négative, max 1 si >= 15%)
    f_value = 0.0 if ev < 0 else min(ev / 0.15, 1.0)

    # Facteur 3 : stabilité selon la cote
    if cote < 1.3:
        f_cote = 0.7      # cote trop basse → peu de marge
    elif cote > 8.0:
        f_cote = 0.5      # cote trop haute → variance énorme
    else:
        f_cote = 1.0

    fiabilite = 0.50 * f_proba + 0.30 * f_value + 0.20 * f_cote
    return round(min(max(fiabilite, 0.0), 1.0), 3)


# =========================================================
# 4. CLASSIFICATION — Décision finale
# =========================================================
def classify_decision(fiabilite, ev, seuil_value=0.05):
    """Retourne (label_décision, niveau)."""
    if fiabilite >= 0.85 and ev >= seuil_value:
        return "🔥 ATTAQUE FORTE", "ELITE"
    elif fiabilite >= 0.75 and ev >= seuil_value:
        return "✅ ATTAQUE", "PREMIUM"
    elif fiabilite >= 0.65 and ev >= seuil_value * 0.8:
        return "🤔 LEAN", "GOOD"
    elif fiabilite >= 0.55:
        return "👀 SURVEILLANCE", "SURVEILLANCE"
    else:
        return "❌ ÉVITER", "AVOID"


# =========================================================
# 5. ANALYSE COMPLÈTE (football)
# =========================================================
def analyser_match_football(
    home_bp, home_bc, away_bp, away_bc,
    open_1, open_x, open_2,
    curr_1, curr_x, curr_2
):
    """Pipeline MVP football complet."""

    # Étape 1 : buts attendus (λ)
    lambda_home, lambda_away = compute_lambdas(home_bp, home_bc, away_bp, away_bc)

    # Étape 2 : matrice des scores
    matrix = compute_score_matrix(lambda_home, lambda_away)

    # Étape 3 : probabilités 1X2
    p1, px, p2 = compute_1x2(matrix)

    # Étape 4 : EV
    ev1 = compute_ev(p1, curr_1)
    evx = compute_ev(px, curr_x) if curr_x > 0 else -1.0
    ev2 = compute_ev(p2, curr_2)

    # Étape 5 : fiabilité
    f1 = compute_reliability(p1, curr_1, ev1)
    fx = compute_reliability(px, curr_x, evx) if curr_x > 0 else 0.0
    f2 = compute_reliability(p2, curr_2, ev2)

    # Étape 6 : classification
    rec1 = classify_decision(f1, ev1)
    recx = classify_decision(fx, evx)
    rec2 = classify_decision(f2, ev2)

    # Étape 7 : liste des recommandations
    recommandations = [
        {"selection": "1 (Domicile)", "marche": "1X2", "p": p1, "cote": curr_1, "ev": ev1, "fiabilite": f1, "decision": rec1[0], "niveau": rec1[1]},
        {"selection": "X (Nul)",     "marche": "1X2", "p": px, "cote": curr_x, "ev": evx, "fiabilite": fx, "decision": recx[0], "niveau": recx[1]},
        {"selection": "2 (Extérieur)","marche": "1X2", "p": p2, "cote": curr_2, "ev": ev2, "fiabilite": f2, "decision": rec2[0], "niveau": rec2[1]},
    ]
    # Tri par fiabilité décroissante
    recommandations.sort(key=lambda x: x["fiabilite"], reverse=True)

    # Étape 8 : top 3 scores
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
        "recommandations": recommandations,
        "top_3_scores": top_3,
  }
