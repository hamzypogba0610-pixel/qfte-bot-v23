"""
qfte_engine/signature.py
------------------------
QFTE SIGNATURE V23.0 - Module True Sigma

Calcule un sigma (écart-type) ADAPTATIF pour chaque match basket,
basé sur la volatilité réelle de chaque équipe.

Innovations :
- Sigma individuel par équipe (calculé sur les 5 derniers matchs)
- Fusion intelligente dom/ext/ligue
- Indice de Consistance (0 = imprévisible, 1 = très régulier)
- Détection d'alerte volatilité
"""

import math


# =========================================================
# 1. SIGMA LIGUE (garde-fou de base)
# =========================================================
SIGMA_LIGUE = {
    "nba": 11.5,
    "euroleague": 9.0,
    "lnb": 9.5,
    "acb": 9.0,
    "bbl": 9.5,
    "lega": 9.5,
    "ncaa": 10.0,
    "fiba": 10.0,
    "autre": 10.5,
}


def get_sigma_ligue(ligue):
    if not ligue:
        return 11.0
    return SIGMA_LIGUE.get(ligue, 10.5)


# =========================================================
# 2. SIGMA INDIVIDUEL D'UNE EQUIPE
# =========================================================
def calcul_sigma_individuel(matchs):
    """
    Calcule l'écart-type des marges (bp - bc) sur les matchs fournis.
    Retourne une valeur entre 2.0 et 25.0 (bornée).
    """
    if not matchs or len(matchs) < 2:
        return None

    marges = [m["bp"] - m["bc"] for m in matchs]
    n = len(marges)
    moy = sum(marges) / n

    variance = sum((x - moy) ** 2 for x in marges) / n
    sigma = math.sqrt(variance)

    # Bornes raisonnables pour le basket
    return round(max(min(sigma, 25.0), 2.0), 2)


# =========================================================
# 3. SIGMA DU MATCH (fusion)
# =========================================================
def calcul_sigma_match(sigma_dom, sigma_ext, ligue):
    """
    Fusionne les sigmas individuels avec le sigma ligue.

    Formule :
      sigma_match = sqrt((sigma_dom² + sigma_ext²) / 2)
      sigma_final = 0.6 × sigma_match + 0.4 × sigma_ligue
    """
    s_ligue = get_sigma_ligue(ligue)

    if sigma_dom is None or sigma_ext is None:
        return {
            "sigma_dom": sigma_dom,
            "sigma_ext": sigma_ext,
            "sigma_match": None,
            "sigma_ligue": s_ligue,
            "sigma_final": s_ligue,
            "methode": "fixe_ligue",
        }

    sigma_match = math.sqrt((sigma_dom ** 2 + sigma_ext ** 2) / 2.0)
    sigma_final = 0.6 * sigma_match + 0.4 * s_ligue

    # Bornes : on reste entre 50% et 150% du sigma ligue
    sigma_final = max(min(sigma_final, s_ligue * 1.5), s_ligue * 0.5)

    return {
        "sigma_dom": sigma_dom,
        "sigma_ext": sigma_ext,
        "sigma_match": round(sigma_match, 2),
        "sigma_ligue": s_ligue,
        "sigma_final": round(sigma_final, 2),
        "methode": "adaptatif",
    }


# =========================================================
# 4. INDICE DE CONSISTANCE
# =========================================================
def calcul_consistance(sigma_equipe, ligue):
    """
    Consistance = 1 - (sigma_equipe / sigma_max)
    Retourne un indice entre 0 et 1.
       > 0.75 : très régulier (paris sûrs)
       0.50-0.75 : normal
       < 0.50 : imprévisible (prudence)
    """
    if sigma_equipe is None:
        return None

    s_ligue = get_sigma_ligue(ligue)
    sigma_max = s_ligue * 1.3  # référence haute

    consistance = 1.0 - (sigma_equipe / sigma_max)
    return round(max(min(consistance, 1.0), 0.0), 2)


def label_consistance(c):
    if c is None:
        return "N/A"
    if c >= 0.75:
        return "TRES REGULIER"
    elif c >= 0.50:
        return "NORMAL"
    else:
        return "IMPREVISIBLE"


# =========================================================
# 5. ALERTE VOLATILITE
# =========================================================
def detecter_alerte_volatilite(sigma_final, ligue):
    """
    Retourne un niveau d'alerte :
      - "NORMAL" : rien à signaler
      - "ATTENTION" : volatilité > 1.15 × sigma ligue
      - "ELEVEE" : volatilité > 1.30 × sigma ligue
    """
    s_ligue = get_sigma_ligue(ligue)
    ratio = sigma_final / s_ligue if s_ligue > 0 else 1.0

    if ratio > 1.30:
        return "ELEVEE", round(ratio, 2)
    elif ratio > 1.15:
        return "ATTENTION", round(ratio, 2)
    else:
        return "NORMAL", round(ratio, 2)

  

# =========================================================
# 6. FONCTION PRINCIPALE — Analyse complète True Sigma
# =========================================================
def analyser_true_sigma(home_ctx, away_ctx, home_glob, away_glob, ligue):
    """
    Orchestre tout le module True Sigma.

    Retourne un dict avec :
      - sigmas (dom, ext, match, ligue, final)
      - consistances (dom, ext)
      - alertes (niveau, ratio)
      - recommandation_stake (multiplicateur pour le stake)
    """
    # Sigmas individuels (sur le contexte : dom à dom, ext à ext)
    sigma_dom = calcul_sigma_individuel(home_ctx)
    sigma_ext = calcul_sigma_individuel(away_ctx)

    # Si pas assez de données contextuelles, on utilise les globales
    if sigma_dom is None and home_glob:
        sigma_dom = calcul_sigma_individuel(home_glob)
    if sigma_ext is None and away_glob:
        sigma_ext = calcul_sigma_individuel(away_glob)

    # Fusion
    fusion = calcul_sigma_match(sigma_dom, sigma_ext, ligue)

    # Consistances
    consistance_dom = calcul_consistance(sigma_dom, ligue)
    consistance_ext = calcul_consistance(sigma_ext, ligue)

    # Alerte volatilité
    niveau_alerte, ratio = detecter_alerte_volatilite(fusion["sigma_final"], ligue)

    # Recommandation de stake
    #   - NORMAL → multiplicateur 1.0
    #   - ATTENTION → 0.75
    #   - ELEVEE → 0.50
    if niveau_alerte == "ELEVEE":
        multiplicateur_stake = 0.50
        message_alerte = "Volatilite elevee - stake reduit de 50%"
    elif niveau_alerte == "ATTENTION":
        multiplicateur_stake = 0.75
        message_alerte = "Volatilite moderee - stake reduit de 25%"
    else:
        multiplicateur_stake = 1.00
        message_alerte = "Volatilite normale"

    # Bonus : si les 2 équipes sont très régulières → bonus stake
    if consistance_dom is not None and consistance_ext is not None:
        if consistance_dom >= 0.75 and consistance_ext >= 0.75:
            multiplicateur_stake = min(multiplicateur_stake * 1.10, 1.00)
            message_alerte = "Equipes regulieres - confiance renforcee"

    return {
        "sigma_dom": sigma_dom,
        "sigma_ext": sigma_ext,
        "sigma_match": fusion["sigma_match"],
        "sigma_ligue": fusion["sigma_ligue"],
        "sigma_final": fusion["sigma_final"],
        "methode": fusion["methode"],
        "consistance_dom": consistance_dom,
        "consistance_ext": consistance_ext,
        "label_consistance_dom": label_consistance(consistance_dom),
        "label_consistance_ext": label_consistance(consistance_ext),
        "niveau_alerte": niveau_alerte,
        "ratio_volatilite": ratio,
        "multiplicateur_stake": round(multiplicateur_stake, 2),
        "message_alerte": message_alerte,
    }


# =========================================================
# 7. PARSER le SIGMA MT/QUART (proportionnel)
# =========================================================
def sigma_mt_depuis_ft(sigma_ft):
    """Sigma mi-temps ≈ 0.70 × sigma FT."""
    return round(sigma_ft * 0.70, 2)


def sigma_quart_depuis_ft(sigma_ft):
    """Sigma quart-temps ≈ 0.52 × sigma FT."""
    return round(sigma_ft * 0.52, 2)
