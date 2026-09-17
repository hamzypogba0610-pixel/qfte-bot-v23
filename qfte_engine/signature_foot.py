"""
qfte_engine/signature_foot.py
-----------------------------
QFTE SIGNATURE FOOT V23.0
Temporal Bayesian Dixon-Coles + Monte Carlo

Expose les 4 sous-probas pour le Meta-Ensemble Stacking.
"""

import math
import random


PRIOR_LIGUE = {
    "premier_league": 2.85,
    "liga": 2.60,
    "serie_a": 2.70,
    "bundesliga": 3.15,
    "ligue_1": 2.65,
    "eredivisie": 3.20,
    "primeira": 2.55,
    "championship": 2.60,
    "mls": 2.90,
    "champions_league": 3.00,
    "europa_league": 2.75,
    "conference_league": 2.90,
    "coupe_du_monde": 2.60,
    "euro": 2.50,
    "can": 2.20,
    "ligue_des_champions_caf": 2.30,
    "copa_libertadores": 2.50,
    "autre": 2.70,
}


def get_prior_ligue(ligue):
    if not ligue:
        return 2.70
    return PRIOR_LIGUE.get(ligue, 2.70)


def poisson_pmf(k, lam):
    if lam <= 0:
        lam = 0.01
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def compute_matrice_poisson(lam_h, lam_a, max_goals=8):
    """Matrice Poisson pure (sans correction DC)."""
    matrix = {}
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            matrix[(i, j)] = poisson_pmf(i, lam_h) * poisson_pmf(j, lam_a)
    total = sum(matrix.values())
    if total > 0:
        matrix = {k: v / total for k, v in matrix.items()}
    return matrix


RHO_DEFAULT = -0.05


def tau_dixon_coles(i, j, lam_h, lam_a, rho=RHO_DEFAULT):
    if i == 0 and j == 0:
        return 1.0 - lam_h * lam_a * rho
    elif i == 1 and j == 0:
        return 1.0 + lam_a * rho
    elif i == 0 and j == 1:
        return 1.0 + lam_h * rho
    elif i == 1 and j == 1:
        return 1.0 - rho
    else:
        return 1.0


def compute_matrice_dixon_coles(lam_h, lam_a, max_goals=8, rho=RHO_DEFAULT):
    matrix = {}
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p_poisson = poisson_pmf(i, lam_h) * poisson_pmf(j, lam_a)
            correction = tau_dixon_coles(i, j, lam_h, lam_a, rho)
            matrix[(i, j)] = p_poisson * correction
    total = sum(matrix.values())
    if total > 0:
        matrix = {k: v / total for k, v in matrix.items()}
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


def compute_over_under_dc(matrix, ligne):
    p_over = 0.0
    p_under = 0.0
    p_remb = 0.0
    est_entiere = abs(ligne - round(ligne)) < 1e-9
    for (i, j), p in matrix.items():
        total = i + j
        if est_entiere:
            seuil = int(round(ligne))
            if total > seuil:
                p_over += p
            elif total < seuil:
                p_under += p
            else:
                p_remb += p
        else:
            if total > ligne:
                p_over += p
            else:
                p_under += p
    return p_over, p_under, p_remb


def compute_btts_dc(matrix):
    p_oui = 0.0
    for (i, j), p in matrix.items():
        if i >= 1 and j >= 1:
            p_oui += p
    return p_oui, 1.0 - p_oui


def bayesian_lambda(lambda_observe, prior_ligue_par_equipe, k=3.0, n=5.0):
    if lambda_observe is None or lambda_observe <= 0:
        return prior_ligue_par_equipe
    lam_final = (k * prior_ligue_par_equipe + n * lambda_observe) / (k + n)
    return round(lam_final, 3)


def sample_poisson(lam):
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1
        if k > 50:
            return k


def monte_carlo_simuler(lam_h, lam_a, n=10000):
    compteurs = {
        "victoires_dom": 0,
        "nuls": 0,
        "victoires_ext": 0,
        "total_buts_liste": [],
        "score_1_0": 0,
        "score_0_1": 0,
        "score_1_1": 0,
        "score_0_0": 0,
        "btts_oui": 0,
    }
    for _ in range(n):
        gh = sample_poisson(lam_h)
        ga = sample_poisson(lam_a)
        total = gh + ga
        if gh > ga:
            compteurs["victoires_dom"] += 1
        elif gh == ga:
            compteurs["nuls"] += 1
        else:
            compteurs["victoires_ext"] += 1
        compteurs["total_buts_liste"].append(total)
        if gh == 1 and ga == 0:
            compteurs["score_1_0"] += 1
        if gh == 0 and ga == 1:
            compteurs["score_0_1"] += 1
        if gh == 1 and ga == 1:
            compteurs["score_1_1"] += 1
        if gh == 0 and ga == 0:
            compteurs["score_0_0"] += 1
        if gh >= 1 and ga >= 1:
            compteurs["btts_oui"] += 1
    return compteurs, n


def extraire_probas_mc(compteurs, n):
    return {
        "p1": round(compteurs["victoires_dom"] / n, 4),
        "px": round(compteurs["nuls"] / n, 4),
        "p2": round(compteurs["victoires_ext"] / n, 4),
        "p_1_0": round(compteurs["score_1_0"] / n, 4),
        "p_0_1": round(compteurs["score_0_1"] / n, 4),
        "p_1_1": round(compteurs["score_1_1"] / n, 4),
        "p_0_0": round(compteurs["score_0_0"] / n, 4),
        "p_btts": round(compteurs["btts_oui"] / n, 4),
    }


def compute_over_under_mc(total_buts_liste, ligne):
    n = len(total_buts_liste)
    if n == 0:
        return 0.5, 0.5
    est_entiere = abs(ligne - round(ligne)) < 1e-9
    p_over = 0.0
    p_under = 0.0
    p_remb = 0.0
    for t in total_buts_liste:
        if est_entiere:
            seuil = int(round(ligne))
            if t > seuil:
                p_over += 1
            elif t < seuil:
                p_under += 1
            else:
                p_remb += 1
        else:
            if t > ligne:
                p_over += 1
            else:
                p_under += 1
    return round(p_over / n, 4), round(p_under / n, 4)


def intervalle_confiance_bootstrap(total_buts_liste, ligne, n_boot=500):
    n = len(total_buts_liste)
    if n < 100:
        return None, None, None
    echantillons = []
    for _ in range(n_boot):
        sous_ech = [random.choice(total_buts_liste) for _ in range(n)]
        p_over = sum(1 for t in sous_ech if t > ligne) / n
        echantillons.append(p_over)
    echantillons.sort()
    idx_bas = int(0.025 * n_boot)
    idx_haut = int(0.975 * n_boot)
    p_moy = sum(echantillons) / n_boot
    return round(p_moy, 4), round(echantillons[idx_bas], 4), round(echantillons[idx_haut], 4)


def score_stabilite(p_moy, ic_bas, ic_haut):
    if p_moy is None or ic_bas is None or ic_haut is None or p_moy <= 0:
        return None
    largeur = ic_haut - ic_bas
    stabilite = 1.0 - (largeur / p_moy)
    return round(max(min(stabilite, 1.0), 0.0), 3)


def intervalle_confiance_proba_simple(p, n=10000):
    if p is None or n <= 0:
        return None, None
    se = math.sqrt(p * (1 - p) / n)
    return round(max(p - 1.96 * se, 0.0), 4), round(min(p + 1.96 * se, 1.0), 4)



# =========================================================
# ORCHESTRATEUR SIGNATURE FOOT
# =========================================================
def analyser_signature_foot(
    lambda_home_brut, lambda_away_brut,
    ligue=None, n_mc=10000, rho=RHO_DEFAULT
):
    """
    Orchestre toute la signature foot.

    Retourne les 4 sous-probas (poisson, dc, mc, bayes) pour le stacking.
    """
    prior_total = get_prior_ligue(ligue)
    prior_par_equipe = prior_total / 2.0

    # 1. LAMBDA BRUT (deja ajuste contextuellement en amont)
    lambda_home_brut_val = max(lambda_home_brut, 0.1)
    lambda_away_brut_val = max(lambda_away_brut, 0.1)

    # 2. BAYESIEN
    lambda_home_bayes = bayesian_lambda(lambda_home_brut_val, prior_par_equipe, k=3.0, n=5.0)
    lambda_away_bayes = bayesian_lambda(lambda_away_brut_val, prior_par_equipe, k=3.0, n=5.0)

    # 3. MATRICE POISSON (sur lambda BRUT)
    matrix_poisson = compute_matrice_poisson(lambda_home_brut_val, lambda_away_brut_val, max_goals=8)
    p1_poisson, px_poisson, p2_poisson = compute_1x2(matrix_poisson)

    # 4. MATRICE DIXON-COLES (sur lambda BAYESIEN)
    matrix_dc = compute_matrice_dixon_coles(lambda_home_bayes, lambda_away_bayes, max_goals=8, rho=rho)
    p1_dc, px_dc, p2_dc = compute_1x2(matrix_dc)
    p_btts_oui_dc, p_btts_non_dc = compute_btts_dc(matrix_dc)

    # 5. MONTE CARLO (sur lambda BAYESIEN)
    compteurs, n = monte_carlo_simuler(lambda_home_bayes, lambda_away_bayes, n=n_mc)
    probas_mc = extraire_probas_mc(compteurs, n)

    # 6. BAYESIEN (probas directes, via Poisson sur lambda bayesien)
    matrix_bayes = compute_matrice_poisson(lambda_home_bayes, lambda_away_bayes, max_goals=8)
    p1_bayes, px_bayes, p2_bayes = compute_1x2(matrix_bayes)

    # 7. IC 95% sur les probas MC (1X2)
    ic_p1 = intervalle_confiance_proba_simple(probas_mc["p1"], n)
    ic_px = intervalle_confiance_proba_simple(probas_mc["px"], n)
    ic_p2 = intervalle_confiance_proba_simple(probas_mc["p2"], n)

    # 8. Stabilite
    stab_p1 = score_stabilite(probas_mc["p1"], ic_p1[0], ic_p1[1])
    stab_px = score_stabilite(probas_mc["px"], ic_px[0], ic_px[1])
    stab_p2 = score_stabilite(probas_mc["p2"], ic_p2[0], ic_p2[1])

    return {
        "prior_ligue": prior_total,
        "lambda_home_brut": round(lambda_home_brut_val, 3),
        "lambda_away_brut": round(lambda_away_brut_val, 3),
        "lambda_home_bayesien": lambda_home_bayes,
        "lambda_away_bayesien": lambda_away_bayes,
        "rho": rho,
        "methode": "Dixon-Coles + Bayesian + Monte Carlo",
        "n_simulations": n,

        # Matrice finale (pour handicap et O/U)
        "matrix_dc": matrix_dc,

        # Probas finales Dixon-Coles (utilisees par defaut)
        "p1_dc": round(p1_dc, 4),
        "px_dc": round(px_dc, 4),
        "p2_dc": round(p2_dc, 4),
        "p_btts_oui_dc": round(p_btts_oui_dc, 4),
        "p_btts_non_dc": round(p_btts_non_dc, 4),

        # Probas Monte Carlo
        "probas_mc": probas_mc,

        # 4 SOUS-PROBAS pour le Meta-Ensemble Stacking
        "probas_poisson": {
            "p1": round(p1_poisson, 4),
            "px": round(px_poisson, 4),
            "p2": round(p2_poisson, 4),
        },
        "probas_dc": {
            "p1": round(p1_dc, 4),
            "px": round(px_dc, 4),
            "p2": round(p2_dc, 4),
        },
        "probas_mc": {
            "p1": probas_mc["p1"],
            "px": probas_mc["px"],
            "p2": probas_mc["p2"],
        },
        "probas_bayes": {
            "p1": round(p1_bayes, 4),
            "px": round(px_bayes, 4),
            "p2": round(p2_bayes, 4),
        },

        # IC et stabilite
        "ic_p1": ic_p1,
        "ic_px": ic_px,
        "ic_p2": ic_p2,
        "stab_p1": stab_p1,
        "stab_px": stab_px,
        "stab_p2": stab_p2,

        # Liste totale buts (pour O/U)
        "total_buts_liste": compteurs["total_buts_liste"],
    }


# =========================================================
# UTILITAIRES PUBLICS
# =========================================================
def calculer_over_under_avec_ic(signature_result, ligne, n_boot=500):
    liste = signature_result["total_buts_liste"]
    p_over, p_under = compute_over_under_mc(liste, ligne)
    p_moy, ic_bas, ic_haut = intervalle_confiance_bootstrap(liste, ligne, n_boot=n_boot)
    stabilite = score_stabilite(p_moy, ic_bas, ic_haut)
    return {
        "p_over": p_over,
        "p_under": p_under,
        "ic_over": (ic_bas, ic_haut) if ic_bas is not None else None,
        "stabilite": stabilite,
    }
