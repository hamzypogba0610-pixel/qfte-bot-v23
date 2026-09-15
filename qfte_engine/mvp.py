"""
qfte_engine/mvp.py
------------------
Moteur QFTE V23.0 - MVP avec ajustements contextuels, HT, global, classement.
"""

import math


# =========================================================
# 1. POISSON
# =========================================================
def poisson_pmf(k, lam):
    if lam <= 0:
        lam = 0.01
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


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
# 2. MOYENNES
# =========================================================
def moy(valeurs):
    v = [x for x in valeurs if x is not None]
    if not v:
        return 0.0
    return sum(v) / len(v)


# =========================================================
# 3. AJUSTEMENTS CONTEXTUELS
# =========================================================
def facteur_meteo(meteo):
    return {
        "normale": 1.00,
        "pluie": 0.90,
        "neige": 0.85,
        "chaleur_extreme": 0.90,
        "vent_fort": 0.92,
    }.get(meteo, 1.00)


def facteur_enjeu(enjeu):
    return {
        "normal": 1.00,
        "derby": 0.95,
        "finale": 0.92,
        "fin_saison": 0.97,
        "relegation": 0.95,
    }.get(enjeu, 1.00)


def facteur_blessures(a_blessures):
    return 0.85 if a_blessures else 1.00


def facteur_classement(pos_dom, pos_ext, total_equipes):
    """
    Retourne (facteur_home, facteur_away) basé sur l'écart de classement.
    Plafonné à ±15%.
    """
    if pos_dom is None or pos_ext is None or total_equipes is None or total_equipes <= 1:
        return (1.0, 1.0)

    # Écart normalisé : > 0 → domicile mieux classé
    ecart = (pos_ext - pos_dom) / total_equipes
    ecart = max(min(ecart, 1.0), -1.0)  # borne [-1, +1]

    # Amplitude max : 15%
    ajust = ecart * 0.15

    f_home = 1.0 + ajust
    f_away = 1.0 - ajust
    return (round(f_home, 3), round(f_away, 3))


def facteur_ht(matchs):
    """
    Analyse les HT pour détecter le profil de l'équipe.
    - Si l'équipe marque bcp en 2e MT → bonus (slow starter)
    - Si elle marque bcp en 1re MT → neutre
    Retourne un facteur entre 0.95 et 1.05.
    """
    matchs_avec_ht = [m for m in matchs if m.get("ht_bp") is not None]
    if not matchs_avec_ht:
        return 1.00

    total_bp = sum(m["bp"] for m in matchs_avec_ht)
    total_ht_bp = sum(m["ht_bp"] for m in matchs_avec_ht)

    if total_bp == 0:
        return 1.00

    ratio_2e_mt = (total_bp - total_ht_bp) / total_bp  # > 0.5 = finit fort

    # Écart autour de 0.5, plafonné à ±5%
    ecart = (ratio_2e_mt - 0.5) * 0.20
    ecart = max(min(ecart, 0.05), -0.05)
    return 1.00 + ecart


# =========================================================
# 4. CALCUL DES LAMBDAS AMÉLIORÉ
# =========================================================
def compute_lambdas(
    home_ctx, home_glob, away_ctx, away_glob,
    meteo, enjeu, blessures_dom, blessures_ext,
    pos_dom=None, pos_ext=None, total_equipes=None
):
    # Moyennes contextuelles
    home_bp_ctx = moy([m["bp"] for m in home_ctx])
    home_bc_ctx = moy([m["bc"] for m in home_ctx])
    away_bp_ctx = moy([m["bp"] for m in away_ctx])
    away_bc_ctx = moy([m["bc"] for m in away_ctx])

    # Moyennes globales (fallback si vide)
    home_bp_glob = moy([m["bp"] for m in home_glob]) if home_glob else home_bp_ctx
    home_bc_glob = moy([m["bc"] for m in home_glob]) if home_glob else home_bc_ctx
    away_bp_glob = moy([m["bp"] for m in away_glob]) if away_glob else away_bp_ctx
    away_bc_glob = moy([m["bc"] for m in away_glob]) if away_glob else away_bc_ctx

    # Fusion 70% contexte / 30% global
    home_bp = 0.7 * home_bp_ctx + 0.3 * home_bp_glob
    home_bc = 0.7 * home_bc_ctx + 0.3 * home_bc_glob
    away_bp = 0.7 * away_bp_ctx + 0.3 * away_bp_glob
    away_bc = 0.7 * away_bc_ctx + 0.3 * away_bc_glob

    # λ de base
    lambda_home = (home_bp + away_bc) / 2.0
    lambda_away = (away_bp + home_bc) / 2.0

    # Ajustement HT (profil de chaque équipe)
    f_ht_home = facteur_ht(home_ctx)
    f_ht_away = facteur_ht(away_ctx)
    lambda_home *= f_ht_home
    lambda_away *= f_ht_away

    # Ajustement classement
    f_class_home, f_class_away = facteur_classement(pos_dom, pos_ext, total_equipes)
    lambda_home *= f_class_home
    lambda_away *= f_class_away

    # Ajustement météo + enjeu (sur les 2 équipes)
    f_commun = facteur_meteo(meteo) * facteur_enjeu(enjeu)
    lambda_home *= f_commun
    lambda_away *= f_commun

    # Ajustement blessures (individuel)
    lambda_home *= facteur_blessures(blessures_dom)
    lambda_away *= facteur_blessures(blessures_ext)

    # Sécurité
    lambda_home = max(lambda_home, 0.1)
    lambda_away = max(lambda_away, 0.1)

    return lambda_home, lambda_away, {
        "home_bp_ctx": round(home_bp_ctx, 2),
        "home_bp_glob": round(home_bp_glob, 2),
        "away_bp_ctx": round(away_bp_ctx, 2),
        "away_bp_glob": round(away_bp_glob, 2),
        "f_ht_home": round(f_ht_home, 3),
        "f_ht_away": round(f_ht_away, 3),
        "f_class_home": f_class_home,
        "f_class_away": f_class_away,
        "f_meteo": round(facteur_meteo(meteo), 3),
        "f_enjeu": round(facteur_enjeu(enjeu), 3),
        "f_bless_dom": facteur_blessures(blessures_dom),
        "f_bless_ext": facteur_blessures(blessures_ext),
        "f_commun": round(f_commun, 3),
    }


# =========================================================
# 5. EV + FIABILITÉ + STAKE
# =========================================================
def compute_ev(p, cote):
    if cote <= 0:
        return 0.0
    return p * cote - 1.0


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


def compute_stake(p, cote, fiabilite, ev):
    if ev <= 0 or cote <= 1:
        return 0.0
    f_star = (p * cote - 1.0) / (cote - 1.0)
    if fiabilite >= 0.85:
        lam, plafond = 0.30, 1.5
    elif fiabilite >= 0.75:
        lam, plafond = 0.25, 1.0
    elif fiabilite >= 0.65:
        lam, plafond = 0.15, 0.5
    else:
        lam, plafond = 0.10, 0.25
    stake = min(f_star * lam * 100, plafond)
    return round(max(stake, 0.0), 2)


# =========================================================
# 6. FILTRES + CLASSIFICATION
# =========================================================
SEUIL_FIABILITE = 0.75
SEUIL_VALUE_1X2 = 0.05
SEUIL_CONFIANCE = 0.70


def appliquer_filtres_discipline(p, cote, ev, fiabilite):
    raisons = []
    if fiabilite < SEUIL_FIABILITE:
        raisons.append(f"Fiabilité {fiabilite} < {SEUIL_FIABILITE}")
    if ev < SEUIL_VALUE_1X2:
        raisons.append(f"Value {ev*100:.2f}% < {SEUIL_VALUE_1X2*100:.0f}%")
    if p < SEUIL_CONFIANCE:
        raisons.append(f"Confiance {p*100:.2f}% < {SEUIL_CONFIANCE*100:.0f}%")
    return (len(raisons) == 0, raisons)


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
# 7. ANALYSE COMPLÈTE
# =========================================================
def analyser_match_football(
    home_ctx, home_glob, away_ctx, away_glob,
    open_1, open_x, open_2,
    curr_1, curr_x, curr_2,
    meteo="normale", enjeu="normal",
    blessures_dom=False, blessures_ext=False,
    pos_dom=None, pos_ext=None, total_equipes=None
):
    lambda_home, lambda_away, details = compute_lambdas(
        home_ctx, home_glob, away_ctx, away_glob,
        meteo, enjeu, blessures_dom, blessures_ext,
        pos_dom, pos_ext, total_equipes
    )

    matrix = compute_score_matrix(lambda_home, lambda_away)
    p1, px, p2 = compute_1x2(matrix)

    ev1 = compute_ev(p1, curr_1)
    evx = compute_ev(px, curr_x) if curr_x > 0 else -1.0
    ev2 = compute_ev(p2, curr_2)

    f1 = compute_reliability(p1, curr_1, ev1)
    fx = compute_reliability(px, curr_x, evx) if curr_x > 0 else 0.0
    f2 = compute_reliability(p2, curr_2, ev2)

    candidats = [
        {"selection": "1 (Domicile)",  "p": p1, "cote": curr_1, "ev": ev1, "fiabilite": f1},
        {"selection": "X (Nul)",       "p": px, "cote": curr_x, "ev": evx, "fiabilite": fx},
        {"selection": "2 (Extérieur)", "p": p2, "cote": curr_2, "ev": ev2, "fiabilite": f2},
    ]

    for c in candidats:
        passe, raisons = appliquer_filtres_discipline(c["p"], c["cote"], c["ev"], c["fiabilite"])
        c["passe_filtres"] = passe
        c["raisons_rejet"] = raisons
        dec, niv = classify_decision(c["fiabilite"], c["ev"])
        c["decision"] = dec
        c["niveau"] = niv
        c["stake"] = compute_stake(c["p"], c["cote"], c["fiabilite"], c["ev"]) if passe else 0.0

    candidats.sort(key=lambda x: x["fiabilite"], reverse=True)

    pari_retenu = None
    for c in candidats:
        if c["passe_filtres"] and c["stake"] > 0:
            pari_retenu = c
            break

    top_scores = sorted(matrix.items(), key=lambda x: x[1], reverse=True)[:3]
    top_3 = [
        {"rank": i + 1, "score": f"{sc[0]}-{sc[1]}", "probability": round(pr, 4)}
        for i, (sc, pr) in enumerate(top_scores)
    ]

    return {
        "lambda_home": round(lambda_home, 2),
        "lambda_away": round(lambda_away, 2),
        "details": details,
        "p1": round(p1, 4), "px": round(px, 4), "p2": round(p2, 4),
        "ev1": round(ev1, 4), "evx": round(evx, 4), "ev2": round(ev2, 4),
        "f1": f1, "fx": fx, "f2": f2,
        "candidats": candidats,
        "pari_retenu": pari_retenu,
        "top_3_scores": top_3,
    }
