"""
qfte_engine/mvp.py
------------------
Moteur QFTE V23.0 - Complet :
1X2 + Handicap + Over/Under + SÉCURITÉ O/U + DÉTECTION DIVERGENCES.
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
# 2. DÉ-MARGEAGE
# =========================================================
def demargeage_proportionnel(cotes):
    """Retourne les probas implicites normalisées d'une liste de cotes."""
    if not cotes or any(c is None or c <= 0 for c in cotes):
        return None
    inv = [1/c for c in cotes]
    total = sum(inv)
    if total <= 0:
        return None
    return [i/total for i in inv]


# =========================================================
# 3. HANDICAP ASIATIQUE
# =========================================================
def proba_handicap_dom(matrix, hcp):
    p_gain = 0.0; p_remb = 0.0
    for (i, j), p in matrix.items():
        marge = i - j; seuil = -hcp
        if marge > seuil: p_gain += p
        elif marge == seuil and abs(seuil - round(seuil)) < 1e-9: p_remb += p
    return p_gain, p_remb


def proba_handicap_ext(matrix, hcp):
    p_gain = 0.0; p_remb = 0.0
    for (i, j), p in matrix.items():
        marge = j - i; seuil = -hcp
        if marge > seuil: p_gain += p
        elif marge == seuil and abs(seuil - round(seuil)) < 1e-9: p_remb += p
    return p_gain, p_remb


def calcul_handicap_complet(matrix, handicap_lignes):
    resultats = []
    for ligne in handicap_lignes:
        hcp_dom = ligne.get("hcp_dom"); hcp_ext = ligne.get("hcp_ext")
        cote_dom = ligne.get("cote_dom"); cote_ext = ligne.get("cote_ext")
        if hcp_dom is not None and cote_dom:
            p_gain, p_remb = proba_handicap_dom(matrix, hcp_dom)
            p_eff = p_gain + 0.5 * p_remb
            ev = compute_ev(p_eff, cote_dom) if cote_dom > 0 else 0.0
            fiab = compute_reliability(p_eff, cote_dom, ev)
            passe, raisons = appliquer_filtres_discipline(p_eff, cote_dom, ev, fiab)
            dec, niv = classify_decision(fiab, ev)
            stake = compute_stake(p_eff, cote_dom, fiab, ev) if passe else 0.0
            resultats.append({
                "hcp": hcp_dom, "cible": "Domicile",
                "p_gain": round(p_gain, 4), "p_remb": round(p_remb, 4),
                "p": round(p_eff, 4), "cote": cote_dom,
                "ev": round(ev, 4), "fiabilite": fiab,
                "passe_filtres": passe, "raisons_rejet": raisons,
                "decision": dec, "niveau": niv, "stake": stake,
            })
        if hcp_ext is not None and cote_ext:
            p_gain, p_remb = proba_handicap_ext(matrix, hcp_ext)
            p_eff = p_gain + 0.5 * p_remb
            ev = compute_ev(p_eff, cote_ext) if cote_ext > 0 else 0.0
            fiab = compute_reliability(p_eff, cote_ext, ev)
            passe, raisons = appliquer_filtres_discipline(p_eff, cote_ext, ev, fiab)
            dec, niv = classify_decision(fiab, ev)
            stake = compute_stake(p_eff, cote_ext, fiab, ev) if passe else 0.0
            resultats.append({
                "hcp": hcp_ext, "cible": "Extérieur",
                "p_gain": round(p_gain, 4), "p_remb": round(p_remb, 4),
                "p": round(p_eff, 4), "cote": cote_ext,
                "ev": round(ev, 4), "fiabilite": fiab,
                "passe_filtres": passe, "raisons_rejet": raisons,
                "decision": dec, "niveau": niv, "stake": stake,
            })
    return resultats


# =========================================================
# 4. OVER / UNDER
# =========================================================
def proba_over_under(matrix, ligne):
    p_over = 0.0; p_under = 0.0; p_remb = 0.0
    est_entiere = abs(ligne - round(ligne)) < 1e-9
    for (i, j), p in matrix.items():
        total = i + j
        if est_entiere:
            seuil = int(round(ligne))
            if total > seuil: p_over += p
            elif total < seuil: p_under += p
            else: p_remb += p
        else:
            if total > ligne: p_over += p
            else: p_under += p
    return p_over, p_under, p_remb


def calcul_ou_complet(matrix, ou_lignes):
    resultats = []
    for l in ou_lignes:
        ligne = l.get("ligne"); cote_over = l.get("cote_over"); cote_under = l.get("cote_under")
        if ligne is None: continue
        p_over, p_under, p_remb = proba_over_under(matrix, ligne)
        if cote_over and cote_over > 0:
            p_eff = p_over + 0.5 * p_remb
            ev = compute_ev(p_eff, cote_over)
            fiab = compute_reliability(p_eff, cote_over, ev)
            passe, raisons = appliquer_filtres_discipline(p_eff, cote_over, ev, fiab)
            dec, niv = classify_decision(fiab, ev)
            stake = compute_stake(p_eff, cote_over, fiab, ev) if passe else 0.0
            resultats.append({
                "ligne": ligne, "type": "Over",
                "p_brute": round(p_over, 4), "p_remb": round(p_remb, 4),
                "p": round(p_eff, 4), "cote": cote_over,
                "ev": round(ev, 4), "fiabilite": fiab,
                "passe_filtres": passe, "raisons_rejet": raisons,
                "decision": dec, "niveau": niv, "stake": stake,
            })
        if cote_under and cote_under > 0:
            p_eff = p_under + 0.5 * p_remb
            ev = compute_ev(p_eff, cote_under)
            fiab = compute_reliability(p_eff, cote_under, ev)
            passe, raisons = appliquer_filtres_discipline(p_eff, cote_under, ev, fiab)
            dec, niv = classify_decision(fiab, ev)
            stake = compute_stake(p_eff, cote_under, fiab, ev) if passe else 0.0
            resultats.append({
                "ligne": ligne, "type": "Under",
                "p_brute": round(p_under, 4), "p_remb": round(p_remb, 4),
                "p": round(p_eff, 4), "cote": cote_under,
                "ev": round(ev, 4), "fiabilite": fiab,
                "passe_filtres": passe, "raisons_rejet": raisons,
                "decision": dec, "niveau": niv, "stake": stake,
            })
    return resultats


# =========================================================
# 5. DÉTECTION DE DIVERGENCES
# =========================================================
def detecter_divergences(r, cotes_dict):
    """
    Détecte les divergences Modèle vs Marché sur 1X2, Handicap et O/U.
    Retourne une liste de dicts.
    """
    divergences = []

    # --- A. 1X2 ---
    p_marche_1x2 = demargeage_proportionnel([
        cotes_dict.get("curr_1"), cotes_dict.get("curr_x"), cotes_dict.get("curr_2")
    ])
    if p_marche_1x2:
        pm1, pmx, pm2 = p_marche_1x2
        for label, p_mod, p_mar in [
            ("1 (Domicile)", r["p1"], pm1),
            ("X (Nul)", r["px"], pmx),
            ("2 (Extérieur)", r["p2"], pm2),
        ]:
            ecart = p_mod - p_mar
            if abs(ecart) > 0.15:
                niveau = "MAJEUR" if abs(ecart) > 0.25 else "MODÉRÉ"
                interp = "🟢 Modèle > Marché — value détectée" if ecart > 0 else "⚠️ Modèle < Marché — piège potentiel"
                divergences.append({
                    "type": "Modèle vs Marché",
                    "marche": f"1X2 — {label}",
                    "p_modele": round(p_mod, 4),
                    "p_marche": round(p_mar, 4),
                    "ecart": round(ecart, 4),
                    "niveau": niveau,
                    "interpretation": interp,
                })

    # --- B. Handicap (par ligne) ---
    for h in r.get("handicap_resultats", []):
        if h["cote"] and h["cote"] > 0:
            # Proba implicite simple du marché (sans démargeage, car côté unique)
            p_marche_hcp = 1.0 / h["cote"]
            ecart = h["p"] - p_marche_hcp
            if abs(ecart) > 0.15:
                niveau = "MAJEUR" if abs(ecart) > 0.25 else "MODÉRÉ"
                interp = "🟢 Modèle > Marché — value" if ecart > 0 else "⚠️ Modèle < Marché — piège"
                divergences.append({
                    "type": "Modèle vs Marché",
                    "marche": f"Hcp {h['hcp']:+g} ({h['cible']})",
                    "p_modele": round(h["p"], 4),
                    "p_marche": round(p_marche_hcp, 4),
                    "ecart": round(ecart, 4),
                    "niveau": niveau,
                    "interpretation": interp,
                })

    # --- C. Over / Under ---
    for o in r.get("ou_resultats", []):
        if o["cote"] and o["cote"] > 0:
            p_marche_ou = 1.0 / o["cote"]
            ecart = o["p"] - p_marche_ou
            if abs(ecart) > 0.15:
                niveau = "MAJEUR" if abs(ecart) > 0.25 else "MODÉRÉ"
                interp = "🟢 Modèle > Marché — value" if ecart > 0 else "⚠️ Modèle < Marché — piège"
                divergences.append({
                    "type": "Modèle vs Marché",
                    "marche": f"{o['type']} {o['ligne']} buts",
                    "p_modele": round(o["p"], 4),
                    "p_marche": round(p_marche_ou, 4),
                    "ecart": round(ecart, 4),
                    "niveau": niveau,
                    "interpretation": interp,
                })

    # Tri : les divergences MAJEURES en premier, puis par écart absolu décroissant
    divergences.sort(key=lambda d: (0 if d["niveau"] == "MAJEUR" else 1, -abs(d["ecart"])))
    return divergences


# =========================================================
# 6. MOYENNES
# =========================================================
def moy(valeurs):
    v = [x for x in valeurs if x is not None]
    if not v: return 0.0
    return sum(v) / len(v)


# =========================================================
# 7. AJUSTEMENTS CONTEXTUELS
# =========================================================
def facteur_meteo(m):
    return {"normale": 1.00, "pluie": 0.90, "neige": 0.85, "chaleur_extreme": 0.90, "vent_fort": 0.92}.get(m, 1.00)

def facteur_enjeu(e):
    return {"normal": 1.00, "derby": 0.95, "finale": 0.92, "fin_saison": 0.97, "relegation": 0.95}.get(e, 1.00)

def facteur_blessures(a): return 0.85 if a else 1.00
def facteur_fatigue(a): return 0.90 if a else 1.00

def facteur_classement(pos_dom, pos_ext, total):
    if pos_dom is None or pos_ext is None or total is None or total <= 1:
        return (1.0, 1.0)
    ecart = max(min((pos_ext - pos_dom) / total, 1.0), -1.0)
    ajust = ecart * 0.15
    return (round(1.0 + ajust, 3), round(1.0 - ajust, 3))

def facteur_ht(matchs):
    m = [x for x in matchs if x.get("ht_bp") is not None]
    if not m: return 1.00
    tbp = sum(x["bp"] for x in m); tht = sum(x["ht_bp"] for x in m)
    if tbp == 0: return 1.00
    r = (tbp - tht) / tbp
    e = max(min((r - 0.5) * 0.20, 0.05), -0.05)
    return 1.00 + e

def facteur_forme_recente(matchs):
    if len(matchs) < 5: return 1.00
    pts = [3 if (m["bp"] - m["bc"]) > 0 else (1 if m["bp"] == m["bc"] else 0) for m in matchs]
    m5 = sum(pts) / len(pts); m3 = sum(pts[:3]) / 3.0
    e = max(min((m3 - m5) / 3.0, 1.0), -1.0)
    return 1.00 + e * 0.05

def facteur_h2h(h2h):
    if not h2h: return (1.00, 1.00)
    v = sum(1 if m["bp"] > m["bc"] else (-1 if m["bp"] < m["bc"] else 0) for m in h2h)
    r = v / len(h2h)
    a = r * 0.08
    return (round(1.0 + a, 3), round(1.0 - a, 3))


# =========================================================
# 8. LAMBDAS
# =========================================================
def compute_lambdas(home_ctx, home_glob, away_ctx, away_glob, h2h_matchs,
                    meteo, enjeu, bd, be, fd, fe, pd=None, pe=None, te=None):
    hbp_ctx = moy([m["bp"] for m in home_ctx]); hbc_ctx = moy([m["bc"] for m in home_ctx])
    abp_ctx = moy([m["bp"] for m in away_ctx]); abc_ctx = moy([m["bc"] for m in away_ctx])
    hbp_g = moy([m["bp"] for m in home_glob]) if home_glob else hbp_ctx
    hbc_g = moy([m["bc"] for m in home_glob]) if home_glob else hbc_ctx
    abp_g = moy([m["bp"] for m in away_glob]) if away_glob else abp_ctx
    abc_g = moy([m["bc"] for m in away_glob]) if away_glob else abc_ctx
    hbp = 0.7*hbp_ctx + 0.3*hbp_g; hbc = 0.7*hbc_ctx + 0.3*hbc_g
    abp = 0.7*abp_ctx + 0.3*abp_g; abc = 0.7*abc_ctx + 0.3*abc_g
    lh = (hbp + abc) / 2.0; la = (abp + hbc) / 2.0

    fht_h = facteur_ht(home_ctx); fht_a = facteur_ht(away_ctx)
    lh *= fht_h; la *= fht_a
    ff_h = facteur_forme_recente(home_ctx); ff_a = facteur_forme_recente(away_ctx)
    lh *= ff_h; la *= ff_a
    fc_h, fc_a = facteur_classement(pd, pe, te)
    lh *= fc_h; la *= fc_a
    fh2h_h, fh2h_a = facteur_h2h(h2h_matchs)
    lh *= fh2h_h; la *= fh2h_a
    fcomm = facteur_meteo(meteo) * facteur_enjeu(enjeu)
    lh *= fcomm; la *= fcomm
    lh *= facteur_blessures(bd); la *= facteur_blessures(be)
    lh *= facteur_fatigue(fd); la *= facteur_fatigue(fe)
    lh = max(lh, 0.1); la = max(la, 0.1)
    return lh, la, {
        "home_bp_ctx": round(hbp_ctx, 2), "home_bp_glob": round(hbp_g, 2),
        "away_bp_ctx": round(abp_ctx, 2), "away_bp_glob": round(abp_g, 2),
        "f_ht_home": round(fht_h, 3), "f_ht_away": round(fht_a, 3),
        "f_forme_home": round(ff_h, 3), "f_forme_away": round(ff_a, 3),
        "f_class_home": fc_h, "f_class_away": fc_a,
        "f_h2h_home": fh2h_h, "f_h2h_away": fh2h_a,
        "f_meteo": round(facteur_meteo(meteo), 3), "f_enjeu": round(facteur_enjeu(enjeu), 3),
        "f_bless_dom": facteur_blessures(bd), "f_bless_ext": facteur_blessures(be),
        "f_fatigue_dom": facteur_fatigue(fd), "f_fatigue_ext": facteur_fatigue(fe),
        "f_commun": round(fcomm, 3),
    }


# =========================================================
# 9. EV + FIABILITÉ + STAKE
# =========================================================
def compute_ev(p, cote):
    if cote <= 0: return 0.0
    return p * cote - 1.0


def compute_reliability(p, cote, ev):
    f_p = p
    f_v = 0.0 if ev < 0 else min(ev / 0.15, 1.0)
    f_c = 0.7 if cote < 1.3 else (0.5 if cote > 8.0 else 1.0)
    fiab = 0.50 * f_p + 0.30 * f_v + 0.20 * f_c
    return round(min(max(fiab, 0.0), 1.0), 3)


def compute_stake(p, cote, fiab, ev):
    if ev <= 0 or cote <= 1: return 0.0
    f_star = (p * cote - 1.0) / (cote - 1.0)
    if fiab >= 0.85: lam, plaf = 0.30, 1.5
    elif fiab >= 0.75: lam, plaf = 0.25, 1.0
    elif fiab >= 0.65: lam, plaf = 0.15, 0.5
    else: lam, plaf = 0.10, 0.25
    return round(max(min(f_star * lam * 100, plaf), 0.0), 2)


# =========================================================
# 10. FILTRES
# =========================================================
SEUIL_FIABILITE = 0.75
SEUIL_VALUE_1X2 = 0.05
SEUIL_CONFIANCE = 0.70


def appliquer_filtres_discipline(p, cote, ev, fiab):
    r = []
    if fiab < SEUIL_FIABILITE: r.append(f"Fiabilité {fiab} < {SEUIL_FIABILITE}")
    if ev < SEUIL_VALUE_1X2: r.append(f"Value {ev*100:.2f}% < {SEUIL_VALUE_1X2*100:.0f}%")
    if p < SEUIL_CONFIANCE: r.append(f"Confiance {p*100:.2f}% < {SEUIL_CONFIANCE*100:.0f}%")
    return (len(r) == 0, r)


def classify_decision(fiab, ev):
    if fiab >= 0.85 and ev >= SEUIL_VALUE_1X2: return "🔥 ATTAQUE FORTE", "ELITE"
    elif fiab >= 0.75 and ev >= SEUIL_VALUE_1X2: return "✅ ATTAQUE", "PREMIUM"
    elif fiab >= 0.65: return "🤔 LEAN", "GOOD"
    elif fiab >= 0.55: return "👀 SURVEILLANCE", "SURVEILLANCE"
    else: return "❌ ÉVITER", "AVOID"


# =========================================================
# 11. ANALYSE COMPLÈTE
# =========================================================
def analyser_match_football(
    home_ctx, home_glob, away_ctx, away_glob,
    open_1, open_x, open_2, curr_1, curr_x, curr_2,
    meteo="normale", enjeu="normal",
    blessures_dom=False, blessures_ext=False,
    fatigue_dom=False, fatigue_ext=False,
    h2h_matchs=None, handicap_lignes=None, ou_lignes=None,
    pos_dom=None, pos_ext=None, total_equipes=None
):
    if h2h_matchs is None: h2h_matchs = []
    if handicap_lignes is None: handicap_lignes = []
    if ou_lignes is None: ou_lignes = []

    lh, la, details = compute_lambdas(
        home_ctx, home_glob, away_ctx, away_glob, h2h_matchs,
        meteo, enjeu, blessures_dom, blessures_ext, fatigue_dom, fatigue_ext,
        pos_dom, pos_ext, total_equipes
    )
    matrix = compute_score_matrix(lh, la)
    p1, px, p2 = compute_1x2(matrix)

    ev1 = compute_ev(p1, curr_1)
    evx = compute_ev(px, curr_x) if curr_x > 0 else -1.0
    ev2 = compute_ev(p2, curr_2)
    f1 = compute_reliability(p1, curr_1, ev1)
    fx = compute_reliability(px, curr_x, evx) if curr_x > 0 else 0.0
    f2 = compute_reliability(p2, curr_2, ev2)

    candidats = [
        {"selection": "1 (Domicile)", "p": p1, "cote": curr_1, "ev": ev1, "fiabilite": f1, "type": "1X2"},
        {"selection": "X (Nul)", "p": px, "cote": curr_x, "ev": evx, "fiabilite": fx, "type": "1X2"},
        {"selection": "2 (Extérieur)", "p": p2, "cote": curr_2, "ev": ev2, "fiabilite": f2, "type": "1X2"},
    ]
    for c in candidats:
        passe, raisons = appliquer_filtres_discipline(c["p"], c["cote"], c["ev"], c["fiabilite"])
        c["passe_filtres"] = passe; c["raisons_rejet"] = raisons
        dec, niv = classify_decision(c["fiabilite"], c["ev"])
        c["decision"] = dec; c["niveau"] = niv
        c["stake"] = compute_stake(c["p"], c["cote"], c["fiabilite"], c["ev"]) if passe else 0.0

    handicap_resultats = calcul_handicap_complet(matrix, handicap_lignes)
    ou_resultats = calcul_ou_complet(matrix, ou_lignes)

    tous = list(candidats)
    for h in handicap_resultats:
        h["selection"] = f"Hcp {h['hcp']:+g} ({h['cible']})"; h["type"] = "Handicap"
        tous.append(h)
    for o in ou_resultats:
        o["selection"] = f"{o['type']} {o['ligne']}"; o["type"] = "O/U Buts"
        tous.append(o)
    tous.sort(key=lambda x: x["fiabilite"], reverse=True)

    pari_retenu = None
    for c in tous:
        if c["passe_filtres"] and c["stake"] > 0:
            pari_retenu = c
            break

    ou_securite = None
    if ou_resultats:
        passes = [o for o in ou_resultats if o["passe_filtres"]]
        ou_securite = max(passes, key=lambda x: x["fiabilite"]) if passes else max(ou_resultats, key=lambda x: x["fiabilite"])
        if pari_retenu and ou_securite:
            if (pari_retenu.get("type") == ou_securite.get("type") and
                pari_retenu.get("ligne") == ou_securite.get("ligne") and
                pari_retenu.get("selection") == ou_securite.get("selection")):
                ou_securite = None
        if ou_securite and ou_securite["fiabilite"] < 0.60:
            ou_securite = None

    top_scores = sorted(matrix.items(), key=lambda x: x[1], reverse=True)[:3]
    top_3 = [{"rank": i+1, "score": f"{s[0]}-{s[1]}", "probability": round(p, 4)} for i, (s, p) in enumerate(top_scores)]

    # Divergences
    cotes_dict = {"curr_1": curr_1, "curr_x": curr_x, "curr_2": curr_2}
    r_temp = {
        "p1": p1, "px": px, "p2": p2,
        "handicap_resultats": handicap_resultats,
        "ou_resultats": ou_resultats,
    }
    divergences = detecter_divergences(r_temp, cotes_dict)

    return {
        "lambda_home": round(lh, 2), "lambda_away": round(la, 2),
        "details": details,
        "p1": round(p1, 4), "px": round(px, 4), "p2": round(p2, 4),
        "ev1": round(ev1, 4), "evx": round(evx, 4), "ev2": round(ev2, 4),
            "f1": f1, "fx": fx, "f2": f2,
    "candidats": candidats,
    "handicap_resultats": handicap_resultats,
    "ou_resultats": ou_resultats,
    "ou_securite": ou_securite,
    "pari_retenu": pari_retenu,
    "top_3_scores": top_3,
    "divergences": divergences,
    }
