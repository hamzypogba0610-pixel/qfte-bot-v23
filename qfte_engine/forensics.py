"""
qfte_engine/forensics.py
------------------------
MARKET FORENSICS ENGINE - QFTE V23.0

Detecte l'argent sharp en analysant le mouvement des cotes.
- CLV predictif
- Sharp Money Detector
- Market Efficiency Score
- Sharpe Signal Score global
"""

import math


# =========================================================
# 1. ANALYSE DU MOUVEMENT
# =========================================================
def analyser_mouvement(open_cote, curr_cote):
    """
    Calcule le delta entre ouverture et actuelle.
    Retourne un dict avec delta, direction, label.
    """
    if not open_cote or open_cote <= 0 or not curr_cote or curr_cote <= 0:
        return None

    delta = (curr_cote - open_cote) / open_cote

    # Interpretation
    if delta <= -0.15:
        direction = "STEAM"
        label = "SHARP FORT"
        interpretation = "Cote en chute forte - argent sharp massif"
    elif delta <= -0.05:
        direction = "BAISSE"
        label = "SHARP"
        interpretation = "Cote en baisse - argent sharp"
    elif delta >= 0.15:
        direction = "HAUSSE_FORTE"
        label = "PUBLIC FORT"
        interpretation = "Cote en hausse forte - argent public"
    elif delta >= 0.05:
        direction = "HAUSSE"
        label = "PUBLIC"
        interpretation = "Cote en hausse - argent public"
    else:
        direction = "STABLE"
        label = "NEUTRE"
        interpretation = "Cote stable - marche efficient"

    return {
        "open": open_cote,
        "curr": curr_cote,
        "delta": round(delta, 4),
        "delta_pct": round(delta * 100, 2),
        "direction": direction,
        "label": label,
        "interpretation": interpretation,
    }


def analyser_mouvement_1x2(open_1, open_x, open_2, curr_1, curr_x, curr_2):
    """Analyse le mouvement complet 1X2."""
    return {
        "1": analyser_mouvement(open_1, curr_1),
        "X": analyser_mouvement(open_x, curr_x),
        "2": analyser_mouvement(open_2, curr_2),
    }


# =========================================================
# 2. DETECTION DU PATTERN
# =========================================================
def detecter_pattern(mouvements):
    """
    Identifie le pattern global du match.
    Patterns : STEAM_MOVE / REVERSE_LINE_MOVEMENT / DRIFT / STATIC / MIXTE
    """
    valides = [m for m in mouvements.values() if m is not None]
    if not valides:
        return {
            "pattern": "INCONNU",
            "description": "Pas assez de donnees",
        }

    # Compte les directions
    baisse_count = sum(1 for m in valides if m["delta"] <= -0.05)
    hausse_count = sum(1 for m in valides if m["delta"] >= 0.05)
    stable_count = sum(1 for m in valides if abs(m["delta"]) < 0.05)

    # Steam Move : baisse forte sur UNE seule issue
    for m in valides:
        if m["delta"] <= -0.15:
            return {
                "pattern": "STEAM_MOVE",
                "description": "Argent sharp massif sur une issue - signal fort",
                "force": abs(m["delta"]),
                "issue_concernee": m,
            }

    # Reverse Line Movement : 2 issues montent, 1 baisse fortement
    if baisse_count >= 1 and hausse_count >= 1:
        return {
            "pattern": "REVERSE_LINE_MOVEMENT",
            "description": "Mouvement contradictoire - sharp contre public",
            "force": 0.6,
        }

    # Static : aucune mouvement
    if stable_count == len(valides):
        return {
            "pattern": "STATIC",
            "description": "Marche fige - peu d'information",
            "force": 0.0,
        }

    # Drift : mouvements modere
    return {
        "pattern": "DRIFT",
        "description": "Mouvement lent - argent en transition",
        "force": 0.4,
    }


# =========================================================
# 3. CLV PREDICTIF
# =========================================================
def calculer_clv_predictif(mouvements, pattern):
    """
    Predit le CLV (Closing Line Value) a partir du mouvement.
    Le CLV est positif si l'argent sharp est entre (cote baisse).
    """
    valides = [m for m in mouvements.values() if m is not None]
    if not valides:
        return {
            "clv_predictif": 0.0,
            "clv_par_issue": {},
            "interpretation": "Pas de donnees",
        }

    # Pour chaque issue : CLV = -delta (si la cote baisse, CLV positif)
    clv_par_issue = {}
    for k, m in mouvements.items():
        if m is None:
            clv_par_issue[k] = 0.0
            continue
        # Baisse -> CLV positif
        clv = -m["delta"]
        clv_par_issue[k] = round(clv, 4)

    # CLV global : moyenne ponderee par la force du mouvement
    clv_global = sum(abs(c) for c in clv_par_issue.values()) / len(clv_par_issue)

    # Ajustement selon le pattern
    if pattern["pattern"] == "STEAM_MOVE":
        clv_global *= 1.3
    elif pattern["pattern"] == "REVERSE_LINE_MOVEMENT":
        clv_global *= 1.15
    elif pattern["pattern"] == "STATIC":
        clv_global *= 0.5

    # Interpretation
    if clv_global > 0.05:
        interp = "CLV predictif FORT - argent sharp confirme"
    elif clv_global > 0.02:
        interp = "CLV predictif positif - signal sharp"
    elif clv_global > -0.02:
        interp = "CLV predictif neutre"
    else:
        interp = "CLV predictif negatif - attention"

    return {
        "clv_predictif": round(clv_global, 4),
        "clv_par_issue": clv_par_issue,
        "interpretation": interp,
      }



# =========================================================
# 4. SHARP MONEY SCORE
# =========================================================
def calculer_sharp_money_score(mouvements, pattern):
    """
    Score entre -1 et +1.
    Positif = argent sharp.
    Negatif = argent public.
    """
    valides = [m for m in mouvements.values() if m is not None]
    if not valides:
        return {
            "score": 0.0,
            "label": "NEUTRE",
            "interpretation": "Pas de donnees",
        }

    # Score de base : moyenne des deltas inversee
    somme = 0.0
    for m in valides:
        # Delta negatif (baisse) = positif pour sharp
        somme += -m["delta"]

    score_base = somme / len(valides)

    # Facteur pattern
    if pattern["pattern"] == "STEAM_MOVE":
        score_base *= 1.5
    elif pattern["pattern"] == "REVERSE_LINE_MOVEMENT":
        score_base *= 1.2
    elif pattern["pattern"] == "STATIC":
        score_base *= 0.3

    # Borner entre -1 et +1
    score = max(min(score_base, 1.0), -1.0)

    # Label
    if score >= 0.50:
        label = "SHARP MASSIF"
        interp = "Argent sharp tres fort detecte"
    elif score >= 0.20:
        label = "SHARP"
        interp = "Argent sharp present"
    elif score >= -0.20:
        label = "NEUTRE"
        interp = "Marche equilibre"
    elif score >= -0.50:
        label = "PUBLIC"
        interp = "Argent public - prudence"
    else:
        label = "PUBLIC MASSIF"
        interp = "Argent public massif - danger"

    return {
        "score": round(score, 4),
        "label": label,
        "interpretation": interp,
    }


# =========================================================
# 5. MARKET EFFICIENCY SCORE
# =========================================================
def calculer_efficience(mouvements):
    """
    Score entre 0 et 1.
    1 = marche tres efficient (value faible)
    0 = marche inefficient (value potentielle)
    """
    valides = [m for m in mouvements.values() if m is not None]
    if not valides:
        return {
            "efficience": 0.5,
            "label": "INCONNU",
            "interpretation": "Pas de donnees",
        }

    # Mouvement total
    mouvement_total = sum(abs(m["delta"]) for m in valides)

    # Efficience : plus le mouvement est faible, plus c'est efficient
    # Mouvement total typique : 0.10 (10%)
    efficience = 1.0 - min(mouvement_total / 0.30, 1.0)

    if efficience >= 0.85:
        label = "TRES EFFICIENT"
        interp = "Marche tres bien prix - value faible"
    elif efficience >= 0.60:
        label = "EFFICIENT"
        interp = "Marche normalement efficient"
    elif efficience >= 0.40:
        label = "MODEREMENT INEFFICIENT"
        interp = "Value potentielle detectee"
    else:
        label = "INEFFICIENT"
        interp = "Marche desequilibre - value forte"

    return {
        "efficience": round(efficience, 4),
        "label": label,
        "interpretation": interp,
    }


# =========================================================
# 6. SHARPE SIGNAL SCORE (score global)
# =========================================================
def calculer_sharpe_signal(clv, sharp_money, efficience):
    """
    Score global entre -1 et +1.
    Combine CLV, Sharp Money et Efficience.
    """
    clv_score = clv["clv_predictif"]
    sharp_score = sharp_money["score"]
    eff_score = efficience["efficience"]

    # Formule signature
    sharpe = 0.4 * clv_score + 0.4 * sharp_score + 0.2 * (1.0 - eff_score)

    # Borner
    sharpe = max(min(sharpe, 1.0), -1.0)

    # Label
    if sharpe >= 0.50:
        label = "TRES SHARP"
        couleur = "#4ade80"
        interp = "Signal sharp tres fort - confiance maximale"
    elif sharpe >= 0.20:
        label = "SHARP"
        couleur = "#22c55e"
        interp = "Signal sharp confirme"
    elif sharpe >= -0.20:
        label = "NEUTRE"
        couleur = "#eab308"
        interp = "Signal neutre - marche equilibre"
    elif sharpe >= -0.50:
        label = "CONTRAIRE"
        couleur = "#ef4444"
        interp = "Signal contraire - attention"
    else:
        label = "TRES CONTRAIRE"
        couleur = "#dc2626"
        interp = "Signal tres contraire - danger"

    return {
        "sharpe_signal": round(sharpe, 4),
        "label": label,
        "couleur": couleur,
        "interpretation": interp,
    }


# =========================================================
# 7. AJUSTEMENT DE FIABILITE
# =========================================================
def ajuster_fiabilite(fiabilite, sharpe_signal):
    """
    Ajuste la fiabilite d'un pari selon le Sharpe Signal.
    - Signal sharp : +0.05 max
    - Signal contraire : -0.10 max
    """
    score = sharpe_signal["sharpe_signal"]

    if score >= 0.50:
        ajust = 0.08
    elif score >= 0.20:
        ajust = 0.05
    elif score >= -0.20:
        ajust = 0.0
    elif score >= -0.50:
        ajust = -0.05
    else:
        ajust = -0.10

    nouvelle = fiabilite + ajust
    return round(max(min(nouvelle, 1.0), 0.0), 3)


# =========================================================
# 8. FONCTION PRINCIPALE
# =========================================================
def analyser_market_forensics(open_1, open_x, open_2, curr_1, curr_x, curr_2):
    """
    Orchestre toute l'analyse Market Forensics.

    Retourne un dict avec :
      - mouvements (par issue)
      - pattern
      - clv
      - sharp_money
      - efficience
      - sharpe_signal
    """
    # 1. Mouvements
    mouvements = analyser_mouvement_1x2(open_1, open_x, open_2, curr_1, curr_x, curr_2)

    # 2. Pattern
    pattern = detecter_pattern(mouvements)

    # 3. CLV predictif
    clv = calculer_clv_predictif(mouvements, pattern)

    # 4. Sharp Money Score
    sharp_money = calculer_sharp_money_score(mouvements, pattern)

    # 5. Efficience
    efficience = calculer_efficience(mouvements)

    # 6. Sharpe Signal
    sharpe = calculer_sharpe_signal(clv, sharp_money, efficience)

    # Verifier si on a assez de donnees
    data_dispo = all(m is not None for m in mouvements.values())

    return {
        "disponible": data_dispo,
        "mouvements": mouvements,
        "pattern": pattern,
        "clv": clv,
        "sharp_money": sharp_money,
        "efficience": efficience,
        "sharpe_signal": sharpe,
  }
