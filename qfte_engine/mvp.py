"""
qfte_engine/mvp.py
------------------
Moteur QFTE V23.0 - MVP complet avec Handicap Asiatique.
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
# 2. HANDICAP ASIATIQUE
# =========================================================
def proba_handicap_dom(matrix, hcp):
    """
    Probabilité de gagner le handicap pour l'équipe domicile.
    Retourne (p_gain, p_rembourse).
    - hcp négatif → l'équipe domicile doit gagner par plus que |hcp|
    """
    p_gain = 0.0
    p_remb = 0.0
    for (i, j), p in matrix.items():
        marge = i - j
        seuil = -hcp  # ex: hcp=-1 → seuil=1
        if marge > seuil:
            p_gain += p
        elif marge == seuil and abs(seuil - round(seuil)) < 1e-9:
            # Handicap entier → remboursement si marge = seuil
            p_remb += p
    return p_gain, p_remb


def proba_handicap_ext(matrix, hcp):
    """
    Probabilité de gagner le handicap pour l'équipe extérieur.
    hcp positif → l'équipe ext doit perdre par moins que hcp
    """
    p_gain = 0.0
    p_remb = 0.0
    for (i, j), p in matrix.items():
        marge = j - i  # marge ext
        seuil = -hcp
        if marge > seuil:
            p_gain += p
        elif marge == seuil and abs(seuil - round(seuil)) < 1e-9:
            p_remb += p
    return p_gain, p_remb


def calcul_handicap_complet(matrix, handicap_lignes):
    """
    Prend une liste de dicts :
      {"hcp_dom": -0.5, "cote_dom": 1.90, "hcp_ext": 0.5, "cote_ext": 1.95}
    Retourne une liste de résultats par ligne.
    """
    resultats = []
    for ligne in handicap_lignes:
        hcp_dom = ligne.get("hcp_dom")
        hcp_ext = ligne.get("hcp_ext")
        cote_dom = ligne.get("cote_dom")
        cote_ext = ligne.get("cote_ext")

        # Côté domicile
        if hcp_dom is not None and cote_dom:
            p_gain, p_remb = proba_handicap_dom(matrix, hcp_dom)
            # Probabilité effective = p_gain + 0.5 * p_remb
            p_eff = p_gain + 0.5 * p_remb
            ev = compute_ev(p_eff, cote_dom) if cote_dom > 0 else 0.0
            fiab = compute_reliability(p_eff, cote_dom, ev)
            passe, raisons = appliquer_filtres_discipline(p_eff, cote_dom, ev, fiab)
            dec, niv = classify_decision(fiab, ev)
            stake = compute_stake(p_eff, cote_dom, fiab, ev) if passe else 0.0
            resultats.append({
                "hcp": hcp_dom,
                "cible": "Domicile",
                "p_gain": round(p_gain, 4),
                "p_remb": round(p_remb, 4),
                "p": round(p_eff, 4),
                "cote": cote_dom,
                "ev": round(ev, 4),
                "fiabilite": fiab,
                "passe_filtres": passe,
                "raisons_rejet": raisons,
                "decision": dec,
                "niveau": niv,
                "stake": stake,
            })

        # Côté extérieur
        if hcp_ext is not None and cote_ext:
            p_gain, p_remb = proba_handicap_ext(matrix, hcp_ext)
            p_eff = p_gain + 0.5 * p_remb
            ev = compute_ev(p_eff, cote_ext) if cote_ext > 0 else 0.0
            fiab = compute_reliability(p_eff, cote_ext, ev)
            passe, raisons = appliquer_filtres_discipline(p_eff, cote_ext, ev, fiab)
            dec, niv = classify_decision(fiab, ev)
            stake = compute_stake(p_eff, cote_ext, fiab, ev) if passe else 0.0
            resultats.append({
                "hcp": hcp_ext,
                "cible": "Extérieur",
                "p_gain": round(p_gain, 4),
                "p_remb": round(p_remb, 4),
                "p": round(p_eff, 4),
                "cote": cote_ext,
                "ev": round(ev, 4),
                "fiabilite": fiab,
                "passe_filtres": passe,
                "raisons_rejet": raisons,
                "decision": dec,
                "niveau": niv,
                "stake": stake,
            })

    return resultats


# =========================================================
# 3. MOYENNES
# =========================================================
def moy(valeurs):
    v = [x for x in valeurs if x is not None]
    if not v:
        return 0.0
    return sum(v) / len(v)


# =========================================================
# 4. AJUSTEMENTS CONTEXTUELS
# =========================================================
def facteur_meteo(meteo):
    return {"normale": 1.00, "pluie": 0.90, "neige": 0.85,
            "chaleur_extreme": 0.90, "vent_fort": 0.92}.get(meteo, 1.00)


def facteur_enjeu(enjeu):
    return {"normal": 1.00, "derby": 0.95, "finale": 0.92,
            "fin_saison": 0.97, "relegation": 0.95}.get(enjeu, 1.00)


def facteur_blessures(a):
    return 0.85 if a else 1.00


def facteur_fatigue(a):
    return 0.90 if a else 1.00


def facteur_classement(pos_dom, pos_ext, total_equipes):
    if pos_dom is None or pos_ext is None or total_equipes is None or total_equipes <= 1:
        return (1.0, 1.0)
    ecart = (pos_ext - pos_dom) / total_equipes
    ecart = max(min(ecart, 1.0), -1.0)
    ajust = ecart * 0.15
    return (round(1.0 + ajust, 3), round(1.0 - ajust, 3))


def facteur_ht(matchs):
    m_ht = [m for m in matchs if m.get("ht_bp") is not None]
    if not m_ht:
        return 1.00
    total_bp = sum(m["bp"] for m in m_ht)
    total_ht_bp = sum(m["ht_bp"] for m in m_ht)
    if total_bp == 0:
        return 1.00
    ratio_2e = (total_bp - total_ht_bp) / total_bp
    ecart = (ratio_2e - 0.5) * 0.20
    ecart = max(min(ecart, 0.05), -0.05)
    return 1.00 + ecart


def facteur_forme_recente(matchs):
    if len(matchs) < 5:
        return 1.00
    points = []
    for m in matchs:
        diff = m["bp"] - m["bc"]
        points.append(3 if diff > 0 else (1 if diff == 0 else 0))
    moy_5 = sum(points) / len(points)
    moy_3 = sum(points[:3]) / 3.0
    ecart = max(min((moy_3 - moy_5) / 3.0, 1.0), -1.0)
    return 1.00 + ecart * 0.05


def facteur_h2h(h2h_matchs):
    if not h2h_matchs:
        return (1.00, 1.00)
    v = 0
    for m in h2h_matchs:
        if m["bp"] > m["bc"]:
            v += 1
        elif m["bp"] < m["bc"]:
            v -= 1
    ratio = v / len(h2h_matchs)
    ajust = ratio * 0.08
    return (round(1.0 + ajust, 3), round(1.0 - ajust, 3))


# =========================================================
# 5. CALCUL DES LAMBDAS
# =========================================================
def compute_lambdas(
    home_ctx, home_glob, away_ctx, away_glob, h2h_matchs,
    meteo, enjeu, blessures_dom, blessures_ext, fatigue_dom, fatigue_ext,
    pos_dom=None, pos_ext=None, total_equipes=None
):
    home_bp_ctx = moy([m["bp"] for m in home_ctx])
    home_bc_ctx = moy([m["bc"] for m in home_ctx])
    away_bp_ctx = moy([m["bp"] for m in away_ctx])
    away_bc_ctx = moy([m["bc"] for m in away_ctx])

    home_bp_glob = moy([m["bp"] for m in home_glob]) if home_glob else home_bp_ctx
    home_bc_glob = moy([m["bc"] for m in home_glob]) if home_glob else home_bc_ctx
    away_bp_glob = moy([m["bp"] for m in away_glob]) if away_glob else away_bp_ctx
    away_bc_glob = moy([m["bc"] for m in away_glob]) if away_glob else away_bc_ctx

    home_bp = 0.7 * home_bp_ctx + 0.3 * home_bp_glob
    home_bc = 0.7 * home_bc_ctx + 0.3 * home_bc_glob
    away_bp = 0.7 * away_bp_ctx + 0.3 * away_bp_glob
    away_bc = 0.7 * away_bc_ctx + 0.3 * away_bc_glob

    lambda_home = (home_bp + away_bc) / 2.0
    lambda_away = (away_bp + home_bc) / 2.0

    f_ht_home = facteur_ht(home_ctx)
    f_ht_away = facteur_ht(away_ctx)
    lambda_home *= f_ht_home
    lambda_away *= f_ht_away

    f_forme_home = facteur_forme_recente(home_ctx)
    f_forme_away = facteur_forme_recente(away_ctx)
    lambda_home *= f_forme_home
    lambda_away *= f_forme_away

    f_class_home, f_class_away = facteur_classement(pos_dom, pos_ext, total_equipes)
    lambda_home *= f_class_home
    lambda_away *= f_class_away

    f_h2h_home, f_h2h_away = facteur_h2h(h2h_matchs)
    lambda_home *= f_h2h_home
    lambda_away *= f_h2h_away

    f_commun = facteur_meteo(meteo) * facteur_enjeu(enjeu)
    lambda_home *= f_commun
    lambda_away *= f_commun

    lambda_home *= facteur_blessures(blessures_dom)
    lambda_away *= facteur_blessures(blessures_ext)
    lambda_home *= facteur_fatigue(fatigue_dom)
    lambda_away *= facteur_fatigue(fatigue_ext)

    lambda_home = max(lambda_home, 0.1)
    lambda_away = max(lambda_away, 0.1)

    return lambda_home, lambda_away, {
        "home_bp_ctx": round(home_bp_ctx, 2),
        "home_bp_glob": round(home_bp_glob, 2),
        "away_bp_ctx": round(away_bp_ctx, 2),
        "away_bp_glob": round(away_bp_glob, 2),
        "f_ht_home": round(f_ht_home, 3),
        "f_ht_away": round(f_ht_away, 3),
        "f_forme_home": round(f_forme_home, 3),
        "f_forme_away": round(f_forme_away, 3),
        "f_class_home": f_class_home,
        "f_class_away": f_class_away,
        "f_h2h_home": f_h2h_home,
        "f_h2h_away": f_h2h_away,
        "f_meteo": round(facteur_meteo(meteo), 3),
        "f_enjeu": round(facteur_enjeu(enjeu), 3),
        "f_bless_dom": facteur_blessures(blessures_dom),
        "f_bless_ext": facteur_blessures(blessures_ext),
        "f_fatigue_dom": facteur_fatigue(fatigue_dom),
        "f_fatigue_ext": facteur_fatigue(fatigue_ext),
        "f_commun": round(f_commun, 3),
    }


# =========================================================
# 6. EV + FIABILITÉ + STAKE
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
# 7. FILTRES + CLASSIFICATION
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
# 8. ANALYSE COMPLÈTE
# =========================================================
def analyser_match_football(
    home_ctx, home_glob, away_ctx, away_glob,
    open_1, open_x, open_2,
    curr_1, curr_x, curr_2,
    meteo="normale", enjeu="normal",
    blessures_dom=False, blessures_ext=False,
    fatigue_dom=False, fatigue_ext=False,
    h2h_matchs=None,
    handicap_lignes=None,
    pos_dom=None, pos_ext=None, total_equipes=None
):
    if h2h_matchs is None:
        h2h_matchs = []
    if handicap_lignes is None:
        handicap_lignes = []

    lambda_home, lambda_away, details = compute_lambdas(
        home_ctx, home_glob, away_ctx, away_glob, h2h_matchs,
        meteo, enjeu, blessures_dom, blessures_ext, fatigue_dom, fatigue_ext,
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
        {"selection": "1 (Domicile)",  "p": p1, "cote": curr_1, "ev": ev1, "fiabilite": f1, "type": "1X2"},
        {"selection": "X (Nul)",       "p": px, "cote": curr_x, "ev": evx, "fiabilite": fx, "type": "1X2"},
        {"selection": "2 (Extérieur)", "p": p2, "cote": curr_2, "ev": ev2, "fiabilite": f2, "type": "1X2"},
    ]

    for c in candidats:
        passe, raisons = appliquer_filtres_discipline(c["p"], c["cote"], c["ev"], c["fiabilite"])
        c["passe_filtres"] = passe
        c["raisons_rejet"] = raisons
        dec, niv = classify_decision(c["fiabilite"], c["ev"])
        c["decision"] = dec
        c["niveau"] = niv
        c["stake"] = compute_stake(c["p"], c["cote"], c["fiabilite"], c["ev"]) if passe else 0.0

    # Handicap
    handicap_resultats = calcul_handicap_complet(matrix, handicap_lignes)

    # Fusion pour trouver le meilleur pari global
    tous_candidats = list(candidats)
    for h in handicap_resultats:
        h["selection"] = f"Hcp {h['hcp']:+g} ({h['cible']})"
        h["type"] = "Handicap"
        tous_candidats.append(h)

    tous_candidats.sort(key=lambda x: x["fiabilite"], reverse=True)

    pari_retenu = None
    for c in tous_candidats:
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
        "handicap_resultats": handicap_resultats,
        "pari_retenu": pari_retenu,
        "top_3_scores": top_3,
            }
