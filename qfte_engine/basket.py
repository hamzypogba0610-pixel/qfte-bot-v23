"""
qfte_engine/basket.py
=====================
QFTE V23.0 — Moteur principal (basketball)
Version propre - sans doublon
"""

import math
from qfte_engine.utils import (
    parse_matchs, parse_hcp, parse_ou, parse_ml,
    parse_total_mt, parse_quart, ff, fi, bloc_candidat
)

SEUIL_FIABILITE = 0.75
SEUIL_VALUE = 0.05
SEUIL_CONFIANCE = 0.70
EPS = 1e-9

def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(value)
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except Exception:
        return default

def _clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, _safe_float(value)))

def _safe_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]

def compute_score_matrix(lambda_home, lambda_away, max_points=150):
    lambda_home = max(0.0, _safe_float(lambda_home))
    lambda_away = max(0.0, _safe_float(lambda_away))
    max_points = max(50, int(max_points))

    home_probs = [math.exp(-lambda_home + i * math.log(lambda_home) - math.lgamma(i + 1)) for i in range(max_points + 1)]
    away_probs = [math.exp(-lambda_away + j * math.log(lambda_away) - math.lgamma(j + 1)) for j in range(max_points + 1)]

    matrix = []
    for i in range(max_points + 1):
        row = []
        for j in range(max_points + 1):
            row.append(home_probs[i] * away_probs[j])
        matrix.append(row)

    total = sum(sum(row) for row in matrix)
    if total > EPS:
        matrix = [[value / total for value in row] for row in matrix]

    return matrix

def compute_ml(matrix):
    p_home = 0.0
    p_away = 0.0
    for i, row in enumerate(matrix):
        for j, prob in enumerate(row):
            if i > j:
                p_home += prob
            elif j > i:
                p_away += prob
    total = p_home + p_away
    if total > EPS:
        p_home /= total
        p_away /= total
    return p_home, p_away

def facteur_fatigue(value):
    value = _safe_float(value, default=0.0)
    if value <= 0:
        return 1.00
    return _clamp(1.0 - 0.01 * value, 0.80, 1.00)

def facteur_blessures(value):
    value = _safe_float(value, default=0.0)
    if value <= 0:
        return 1.00
    return _clamp(1.0 - 0.02 * value, 0.75, 1.00)

def facteur_forme(matchs):
    matchs = _safe_list(matchs)
    if not matchs:
        return 1.00
    diff = 0.0
    for match in matchs:
        if isinstance(match, dict):
            gf = match.get("gf")
            ga = match.get("ga")
            if gf is not None and ga is not None:
                diff += _safe_float(gf) - _safe_float(ga)
    return _clamp(1.0 + 0.01 * diff, 0.90, 1.10)

def compute_ev(probabilite, cote):
    p = _clamp(probabilite)
    cote = _safe_float(cote)
    if cote <= 1.0:
        return 0.0
    return (p * cote) - 1.0

def compute_reliability(probabilite, cote=0.0):
    p = _clamp(probabilite)
    cote = _safe_float(cote)
    if cote > 1.0:
        implied = 1.0 / cote
        coherence = 1.0 - abs(p - implied)
    else:
        coherence = 0.50
    reliability = 0.70 * p + 0.30 * coherence
    return _clamp(reliability)

def eval_candidat_simple(marche, selection, probabilite, cote=None, ligne=None, direction=None):
    ev = compute_ev(probabilite, cote)
    fiabilite = compute_reliability(probabilite, cote)
    return {
        "marche": marche,
        "selection": selection,
        "probabilite": round(probabilite, 4),
        "cote": round(_safe_float(cote), 4),
        "ev": round(ev, 4),
        "fiabilite": round(fiabilite, 4),
        "decision": "VALUE" if ev >= SEUIL_VALUE and fiabilite >= SEUIL_FIABILITE else "NO BET",
    }

def calcul_handicap(matrix, ligne, cote_home=None, cote_away=None):
    win_home = 0.0
    win_away = 0.0
    for i, row in enumerate(matrix):
        for j, prob in enumerate(row):
            if i + ligne > j:
                win_home += prob
            else:
                win_away += prob
    candidats = []
    if cote_home:
        candidats.append(eval_candidat_simple("Handicap", "Home", win_home, cote_home, ligne, "home"))
    if cote_away:
        candidats.append(eval_candidat_simple("Handicap", "Away", win_away, cote_away, ligne, "away"))
    return {"ligne": ligne, "home": win_home, "away": win_away, "candidats": candidats}

def calcul_total(matrix, ligne, cote_over=None, cote_under=None):
    total_points = []
    for i, row in enumerate(matrix):
        for j, prob in enumerate(row):
            total_points.append((i + j, prob))
    p_over = sum(prob for pts, prob in total_points if pts > ligne)
    p_under = sum(prob for pts, prob in total_points if pts < ligne)
    candidats = []
    if cote_over:
        candidats.append(eval_candidat_simple("Total", f"Over {ligne}", p_over, cote_over, ligne, "over"))
    if cote_under:
        candidats.append(eval_candidat_simple("Total", f"Under {ligne}", p_under, cote_under, ligne, "under"))
    return {"ligne": ligne, "p_over": p_over, "p_under": p_under, "candidats": candidats}

def analyser_match_basket(
    home_ctx, home_glob, away_ctx, away_glob,
    h2h=None, hcp_lignes=None, ou_lignes=None,
    blessures_dom=False, blessures_ext=False,
    fatigue_dom=False, fatigue_ext=False,
    pos_dom=None, pos_ext=None, total_equipes=None,
    ml_ft=None, ml_1h=None, ml_2h=None,
    total_1h=None, total_2h=None,
    ligue=None,
    q1=None, q2=None, q3=None, q4=None,
    cote_home=None, cote_away=None,
):
    # Normalisation des historiques
    home_matches = _safe_list(home_ctx) + _safe_list(home_glob)
    away_matches = _safe_list(away_ctx) + _safe_list(away_glob)

    # Estimation des lambdas (points moyens attendus)
    lambda_home = 80 * facteur_forme(home_matches) * facteur_fatigue(fatigue_dom) * facteur_blessures(blessures_dom)
    lambda_away = 80 * facteur_forme(away_matches) * facteur_fatigue(fatigue_ext) * facteur_blessures(blessures_ext)

    # Matrice de probabilité des scores
    matrix = compute_score_matrix(lambda_home, lambda_away, max_points=150)
    p_home, p_away = compute_ml(matrix)

    # Candidats Moneyline
    candidats_ml = []
    if cote_home:
        candidats_ml.append(eval_candidat_simple("ML", "Home", p_home, cote_home))
    if cote_away:
        candidats_ml.append(eval_candidat_simple("ML", "Away", p_away, cote_away))

    # Candidats Handicap
    handicap_resultats = []
    for ligne in _safe_list(hcp_lignes):
        if isinstance(ligne, dict):
            handicap_resultats.append(
                calcul_handicap(matrix, ligne.get("ligne", 0.0), ligne.get("cote_home"), ligne.get("cote_away"))
            )
        elif isinstance(ligne, (list, tuple)) and len(ligne) >= 3:
            handicap_resultats.append(
                calcul_handicap(matrix, ligne[0], ligne[1], ligne[2])
            )

    # Candidats Over/Under
    ou_resultats = []
    for ligne in _safe_list(ou_lignes):
        if isinstance(ligne, dict):
            ou_resultats.append(
                calcul_total(matrix, ligne.get("ligne", 150), ligne.get("cote_over"), ligne.get("cote_under"))
            )
        elif isinstance(ligne, (list, tuple)) and len(ligne) >= 3:
            ou_resultats.append(
                calcul_total(matrix, ligne[0], ligne[1], ligne[2])
            )

    # Résultat final
    return {
        "ligue": ligue,
        "lambda_home": round(lambda_home, 2),
        "lambda_away": round(lambda_away, 2),
        "p_home": round(p_home, 4),
        "p_away": round(p_away, 4),
        "moneyline": candidats_ml,
        "handicap": handicap_resultats,
        "over_under": ou_resultats,
        "matrice_score": matrix,
            }
