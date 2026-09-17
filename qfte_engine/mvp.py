"""
qfte_engine/mvp.py
------------------
Moteur QFTE V23.0 - Football
1X2 + Handicap + O/U + 2 mi-temps + Divergences + QFTE SIGNATURE FOOT + MARKET FORENSICS.
"""

import math
from qfte_engine.signature_foot import (
    analyser_signature_foot,
    calculer_over_under_avec_ic,
)
from qfte_engine.forensics import (
    analyser_market_forensics,
    ajuster_fiabilite,
)


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


def compute_ratio_ht(matchs):
    m_ht = [m for m in matchs if m.get("ht_bp") is not None]
    if not m_ht:
        return 0.45
    total_bp = sum(m["bp"] for m in m_ht)
    total_ht_bp = sum(m["ht_bp"] for m in m_ht)
    if total_bp <= 0:
        return 0.45
    r = total_ht_bp / total_bp
    return max(min(r, 0.70), 0.25)


def demargeage_proportionnel(cotes):
    if not cotes or any(c is None or c <= 0 for c in cotes):
        return None
    inv = [1/c for c in cotes]
    total = sum(inv)
    if total <= 0:
        return None
    return [i/total for i in inv]


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


def moy(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return 0.0
    return sum(v) / len(v)


def facteur_meteo(m):
    return {"normale": 1.00, "pluie": 0.90, "neige": 0.85, "chaleur_extreme": 0.90, "vent_fort": 0.92}.get(m, 1.00)


def facteur_enjeu(e):
    return {"normal": 1.00, "derby": 0.95, "finale": 0.92, "fin_saison": 0.97, "relegation": 0.95}.get(e, 1.00)


def facteur_blessures(a):
    return 0.85 if a else 1.00


def facteur_fatigue(a):
    return 0.90 if a else 1.00


def facteur_classement(pos_dom, pos_ext, total):
    if pos_dom is None or pos_ext is None or total is None or total <= 1:
        return (1.0, 1.0)
    ecart = max(min((pos_ext - pos_dom) / total, 1.0), -1.0)
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


def compute_ev(p, cote):
    if cote <= 0:
        return 0.0
    return p * cote - 1.0


def compute_reliability(p, cote, ev):
    f_p = p
    f_v = 0.0 if ev < 0 else min(ev / 0.15, 1.0)
    f_c = 0.7 if cote < 1.3 else (0.5 if cote > 8.0 else 1.0)
    fiab = 0.50 * f_p + 0.30 * f_v + 0.20 * f_c
    return round(min(max(fiab, 0.0), 1.0), 3)


def compute_stake(p, cote, fiab, ev):
    if ev <= 0 or cote <= 1:
        return 0.0
    f_star = (p * cote - 1.0) / (cote - 1.0)
    if fiab >= 0.85:
        lam, plaf = 0.30, 1.5
    elif fiab >= 0.75:
        lam, plaf = 0.25, 1.0
    elif fiab >= 0.65:
        lam, plaf = 0.15, 0.5
    else:
        lam, plaf = 0.10, 0.25
    return round(max(min(f_star * lam * 100, plaf), 0.0), 2)


SEUIL_FIABILITE = 0.75
SEUIL_VALUE_1X2 = 0.05
SEUIL_CONFIANCE = 0.70


def appliquer_filtres_discipline(p, cote, ev, fiab):
    r = []
    if fiab < SEUIL_FIABILITE:
        r.append("Fiabilite " + str(fiab) + " < " + str(SEUIL_FIABILITE))
    if ev < SEUIL_VALUE_1X2:
        r.append("Value " + str(round(ev * 100, 2)) + "% < " + str(int(SEUIL_VALUE_1X2 * 100)) + "%")
    if p < SEUIL_CONFIANCE:
        r.append("Confiance " + str(round(p * 100, 2)) + "% < " + str(int(SEUIL_CONFIANCE * 100)) + "%")
    return (len(r) == 0, r)


def classify_decision(fiab, ev):
    if fiab >= 0.85 and ev >= SEUIL_VALUE_1X2:
        return "ATTAQUE FORTE", "ELITE"
    elif fiab >= 0.75 and ev >= SEUIL_VALUE_1X2:
        return "ATTAQUE", "PREMIUM"
    elif fiab >= 0.65:
        return "LEAN", "GOOD"
    elif fiab >= 0.55:
        return "SURVEILLANCE", "SURVEILLANCE"
    else:
        return "EVITER", "AVOID"



def eval_candidat_simple(label, p, cote, marche=None):
    if not cote or cote <= 0:
        return None
    ev = compute_ev(p, cote)
    fiab = compute_reliability(p, cote, ev)
    passe, raisons = appliquer_filtres_discipline(p, cote, ev, fiab)
    dec, niv = classify_decision(fiab, ev)
    stake = compute_stake(p, cote, fiab, ev) if passe else 0.0
    return {
        "selection": label, "marche": marche or "1X2",
        "p": round(p, 4), "cote": cote,
        "ev": round(ev, 4), "fiabilite": fiab,
        "passe_filtres": passe, "raisons_rejet": raisons,
        "decision": dec, "niveau": niv, "stake": stake,
    }


def appliquer_forensics_au_candidat(c, forensics):
    """Ajuste la fiabilite d'un candidat selon le Sharpe Signal."""
    if not forensics or not forensics.get("disponible"):
        c["fiabilite_origine"] = c["fiabilite"]
        c["ajustement_forensics"] = 0.0
        c["sharpe_signal"] = None
        return c

    sharpe = forensics["sharpe_signal"]
    fiab_origine = c["fiabilite"]
    fiab_ajustee = ajuster_fiabilite(fiab_origine, sharpe)
    ajustement = round(fiab_ajustee - fiab_origine, 3)

    c["fiabilite_origine"] = fiab_origine
    c["fiabilite"] = fiab_ajustee
    c["ajustement_forensics"] = ajustement
    c["sharpe_signal"] = sharpe["sharpe_signal"]

    # Re-classifier selon la nouvelle fiabilite
    dec, niv = classify_decision(c["fiabilite"], c["ev"])
    c["decision"] = dec
    c["niveau"] = niv

    # Re-appliquer les filtres
    passe, raisons = appliquer_filtres_discipline(c["p"], c["cote"], c["ev"], c["fiabilite"])
    c["passe_filtres"] = passe
    c["raisons_rejet"] = raisons
    c["stake"] = compute_stake(c["p"], c["cote"], c["fiabilite"], c["ev"]) if passe else 0.0

    return c


def calcul_handicap_complet(matrix, handicap_lignes):
    resultats = []
    for ligne in handicap_lignes:
        hcp_dom = ligne.get("hcp_dom"); hcp_ext = ligne.get("hcp_ext")
        cote_dom = ligne.get("cote_dom"); cote_ext = ligne.get("cote_ext")
        if hcp_dom is not None and cote_dom:
            p_gain, p_remb = proba_handicap_dom(matrix, hcp_dom)
            p_eff = p_gain + 0.5 * p_remb
            c = eval_candidat_simple("Hcp " + str(hcp_dom) + " (Dom)", p_eff, cote_dom, "Handicap")
            if c:
                c["hcp"] = hcp_dom
                c["cible"] = "Domicile"
                c["p_gain"] = round(p_gain, 4)
                c["p_remb"] = round(p_remb, 4)
                resultats.append(c)
        if hcp_ext is not None and cote_ext:
            p_gain, p_remb = proba_handicap_ext(matrix, hcp_ext)
            p_eff = p_gain + 0.5 * p_remb
            c = eval_candidat_simple("Hcp " + str(hcp_ext) + " (Ext)", p_eff, cote_ext, "Handicap")
            if c:
                c["hcp"] = hcp_ext
                c["cible"] = "Exterieur"
                c["p_gain"] = round(p_gain, 4)
                c["p_remb"] = round(p_remb, 4)
                resultats.append(c)
    return resultats


def calcul_ou_complet_from_signature(signature_result, ou_lignes):
    resultats = []
    for l in ou_lignes:
        ligne = l.get("ligne")
        cote_over = l.get("cote_over")
        cote_under = l.get("cote_under")
        if ligne is None:
            continue

        data = calculer_over_under_avec_ic(signature_result, ligne)
        p_over = data["p_over"]
        p_under = data["p_under"]
        ic_over = data["ic_over"]
        stab = data["stabilite"]

        if cote_over and cote_over > 0:
            c = eval_candidat_simple("Over " + str(ligne), p_over, cote_over, "O/U")
            if c:
                c["type_ou"] = "Over"
                c["ligne"] = ligne
                c["ic_95"] = ic_over
                c["stabilite"] = stab
                resultats.append(c)
        if cote_under and cote_under > 0:
            c = eval_candidat_simple("Under " + str(ligne), p_under, cote_under, "O/U")
            if c:
                c["type_ou"] = "Under"
                c["ligne"] = ligne
                c["ic_95"] = (1 - ic_over[1], 1 - ic_over[0]) if ic_over else None
                c["stabilite"] = stab
                resultats.append(c)
    return resultats


def calcul_marches_2mt(lambda_ht_home, lambda_ht_away, lambda_2h_home, lambda_2h_away, cotes_ht, cotes_2h):
    resultats = {"ht": [], "2h": []}
    matrix_ht = compute_score_matrix(lambda_ht_home, lambda_ht_away)
    matrix_2h = compute_score_matrix(lambda_2h_home, lambda_2h_away)
    p1_ht, px_ht, p2_ht = compute_1x2(matrix_ht)
    p1_2h, px_2h, p2_2h = compute_1x2(matrix_2h)

    if cotes_ht:
        for label, p, cote in [
            ("HT - 1 (Dom)", p1_ht, cotes_ht[0]),
            ("HT - X (Nul)", px_ht, cotes_ht[1]),
            ("HT - 2 (Ext)", p2_ht, cotes_ht[2]),
        ]:
            c = eval_candidat_simple(label, p, cote, "1X2 HT")
            if c:
                resultats["ht"].append(c)

    if cotes_2h:
        for label, p, cote in [
            ("2H - 1 (Dom)", p1_2h, cotes_2h[0]),
            ("2H - X (Nul)", px_2h, cotes_2h[1]),
            ("2H - 2 (Ext)", p2_2h, cotes_2h[2]),
        ]:
            c = eval_candidat_simple(label, p, cote, "1X2 2H")
            if c:
                resultats["2h"].append(c)

    resultats["p1_ht"] = round(p1_ht, 4)
    resultats["px_ht"] = round(px_ht, 4)
    resultats["p2_ht"] = round(p2_ht, 4)
    resultats["p1_2h"] = round(p1_2h, 4)
    resultats["px_2h"] = round(px_2h, 4)
    resultats["p2_2h"] = round(p2_2h, 4)
    return resultats


def detecter_divergences(r, cotes_dict):
    divergences = []
    p_marche_1x2 = demargeage_proportionnel([
        cotes_dict.get("curr_1"), cotes_dict.get("curr_x"), cotes_dict.get("curr_2")
    ])
    if p_marche_1x2:
        pm1, pmx, pm2 = p_marche_1x2
        for label, p_mod, p_mar in [
            ("1 (Domicile)", r["p1"], pm1),
            ("X (Nul)", r["px"], pmx),
            ("2 (Exterieur)", r["p2"], pm2),
        ]:
            ecart = p_mod - p_mar
            if abs(ecart) > 0.15:
                niveau = "MAJEUR" if abs(ecart) > 0.25 else "MODERE"
                interp = "Modele > Marche - value" if ecart > 0 else "Modele < Marche - piege"
                divergences.append({
                    "marche": "1X2 - " + label,
                    "p_modele": round(p_mod, 4), "p_marche": round(p_mar, 4),
                    "ecart": round(ecart, 4), "niveau": niveau, "interpretation": interp,
                })

    for h in r.get("handicap_resultats", []):
        if h["cote"] and h["cote"] > 0:
            p_marche_hcp = 1.0 / h["cote"]
            ecart = h["p"] - p_marche_hcp
            if abs(ecart) > 0.15:
                niveau = "MAJEUR" if abs(ecart) > 0.25 else "MODERE"
                interp = "Modele > Marche - value" if ecart > 0 else "Modele < Marche - piege"
                divergences.append({
                    "marche": "Hcp " + str(h["hcp"]) + " (" + h["cible"] + ")",
                    "p_modele": round(h["p"], 4), "p_marche": round(p_marche_hcp, 4),
                    "ecart": round(ecart, 4), "niveau": niveau, "interpretation": interp,
                })

    for o in r.get("ou_resultats", []):
        if o["cote"] and o["cote"] > 0:
            p_marche_ou = 1.0 / o["cote"]
            ecart = o["p"] - p_marche_ou
            if abs(ecart) > 0.15:
                niveau = "MAJEUR" if abs(ecart) > 0.25 else "MODERE"
                interp = "Modele > Marche - value" if ecart > 0 else "Modele < Marche - piege"
                divergences.append({
                    "marche": o.get("type_ou", "O/U") + " " + str(o.get("ligne", "")),
                    "p_modele": round(o["p"], 4), "p_marche": round(p_marche_ou, 4),
                    "ecart": round(ecart, 4), "niveau": niveau, "interpretation": interp,
                })

    divergences.sort(key=lambda d: (0 if d["niveau"] == "MAJEUR" else 1, -abs(d["ecart"])))
    return divergences


# =========================================================
# FONCTION PRINCIPALE
# =========================================================
def analyser_match_football(
    home_ctx, home_glob, away_ctx, away_glob,
    open_1, open_x, open_2, curr_1, curr_x, curr_2,
    meteo="normale", enjeu="normal",
    blessures_dom=False, blessures_ext=False,
    fatigue_dom=False, fatigue_ext=False,
    h2h_matchs=None, handicap_lignes=None, ou_lignes=None,
    pos_dom=None, pos_ext=None, total_equipes=None,
    cotes_ht=None, cotes_2h=None,
    ligue=None
):
    if h2h_matchs is None:
        h2h_matchs = []
    if handicap_lignes is None:
        handicap_lignes = []
    if ou_lignes is None:
        ou_lignes = []

    # ========================================
    # LAMBDA BRUT
    # ========================================
    hbp_ctx = moy([m["bp"] for m in home_ctx])
    hbc_ctx = moy([m["bc"] for m in home_ctx])
    abp_ctx = moy([m["bp"] for m in away_ctx])
    abc_ctx = moy([m["bc"] for m in away_ctx])

    hbp_g = moy([m["bp"] for m in home_glob]) if home_glob else hbp_ctx
    hbc_g = moy([m["bc"] for m in home_glob]) if home_glob else hbc_ctx
    abp_g = moy([m["bp"] for m in away_glob]) if away_glob else abp_ctx
    abc_g = moy([m["bc"] for m in away_glob]) if away_glob else abc_ctx

    hbp = 0.7 * hbp_ctx + 0.3 * hbp_g
    hbc = 0.7 * hbc_ctx + 0.3 * hbc_g
    abp = 0.7 * abp_ctx + 0.3 * abp_g
    abc = 0.7 * abc_ctx + 0.3 * abc_g

    lh_brut = (hbp + abc) / 2.0
    la_brut = (abp + hbc) / 2.0

    # Ajustements contextuels
    fht_h = facteur_ht(home_ctx); fht_a = facteur_ht(away_ctx)
    lh_brut *= fht_h; la_brut *= fht_a

    ff_h = facteur_forme_recente(home_ctx); ff_a = facteur_forme_recente(away_ctx)
    lh_brut *= ff_h; la_brut *= ff_a

    fc_h, fc_a = facteur_classement(pos_dom, pos_ext, total_equipes)
    lh_brut *= fc_h; la_brut *= fc_a

    fh2h_h, fh2h_a = facteur_h2h(h2h_matchs)
    lh_brut *= fh2h_h; la_brut *= fh2h_a

    fcomm = facteur_meteo(meteo) * facteur_enjeu(enjeu)
    lh_brut *= fcomm; la_brut *= fcomm

    lh_brut *= facteur_blessures(blessures_dom)
    la_brut *= facteur_blessures(blessures_ext)
    lh_brut *= facteur_fatigue(fatigue_dom)
    la_brut *= facteur_fatigue(fatigue_ext)

    lh_brut = max(lh_brut, 0.1)
    la_brut = max(la_brut, 0.1)

    # ========================================
    # QFTE SIGNATURE FOOT
    # ========================================
    signature = analyser_signature_foot(lh_brut, la_brut, ligue=ligue, n_mc=10000, rho=-0.05)

    lh = signature["lambda_home_bayesien"]
    la = signature["lambda_away_bayesien"]
    matrix = signature["matrix_dc"]

    p1, px, p2 = compute_1x2(matrix)

    # ========================================
    # MARKET FORENSICS
    # ========================================
    forensics = analyser_market_forensics(open_1, open_x, open_2, curr_1, curr_x, curr_2)

    ev1 = compute_ev(p1, curr_1)
    evx = compute_ev(px, curr_x) if curr_x > 0 else -1.0
    ev2 = compute_ev(p2, curr_2)
    f1 = compute_reliability(p1, curr_1, ev1)
    fx = compute_reliability(px, curr_x, evx) if curr_x > 0 else 0.0
    f2 = compute_reliability(p2, curr_2, ev2)

    candidats = [
        {"selection": "1 (Domicile)", "p": p1, "cote": curr_1, "ev": ev1, "fiabilite": f1, "type": "1X2"},
        {"selection": "X (Nul)", "p": px, "cote": curr_x, "ev": evx, "fiabilite": fx, "type": "1X2"},
        {"selection": "2 (Exterieur)", "p": p2, "cote": curr_2, "ev": ev2, "fiabilite": f2, "type": "1X2"},
    ]
    for c in candidats:
        passe, raisons = appliquer_filtres_discipline(c["p"], c["cote"], c["ev"], c["fiabilite"])
        c["passe_filtres"] = passe; c["raisons_rejet"] = raisons
        dec, niv = classify_decision(c["fiabilite"], c["ev"])
        c["decision"] = dec; c["niveau"] = niv
        c["stake"] = compute_stake(c["p"], c["cote"], c["fiabilite"], c["ev"]) if passe else 0.0
        # Appliquer forensics
        appliquer_forensics_au_candidat(c, forensics)

    handicap_resultats = calcul_handicap_complet(matrix, handicap_lignes)
    ou_resultats = calcul_ou_complet_from_signature(signature, ou_lignes)

    # Appliquer forensics aux handicaps et O/U
    for h in handicap_resultats:
        appliquer_forensics_au_candidat(h, forensics)
    for o in ou_resultats:
        appliquer_forensics_au_candidat(o, forensics)

    ratio_ht_h = compute_ratio_ht(home_ctx)
    ratio_ht_a = compute_ratio_ht(away_ctx)
    lambda_ht_h = lh * ratio_ht_h
    lambda_ht_a = la * ratio_ht_a
    lambda_2h_h = lh * (1 - ratio_ht_h)
    lambda_2h_a = la * (1 - ratio_ht_a)
    marches_2mt = calcul_marches_2mt(lambda_ht_h, lambda_ht_a, lambda_2h_h, lambda_2h_a, cotes_ht, cotes_2h)

    # Appliquer forensics aux marches 2MT
    for c in marches_2mt.get("ht", []):
        appliquer_forensics_au_candidat(c, forensics)
    for c in marches_2mt.get("2h", []):
        appliquer_forensics_au_candidat(c, forensics)

    tous = list(candidats)
    for h in handicap_resultats:
        h["selection"] = "Hcp " + str(h["hcp"]) + " (" + h["cible"] + ")"; h["type"] = "Handicap"
        tous.append(h)
    for o in ou_resultats:
        o["selection"] = o.get("type_ou", "O/U") + " " + str(o.get("ligne", "")); o["type"] = "O/U"
        tous.append(o)
    for c in marches_2mt.get("ht", []):
        c["type"] = "1X2 HT"; tous.append(c)
    for c in marches_2mt.get("2h", []):
        c["type"] = "1X2 2H"; tous.append(c)

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
            if pari_retenu.get("marche") == ou_securite.get("marche") and pari_retenu.get("selection") == ou_securite.get("selection"):
                ou_securite = None
        if ou_securite and ou_securite["fiabilite"] < 0.60:
            ou_securite = None

    top_scores = sorted(matrix.items(), key=lambda x: x[1], reverse=True)[:3]
    top_3 = [{"rank": i+1, "score": str(s[0]) + "-" + str(s[1]), "probability": round(p, 4)} for i, (s, p) in enumerate(top_scores)]

    cotes_dict = {"curr_1": curr_1, "curr_x": curr_x, "curr_2": curr_2}
    r_temp = {
        "p1": p1, "px": px, "p2": p2,
        "handicap_resultats": handicap_resultats,
        "ou_resultats": ou_resultats,
    }
    divergences = detecter_divergences(r_temp, cotes_dict)

    details = {
        "home_bp_ctx": round(hbp_ctx, 2), "home_bp_glob": round(hbp_g, 2),
        "away_bp_ctx": round(abp_ctx, 2), "away_bp_glob": round(abp_g, 2),
        "ratio_ht_home": round(ratio_ht_h, 3), "ratio_ht_away": round(ratio_ht_a, 3),
        "f_ht_home": round(fht_h, 3), "f_ht_away": round(fht_a, 3),
        "f_forme_home": round(ff_h, 3), "f_forme_away": round(ff_a, 3),
        "f_class_home": fc_h, "f_class_away": fc_a,
        "f_h2h_home": fh2h_h, "f_h2h_away": fh2h_a,
        "f_meteo": round(facteur_meteo(meteo), 3), "f_enjeu": round(facteur_enjeu(enjeu), 3),
        "f_bless_dom": facteur_blessures(blessures_dom), "f_bless_ext": facteur_blessures(blessures_ext),
        "f_fatigue_dom": facteur_fatigue(fatigue_dom), "f_fatigue_ext": facteur_fatigue(fatigue_ext),
        "f_commun": round(fcomm, 3),
    }

    return {
        "lambda_home": round(lh, 2), "lambda_away": round(la, 2),
        "lambda_home_brut": round(lh_brut, 2), "lambda_away_brut": round(la_brut, 2),
        "lambda_ht_home": round(lambda_ht_h, 2), "lambda_ht_away": round(lambda_ht_a, 2),
        "lambda_2h_home": round(lambda_2h_h, 2), "lambda_2h_away": round(lambda_2h_a, 2),
        "details": details,
        "signature": {
            "prior_ligue": signature["prior_ligue"],
            "lambda_home_brut": signature["lambda_home_brut"],
            "lambda_away_brut": signature["lambda_away_brut"],
            "lambda_home_bayesien": signature["lambda_home_bayesien"],
            "lambda_away_bayesien": signature["lambda_away_bayesien"],
            "rho": signature["rho"],
            "methode": signature["methode"],
            "n_simulations": signature["n_simulations"],
            "ic_p1": signature["ic_p1"],
            "ic_px": signature["ic_px"],
            "ic_p2": signature["ic_p2"],
            "stab_p1": signature["stab_p1"],
            "stab_px": signature["stab_px"],
            "stab_p2": signature["stab_p2"],
            "p_btts_oui_dc": signature["p_btts_oui_dc"],
            "p_btts_non_dc": signature["p_btts_non_dc"],
        },
        "forensics": forensics,
        "p1": round(p1, 4), "px": round(px, 4), "p2": round(p2, 4),
        "ev1": round(ev1, 4), "evx": round(evx, 4), "ev2": round(ev2, 4),
        "f1": f1, "fx": fx, "f2": f2,
        "candidats": candidats,
        "handicap_resultats": handicap_resultats,
        "ou_resultats": ou_resultats,
        "marches_2mt": marches_2mt,
        "ou_securite": ou_securite,
        "pari_retenu": pari_retenu,
        "top_3_scores": top_3,
        "divergences": divergences,
    }
