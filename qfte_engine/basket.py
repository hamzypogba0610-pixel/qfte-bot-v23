"""
qfte_engine/basket.py
---------------------
Moteur QFTE V23.0 - Basketball (NBA, Euroleague).
Distribution Normale + Moneyline/Spread/Total (FT, 1H, 2H).
"""

import math


# =========================================================
# 1. HELPERS
# =========================================================
def norm_cdf(x, mu=0.0, sigma=1.0):
    if sigma <= 0:
        return 0.0 if x < mu else 1.0
    return 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))


def moy(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return 0.0
    return sum(v) / len(v)


# =========================================================
# 2. AJUSTEMENTS BASKET
# =========================================================
def facteur_blessures(a):
    return 0.92 if a else 1.00


def facteur_fatigue(a):
    return 0.94 if a else 1.00


def facteur_classement(pos_dom, pos_ext, total):
    if pos_dom is None or pos_ext is None or total is None or total <= 1:
        return (1.0, 1.0)
    ecart = max(min((pos_ext - pos_dom) / total, 1.0), -1.0)
    ajust = ecart * 0.10
    return (round(1.0 + ajust, 3), round(1.0 - ajust, 3))


def facteur_h2h(h2h):
    if not h2h:
        return (1.00, 1.00)
    v = sum(1 if m["bp"] > m["bc"] else (-1 if m["bp"] < m["bc"] else 0) for m in h2h)
    r = v / len(h2h)
    a = r * 0.06
    return (round(1.0 + a, 3), round(1.0 - a, 3))


# =========================================================
# 3. EV / FIABILITE / STAKE
# =========================================================
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


# =========================================================
# 4. FILTRES
# =========================================================
SEUIL_FIABILITE = 0.75
SEUIL_VALUE = 0.04
SEUIL_CONFIANCE = 0.70


def appliquer_filtres(p, cote, ev, fiab):
    r = []
    if fiab < SEUIL_FIABILITE:
        r.append("Fiabilite " + str(fiab) + " < " + str(SEUIL_FIABILITE))
    if ev < SEUIL_VALUE:
        r.append("Value " + str(round(ev * 100, 2)) + "% < " + str(int(SEUIL_VALUE * 100)) + "%")
    if p < SEUIL_CONFIANCE:
        r.append("Confiance " + str(round(p * 100, 2)) + "% < " + str(int(SEUIL_CONFIANCE * 100)) + "%")
    return (len(r) == 0, r)


def classify(fiab, ev):
    if fiab >= 0.85 and ev >= SEUIL_VALUE:
        return "ATTAQUE FORTE", "ELITE"
    elif fiab >= 0.75 and ev >= SEUIL_VALUE:
        return "ATTAQUE", "PREMIUM"
    elif fiab >= 0.65:
        return "LEAN", "GOOD"
    elif fiab >= 0.55:
        return "SURVEILLANCE", "SURVEILLANCE"
    else:
        return "EVITER", "AVOID"


# =========================================================
# 5. CANDIDAT GENERIQUE
# =========================================================
def eval_candidat(label, p, cote, marche=None):
    if not cote or cote <= 0:
        return None
    ev = compute_ev(p, cote)
    fiab = compute_reliability(p, cote, ev)
    passe, raisons = appliquer_filtres(p, cote, ev, fiab)
    dec, niv = classify(fiab, ev)
    stake = compute_stake(p, cote, fiab, ev) if passe else 0.0
    return {
        "selection": label,
        "marche": marche or "?",
        "p": round(p, 4),
        "cote": cote,
        "ev": round(ev, 4),
        "fiabilite": fiab,
        "passe_filtres": passe,
        "raisons_rejet": raisons,
        "decision": dec,
        "niveau": niv,
        "stake": stake,
  }


# =========================================================
# 6. CALCUL DES POINTS ATTENDUS (MODELE NORMAL)
# =========================================================
def compute_lambdas_basket(home_ctx, home_glob, away_ctx, away_glob,
                            h2h, bd, be, fd, fe, pd, pe, te):
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

    # Points attendus (basket)
    mu_home = (hbp + abc) / 2.0
    mu_away = (abp + hbc) / 2.0

    # Facteurs
    fc_h, fc_a = facteur_classement(pd, pe, te)
    mu_home *= fc_h
    mu_away *= fc_a

    fh2h_h, fh2h_a = facteur_h2h(h2h)
    mu_home *= fh2h_h
    mu_away *= fh2h_a

    mu_home *= facteur_blessures(bd)
    mu_away *= facteur_blessures(be)
    mu_home *= facteur_fatigue(fd)
    mu_away *= facteur_fatigue(fe)

    mu_home = max(mu_home, 60.0)
    mu_away = max(mu_away, 60.0)

    return mu_home, mu_away, {
        "home_bp_ctx": round(hbp_ctx, 1),
        "home_bp_glob": round(hbp_g, 1),
        "away_bp_ctx": round(abp_ctx, 1),
        "away_bp_glob": round(abp_g, 1),
        "f_class_home": fc_h,
        "f_class_away": fc_a,
        "f_h2h_home": fh2h_h,
        "f_h2h_away": fh2h_a,
        "f_bless_dom": facteur_blessures(bd),
        "f_bless_ext": facteur_blessures(be),
        "f_fatigue_dom": facteur_fatigue(fd),
        "f_fatigue_ext": facteur_fatigue(fe),
    }


# =========================================================
# 7. PROBABILITE MONEYLINE (sans nul)
# =========================================================
def proba_moneyline(mu_home, mu_away, sigma):
    # P(home gagne) = P(home_score > away_score)
    # Marge = home - away ~ N(mu_home - mu_away, sigma*sqrt(2))
    mu_diff = mu_home - mu_away
    sigma_diff = sigma * math.sqrt(2)
    p_home = 1 - norm_cdf(0, mu_diff, sigma_diff)
    p_away = norm_cdf(0, mu_diff, sigma_diff)
    return p_home, p_away


# =========================================================
# 8. PROBABILITES SPREAD (handicap basket)
# =========================================================
def proba_spread(mu_home, mu_away, hcp, sigma):
    # Marge ajustee = (home - away) + hcp  (hcp negatif → home doit gagner par +)
    mu_ajuste = mu_home - mu_away + hcp
    p_home = 1 - norm_cdf(0, mu_ajuste, sigma * math.sqrt(2))
    p_away = norm_cdf(0, mu_ajuste, sigma * math.sqrt(2))
    return p_home, p_away


# =========================================================
# 9. PROBABILITES OVER/UNDER POINTS
# =========================================================
def proba_total(mu_total, ligne, sigma):
    p_over = 1 - norm_cdf(ligne, mu_total, sigma)
    p_under = norm_cdf(ligne, mu_total, sigma)
    return p_over, p_under


# =========================================================
# 10. RATIOS MI-TEMPS BASKET
# =========================================================
RATIO_1H = 0.51
RATIO_2H = 0.49
SIGMA_FT = 11.0
SIGMA_MT = 8.0


# =========================================================
# 11. ANALYSE COMPLETE BASKET
# =========================================================
def analyser_match_basket(
    home_ctx, home_glob, away_ctx, away_glob,
    h2h_matchs, hcp_lignes, ou_lignes,
    bd, be, fd, fe, pd, pe, te,
    ml_ft=None, ml_1h=None, ml_2h=None,
    total_1h=None, total_2h=None
):
    if h2h_matchs is None:
        h2h_matchs = []
    if hcp_lignes is None:
        hcp_lignes = []
    if ou_lignes is None:
        ou_lignes = []

    mu_home, mu_away, details = compute_lambdas_basket(
        home_ctx, home_glob, away_ctx, away_glob,
        h2h_matchs, bd, be, fd, fe, pd, pe, te
    )
    mu_total = mu_home + mu_away

    # --- MONEYLINE FT ---
    p_ml_home, p_ml_away = proba_moneyline(mu_home, mu_away, SIGMA_FT)
    ml_candidats = []
    if ml_ft and len(ml_ft) == 2:
        c = eval_candidat("FT - Domicile", p_ml_home, ml_ft[0], "Moneyline FT")
        if c:
            ml_candidats.append(c)
        c = eval_candidat("FT - Exterieur", p_ml_away, ml_ft[1], "Moneyline FT")
        if c:
            ml_candidats.append(c)

    # --- SPREAD FT ---
    spread_candidats = []
    for l in hcp_lignes:
        hd = l.get("hcp_dom")
        he = l.get("hcp_ext")
        cd = l.get("cote_dom")
        ce = l.get("cote_ext")
        if hd is not None and cd:
            p_dom, _ = proba_spread(mu_home, mu_away, hd, SIGMA_FT)
            c = eval_candidat("Spread " + str(hd) + " (Dom)", p_dom, cd, "Spread FT")
            if c:
                spread_candidats.append(c)
        if he is not None and ce:
            _, p_ext = proba_spread(mu_home, mu_away, he, SIGMA_FT)
            c = eval_candidat("Spread " + str(he) + " (Ext)", p_ext, ce, "Spread FT")
            if c:
                spread_candidats.append(c)

    # --- TOTAL POINTS FT ---
    total_ft_candidats = []
    for l in ou_lignes:
        ligne = l.get("ligne")
        co = l.get("cote_over")
        cu = l.get("cote_under")
        if ligne is None:
            continue
        p_over, p_under = proba_total(mu_total, ligne, SIGMA_FT)
        if co:
            c = eval_candidat("Over " + str(ligne), p_over, co, "Total FT")
            if c:
                total_ft_candidats.append(c)
        if cu:
            c = eval_candidat("Under " + str(ligne), p_under, cu, "Total FT")
            if c:
                total_ft_candidats.append(c)

    # --- MI-TEMPS 1H ---
    mu_total_1h = mu_total * RATIO_1H
    mu_home_1h = mu_home * RATIO_1H
    mu_away_1h = mu_away * RATIO_1H
    ml_1h_candidats = []
    total_1h_candidats = []
    p_1h_home, p_1h_away = proba_moneyline(mu_home_1h, mu_away_1h, SIGMA_MT)
    if ml_1h and len(ml_1h) == 2:
        c = eval_candidat("1H - Domicile", p_1h_home, ml_1h[0], "Moneyline 1H")
        if c:
            ml_1h_candidats.append(c)
        c = eval_candidat("1H - Exterieur", p_1h_away, ml_1h[1], "Moneyline 1H")
        if c:
            ml_1h_candidats.append(c)
    if total_1h and len(total_1h) == 3:
        ligne_1h = total_1h[0]
        co = total_1h[1]
        cu = total_1h[2]
        p_over, p_under = proba_total(mu_total_1h, ligne_1h, SIGMA_MT)
        c = eval_candidat("1H Over " + str(ligne_1h), p_over, co, "Total 1H")
        if c:
            total_1h_candidats.append(c)
        c = eval_candidat("1H Under " + str(ligne_1h), p_under, cu, "Total 1H")
        if c:
            total_1h_candidats.append(c)

    # --- MI-TEMPS 2H ---
    mu_total_2h = mu_total * RATIO_2H
    mu_home_2h = mu_home * RATIO_2H
    mu_away_2h = mu_away * RATIO_2H
    ml_2h_candidats = []
    total_2h_candidats = []
    p_2h_home, p_2h_away = proba_moneyline(mu_home_2h, mu_away_2h, SIGMA_MT)
    if ml_2h and len(ml_2h) == 2:
        c = eval_candidat("2H - Domicile", p_2h_home, ml_2h[0], "Moneyline 2H")
        if c:
            ml_2h_candidats.append(c)
        c = eval_candidat("2H - Exterieur", p_2h_away, ml_2h[1], "Moneyline 2H")
        if c:
            ml_2h_candidats.append(c)
    if total_2h and len(total_2h) == 3:
        ligne_2h = total_2h[0]
        co = total_2h[1]
        cu = total_2h[2]
        p_over, p_under = proba_total(mu_total_2h, ligne_2h, SIGMA_MT)
        c = eval_candidat("2H Over " + str(ligne_2h), p_over, co, "Total 2H")
        if c:
            total_2h_candidats.append(c)
        c = eval_candidat("2H Under " + str(ligne_2h), p_under, cu, "Total 2H")
        if c:
            total_2h_candidats.append(c)

    # --- FUSION TOUS CANDIDATS ---
    tous = []
    tous.extend(ml_candidats)
    tous.extend(spread_candidats)
    tous.extend(total_ft_candidats)
    tous.extend(ml_1h_candidats)
    tous.extend(total_1h_candidats)
    tous.extend(ml_2h_candidats)
    tous.extend(total_2h_candidats)

    tous.sort(key=lambda x: x["fiabilite"], reverse=True)

    pari_retenu = None
    for c in tous:
        if c["passe_filtres"] and c["stake"] > 0:
            pari_retenu = c
            break

    return {
        "mu_home": round(mu_home, 1),
        "mu_away": round(mu_away, 1),
        "mu_total": round(mu_total, 1),
        "mu_total_1h": round(mu_total_1h, 1),
        "mu_total_2h": round(mu_total_2h, 1),
        "details": details,
        "p_ml_home": round(p_ml_home, 4),
        "p_ml_away": round(p_ml_away, 4),
        "p_1h_home": round(p_1h_home, 4),
        "p_1h_away": round(p_1h_away, 4),
        "p_2h_home": round(p_2h_home, 4),
        "p_2h_away": round(p_2h_away, 4),
        "ml_candidats": ml_candidats,
        "spread_candidats": spread_candidats,
        "total_ft_candidats": total_ft_candidats,
        "ml_1h_candidats": ml_1h_candidats,
        "total_1h_candidats": total_1h_candidats,
        "ml_2h_candidats": ml_2h_candidats,
        "total_2h_candidats": total_2h_candidats,
        "pari_retenu": pari_retenu,
}
