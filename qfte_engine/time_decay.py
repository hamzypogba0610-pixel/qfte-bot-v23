"""
qfte_engine/time_decay.py
-------------------------
TIME-DECAY WEIGHTING - QFTE V23.0

Ponderation exponentielle des matchs selon leur anciennete.
Les matchs recents comptent plus que les anciens.

Option B : on utilise le RANG (position dans la liste)
  - Rang 1 (le plus recent) : poids max
  - Rang 5 (le plus ancien) : poids min
"""

import math


# =========================================================
# 1. POIDS PAR RANG
# =========================================================
# Facteurs de decroissance (rang -> poids)
POIDS_RANG = {
    1: 1.00,   # le plus recent
    2: 0.82,
    3: 0.67,
    4: 0.55,
    5: 0.45,   # le plus ancien
}


def poids_par_rang(rang):
    """Retourne le poids d'un match selon son rang (1 a 5+)."""
    if rang in POIDS_RANG:
        return POIDS_RANG[rang]
    if rang > 5:
        return max(0.45 - (rang - 5) * 0.05, 0.20)
    return 1.0


# =========================================================
# 2. MOYENNE PONDEREE
# =========================================================
def moyenne_ponderee(valeurs):
    """
    Calcule la moyenne ponderee d'une liste de valeurs.
    La position 0 = le match le plus recent = poids max.

    Parametres :
      valeurs : liste de nombres (ou None)

    Retourne la moyenne ponderee (float).
    """
    if not valeurs:
        return 0.0

    total_poids = 0.0
    total_valeurs = 0.0

    for i, v in enumerate(valeurs):
        if v is None:
            continue
        rang = i + 1
        poids = poids_par_rang(rang)
        total_valeurs += v * poids
        total_poids += poids

    if total_poids <= 0:
        return 0.0
    return total_valeurs / total_poids


# =========================================================
# 3. EXTRACTION DE MESSAGES
# =========================================================
def extraire_moyennes_ponderees(matchs):
    """
    Prend une liste de matchs (dict avec bp/bc/ht_bp/ht_bc)
    et retourne les moyennes ponderees.

    Parametres :
      matchs : liste de dict [{"bp": ..., "bc": ..., ...}, ...]

    Retourne un dict avec :
      bp, bc, ht_bp, ht_bc (moyennes ponderees)
      nb_matchs (nombre de matchs valides)
    """
    if not matchs:
        return {
            "bp": 0.0,
            "bc": 0.0,
            "ht_bp": 0.0,
            "ht_bc": 0.0,
            "nb_matchs": 0,
        }

    bp_list = [m.get("bp") for m in matchs]
    bc_list = [m.get("bc") for m in matchs]
    ht_bp_list = [m.get("ht_bp") for m in matchs]
    ht_bc_list = [m.get("ht_bc") for m in matchs]

    bp_moy = moyenne_ponderee(bp_list)
    bc_moy = moyenne_ponderee(bc_list)
    ht_bp_moy = moyenne_ponderee(ht_bp_list)
    ht_bc_moy = moyenne_ponderee(ht_bc_list)

    return {
        "bp": round(bp_moy, 3),
        "bc": round(bc_moy, 3),
        "ht_bp": round(ht_bp_moy, 3),
        "ht_bc": round(ht_bc_moy, 3),
        "nb_matchs": len(matchs),
    }


# =========================================================
# 4. FUSION DES POIDS CONTEXTE + GLOBAL
# =========================================================
def fusion_ponderee(moy_ctx, moy_glob, poids_ctx=0.7):
    """
    Fusionne deux moyennes (contexte + global) avec un poids.
    Garde la compatibilite avec le systeme existant (0.7 / 0.3).
    """
    if moy_ctx is None and moy_glob is None:
        return 0.0
    if moy_ctx is None:
        return moy_glob
    if moy_glob is None:
        return moy_ctx
    return round(poids_ctx * moy_ctx + (1 - poids_ctx) * moy_glob, 3)
