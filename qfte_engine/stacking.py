"""
qfte_engine/stacking.py
-----------------------
META-ENSEMBLE STACKING - QFTE V23.0

Combine plusieurs modeles de prediction en un meta-modele adaptatif.
- Consensus Score (accord entre modeles)
- Adaptive Weighting (poids selon contexte)
- Prediction Confidence Score (PCS)
- Ajustement de fiabilite
"""

import math


# =========================================================
# 1. STATISTIQUES DE BASE
# =========================================================
def moyenne(valeurs):
    v = [x for x in valeurs if x is not None]
    if not v:
        return 0.0
    return sum(v) / len(v)


def ecart_type(valeurs):
    v = [x for x in valeurs if x is not None]
    if len(v) < 2:
        return 0.0
    m = moyenne(v)
    variance = sum((x - m) ** 2 for x in v) / len(v)
    return math.sqrt(variance)


# =========================================================
# 2. CONSENSUS SCORE
# =========================================================
def calculer_consensus(probas_liste):
    """
    Mesure a quel point plusieurs modeles s'accordent.
    Retourne un score entre 0 et 1.
    """
    valides = [p for p in probas_liste if p is not None]
    if len(valides) < 2:
        return {
            "consensus": 0.5,
            "ecart_type": 0.0,
            "label": "INCONNU",
            "interpretation": "Pas assez de modeles",
        }

    et = ecart_type(valides)

    # Consensus : 1 si et = 0, decroit avec l'ecart-type
    # Seuil : un ecart-type de 0.10 = consensus 0
    consensus = 1.0 - min(et / 0.10, 1.0)
    consensus = round(max(min(consensus, 1.0), 0.0), 3)

    if consensus >= 0.90:
        label = "UNANIMES"
        interp = "Tous les modeles s'accordent - prediction tres fiable"
    elif consensus >= 0.75:
        label = "COHERENTS"
        interp = "Modeles coherents - legers desaccords"
    elif consensus >= 0.50:
        label = "DIVERGENTS"
        interp = "Modeles divergents - prudence"
    else:
        label = "CONTRADICTOIRES"
        interp = "Modeles en contradiction - prediction incertaine"

    return {
        "consensus": consensus,
        "ecart_type": round(et, 4),
        "label": label,
        "interpretation": interp,
    }


# =========================================================
# 3. POIDS ADAPTATIFS
# =========================================================
def calculer_poids_adaptatifs(contexte):
    """
    Calcule les poids des 4 modeles selon le contexte.

    Parametres de contexte :
      - volatilite : sigma (bas = match previsible, haut = volatil)
      - ecart_forces : difference de force entre les 2 equipes
      - ligue : nom de la ligue
      - forensics_sharpe : score Sharpe Signal (optionnel)
    """
    volatilite = contexte.get("volatilite", 0.5)  # normalise 0-1
    ecart_forces = contexte.get("ecart_forces", 0.5)  # 0 = equilibre, 1 = desequilibre
    ligue = contexte.get("ligue", "autre")
    forensics_sharpe = contexte.get("forensics_sharpe", 0.0)

    # Poids de base (equilibres)
    w_poisson = 0.25
    w_dc = 0.25
    w_mc = 0.25
    w_bayes = 0.25

    # Ajustement selon volatilite
    if volatilite > 0.7:
        # Haute volatilite -> plus de Monte Carlo
        w_mc += 0.15
        w_poisson -= 0.10
        w_dc -= 0.05
    elif volatilite < 0.3:
        # Basse volatilite -> plus de Poisson et DC
        w_poisson += 0.10
        w_dc += 0.10
        w_mc -= 0.10
        w_bayes -= 0.10

    # Ajustement selon ecart de forces
    if ecart_forces > 0.7:
        # Match desequilibre -> Monte Carlo et Bayesien mieux
        w_mc += 0.05
        w_bayes += 0.05
        w_poisson -= 0.05
        w_dc -= 0.05
    elif ecart_forces < 0.3:
        # Match equilibre -> Bayesiens (stabilite)
        w_bayes += 0.10
        w_poisson -= 0.05
        w_dc -= 0.05

    # Ajustement selon ligue
    if ligue in ["nba", "euroleague"]:
        # Basket : Monte Carlo privilegie
        w_mc += 0.05
        w_poisson -= 0.05
    elif ligue in ["premier_league", "bundesliga"]:
        # Foot : DC privilegie
        w_dc += 0.05
        w_mc -= 0.05

    # Ajustement selon forensics
    if forensics_sharpe > 0.5:
        # Sharp signal -> Monte Carlo (extrêmes)
        w_mc += 0.05
        w_poisson -= 0.05

    # Normalisation (somme = 1)
    total = w_poisson + w_dc + w_mc + w_bayes
    if total > 0:
        w_poisson /= total
        w_dc /= total
        w_mc /= total
        w_bayes /= total

    return {
        "w_poisson": round(w_poisson, 3),
        "w_dc": round(w_dc, 3),
        "w_mc": round(w_mc, 3),
        "w_bayes": round(w_bayes, 3),
        "contexte": {
            "volatilite": volatilite,
            "ecart_forces": ecart_forces,
            "ligue": ligue,
            "forensics_sharpe": forensics_sharpe,
        },
  }



# =========================================================
# 4. COMBINAISON DES PREDICTIONS
# =========================================================
def combiner_predictions(p1_poisson, p1_dc, p1_mc, p1_bayes, poids):
    """
    Combine 4 predictions avec les poids adaptatifs.
    Retourne la probabilite finale.
    """
    probas = [p1_poisson, p1_dc, p1_mc, p1_bayes]
    poids_liste = [poids["w_poisson"], poids["w_dc"], poids["w_mc"], poids["w_bayes"]]

    # Filtrer les None
    valides = []
    poids_valides = []
    for p, w in zip(probas, poids_liste):
        if p is not None:
            valides.append(p)
            poids_valides.append(w)

    if not valides:
        return 0.0

    # Normaliser les poids des modeles valides
    total_poids = sum(poids_valides)
    if total_poids <= 0:
        return moyenne(valides)

    p_final = sum(p * w for p, w in zip(valides, poids_valides)) / total_poids
    return round(p_final, 4)


# =========================================================
# 5. PREDICTION CONFIDENCE SCORE (PCS)
# =========================================================
def calculer_pcs(consensus, ecart_type_probas, forensics_sharpe=0.0):
    """
    Score global de confiance de la prediction.
    Combine consensus, dispersion et alignement forensics.

    Retourne un score entre 0 et 1.
    """
    # Facteur consensus (0-1)
    f_consensus = consensus

    # Facteur dispersion (inverse)
    f_dispersion = 1.0 - min(ecart_type_probas / 0.15, 1.0)

    # Facteur forensics (alignement)
    # Si sharpe positif -> aligne (bonus)
    # Si sharpe negatif -> desaligne (malus)
    f_forensics = 0.5 + (forensics_sharpe * 0.5)
    f_forensics = max(min(f_forensics, 1.0), 0.0)

    # PCS : moyenne ponderee
    pcs = 0.50 * f_consensus + 0.30 * f_dispersion + 0.20 * f_forensics
    pcs = round(max(min(pcs, 1.0), 0.0), 3)

    if pcs >= 0.85:
        label = "TRES HAUTE"
    elif pcs >= 0.70:
        label = "HAUTE"
    elif pcs >= 0.55:
        label = "MOYENNE"
    elif pcs >= 0.40:
        label = "FAIBLE"
    else:
        label = "TRES FAIBLE"

    return {
        "pcs": pcs,
        "label": label,
        "f_consensus": round(f_consensus, 3),
        "f_dispersion": round(f_dispersion, 3),
        "f_forensics": round(f_forensics, 3),
    }


# =========================================================
# 6. AJUSTEMENT DE FIABILITE VIA PCS
# =========================================================
def ajuster_fiabilite_pcs(fiabilite, pcs):
    """
    Ajuste la fiabilite d'un pari selon le PCS.
    - PCS eleve : +0.05 max
    - PCS faible : -0.08 max
    """
    score_pcs = pcs["pcs"]

    # Reference : PCS = 0.70 (neutre)
    ecart = score_pcs - 0.70

    if ecart >= 0.15:
        ajust = 0.05
    elif ecart >= 0.05:
        ajust = 0.02
    elif ecart >= -0.05:
        ajust = 0.0
    elif ecart >= -0.15:
        ajust = -0.03
    else:
        ajust = -0.08

    nouvelle = fiabilite + ajust
    return round(max(min(nouvelle, 1.0), 0.0), 3)


# =========================================================
# 7. FONCTION PRINCIPALE — META-ENSEMBLE
# =========================================================
def analyser_meta_ensemble(
    probas_poisson, probas_dc, probas_mc, probas_bayes,
    contexte
):
    """
    Orchestre tout le Meta-Ensemble Stacking.

    Parametres :
      - probas_poisson : dict {p1, px, p2} ou None
      - probas_dc : dict {p1, px, p2} ou None
      - probas_mc : dict {p1, px, p2} ou None
      - probas_bayes : dict {p1, px, p2} ou None
      - contexte : dict avec volatilite, ecart_forces, ligue, forensics_sharpe

    Retourne un dict complet avec consensus, poids, P_final et PCS.
    """
    # Extraire les P(1) de chaque modele
    p1_poisson = probas_poisson.get("p1") if probas_poisson else None
    p1_dc = probas_dc.get("p1") if probas_dc else None
    p1_mc = probas_mc.get("p1") if probas_mc else None
    p1_bayes = probas_bayes.get("p1") if probas_bayes else None

    # Extraire les P(X) et P(2)
    px_poisson = probas_poisson.get("px") if probas_poisson else None
    px_dc = probas_dc.get("px") if probas_dc else None
    px_mc = probas_mc.get("px") if probas_mc else None
    px_bayes = probas_bayes.get("px") if probas_bayes else None

    p2_poisson = probas_poisson.get("p2") if probas_poisson else None
    p2_dc = probas_dc.get("p2") if probas_dc else None
    p2_mc = probas_mc.get("p2") if probas_mc else None
    p2_bayes = probas_bayes.get("p2") if probas_bayes else None

    # 1. Consensus (moyenne des 3 issues)
    consensus_1 = calculer_consensus([p1_poisson, p1_dc, p1_mc, p1_bayes])
    consensus_x = calculer_consensus([px_poisson, px_dc, px_mc, px_bayes])
    consensus_2 = calculer_consensus([p2_poisson, p2_dc, p2_mc, p2_bayes])

    # Consensus global : moyenne ponderee (P(1) pese plus)
    consensus_global = round(
        consensus_1["consensus"] * 0.5 +
        consensus_x["consensus"] * 0.25 +
        consensus_2["consensus"] * 0.25,
        3
    )

    # 2. Poids adaptatifs
    poids = calculer_poids_adaptatifs(contexte)

    # 3. Combinaison des predictions
    p1_final = combiner_predictions(p1_poisson, p1_dc, p1_mc, p1_bayes, poids)
    px_final = combiner_predictions(px_poisson, px_dc, px_mc, px_bayes, poids)
    p2_final = combiner_predictions(p2_poisson, p2_dc, p2_mc, p2_bayes, poids)

    # Normalisation (somme = 1)
    total = p1_final + px_final + p2_final
    if total > 0:
        p1_final = round(p1_final / total, 4)
        px_final = round(px_final / total, 4)
        p2_final = round(p2_final / total, 4)

    # 4. Ecart-type global des predictions
    et_global = ecart_type([p1_poisson, p1_dc, p1_mc, p1_bayes, px_poisson, px_dc, px_mc, px_bayes, p2_poisson, p2_dc, p2_mc, p2_bayes])

    # 5. PCS
    forensics_sharpe = contexte.get("forensics_sharpe", 0.0)
    pcs = calculer_pcs(consensus_global, et_global, forensics_sharpe)

    return {
        "disponible": True,
        "consensus_global": consensus_global,
        "consensus_1": consensus_1,
        "consensus_x": consensus_x,
        "consensus_2": consensus_2,
        "poids": poids,
        "p1_final": p1_final,
        "px_final": px_final,
        "p2_final": p2_final,
        "ecart_type_global": round(et_global, 4),
        "pcs": pcs,
        "probas_sources": {
            "poisson": probas_poisson,
            "dc": probas_dc,
            "mc": probas_mc,
            "bayes": probas_bayes,
        },
  }
