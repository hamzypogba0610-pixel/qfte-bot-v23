"""
qfte_engine/basket.py
---------------------
Moteur QFTE V23.0 - Basketball multi-ligues.
True Sigma + Pace + Q1-Q4 + MARKET FORENSICS + META-ENSEMBLE.
"""

import math
import random
from qfte_engine.signature import (
    analyser_true_sigma,
    sigma_mt_depuis_ft,
    sigma_quart_depuis_ft,
)
from qfte_engine.forensics import (
    analyser_market_forensics,
    ajuster_fiabilite,
)


SIGMA_PAR_LIGUE = {
    "nba": (11.5, 8.0),
    "euroleague": (9.0, 7.0),
    "lnb": (9.5, 7.0),
    "acb": (9.0, 7.0),
    "bbl": (9.5, 7.0),
    "lega": (9.5, 7.0),
    "ncaa": (10.0, 7.5),
    "fiba": (10.0, 7.5),
    "autre": (10.5, 7.5),
}


def get_sigmas(ligue):
    if not ligue:
        return (11.0, 8.0)
    return SIGMA_PAR_LIGUE.get(ligue, (10.5, 7.5))


def norm_cdf(x, mu=0.0, sigma=1.0):
    if sigma <= 0:
        return 0.0 if x < mu else 1.0
    return 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))


def moy(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return 0.0
    return sum(v) / len(v)


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


def appliquer_forensics_au_candidat(c, forensics):
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

    dec, niv = classify(c["fiabilite"], c["ev"])
    c["decision"] = dec
    c["niveau"] = niv

    passe, raisons = appliquer_filtres(c["p"], c["cote"], c["ev"], c["fiabilite"])
    c["passe_filtres"] = passe
    c["raisons_rejet"] = raisons
    c["stake"] = compute_stake(c["p"], c["cote"], c["fiabilite"], c["ev"]) if passe else 0.0

    return c


def sample_normal(mu, sigma):
    """Tirage Normal via Box-Muller."""
    u1 = random.random()
    u2 = random.random()
    z = math.sqrt(-2 * math.log(u1 + 1e-10)) * math.cos(2 * math.pi * u2)
    return mu + sigma * z



def compute_lambdas_basket(
    home_ctx, home_glob, away_ctx, away_glob,
    h2h, bd, be, fd, fe, pd, pe, te,
    pace_dom=None, offrtg_dom=None, defrtg_dom=None,
    pace_ext=None, offrtg_ext=None, defrtg_ext=None
):
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

    mu_home_base = (hbp + abc) / 2.0
    mu_away_base = (abp + hbc) / 2.0

    pace_applique = False
    if all(v is not None and v > 0 for v in [pace_dom, offrtg_dom, defrtg_dom, pace_ext, offrtg_ext, defrtg_ext]):
        pace_moy = (pace_dom + pace_ext) / 2.0
        mu_home_avance = (offrtg_dom * defrtg_ext / 100.0) * (pace_moy / 100.0)
        mu_away_avance = (offrtg_ext * defrtg_dom / 100.0) * (pace_moy / 100.0)
        mu_home = 0.6 * mu_home_avance + 0.4 * mu_home_base
        mu_away = 0.6 * mu_away_avance + 0.4 * mu_away_base
        pace_applique = True
    else:
        mu_home = mu_home_base
        mu_away = mu_away_base

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
        "mu_home_base": round(mu_home_base, 1),
        "mu_away_base": round(mu_away_base, 1),
        "pace_applique": pace_applique,
        "f_class_home": fc_h,
        "f_class_away": fc_a,
        "f_h2h_home": fh2h_h,
        "f_h2h_away": fh2h_a,
        "f_bless_dom": facteur_blessures(bd),
        "f_bless_ext": facteur_blessures(be),
        "f_fatigue_dom": facteur_fatigue(fd),
        "f_fatigue_ext": facteur_fatigue(fe),
    }


def proba_moneyline(mu_home, mu_away, sigma):
    mu_diff = mu_home - mu_away
    sigma_diff = sigma * math.sqrt(2)
    p_home = 1 - norm_cdf(0, mu_diff, sigma_diff)
    p_away = norm_cdf(0, mu_diff, sigma_diff)
    return p_home, p_away


def proba_spread(mu_home, mu_away, hcp, sigma):
    mu_ajuste = mu_home - mu_away + hcp
    p_home = 1 - norm_cdf(0, mu_ajuste, sigma * math.sqrt(2))
    p_away = norm_cdf(0, mu_ajuste, sigma * math.sqrt(2))
    return p_home, p_away


def proba_total(mu_total, ligne, sigma):
    p_over = 1 - norm_cdf(ligne, mu_total, sigma)
    p_under = norm_cdf(ligne, mu_total, sigma)
    return p_over, p_under


RATIO_1H = 0.51
RATIO_2H = 0.49
RATIO_Q1 = 0.27
RATIO_Q2 = 0.24
RATIO_Q3 = 0.25
RATIO_Q4 = 0.24


def monte_carlo_basket(mu_home, mu_away, sigma, n=5000):
    """Simule n matchs basket via distribution Normale."""
    compteurs = {
        "victoires_dom": 0,
        "victoires_ext": 0,
        "scores_home": [],
        "scores_away": [],
        "totaux": [],
    }
    for _ in range(n):
        sh = sample_normal(mu_home, sigma)
        sa = sample_normal(mu_away, sigma)
        sh = max(sh, 60.0)
        sa = max(sa, 60.0)
        compteurs["scores_home"].append(sh)
        compteurs["scores_away"].append(sa)
        compteurs["totaux"].append(sh + sa)
        if sh > sa:
            compteurs["victoires_dom"] += 1
        else:
            compteurs["victoires_ext"] += 1
    return compteurs, n


def extraire_probas_mc_basket(compteurs, n):
    return {
        "p1": round(compteurs["victoires_dom"] / n, 4),
        "p2": round(compteurs["victoires_ext"] / n, 4),
        "px": 0.0,
    }


def calculer_sous_probas_basket(mu_home, mu_away, sigma_ft):
    """
    Expose les 4 sous-probas pour le Meta-Ensemble :
      - Poisson-like (baseline Normal sans ajustement)
      - DC-equivalent (Normal avec correction "faible ecart")
      - Monte Carlo
      - Bayesien (moyenne ponderee)
    """
    # 1. Baseline (Normal pur sur mu brut)
    p_ml_home, p_ml_away = proba_moneyline(mu_home, mu_away, sigma_ft)
    probas_baseline = {
        "p1": round(p_ml_home, 4),
        "px": 0.0,
        "p2": round(p_ml_away, 4),
    }

    # 2. DC-equivalent (Normal avec sigma legerement reduit - correction)
    sigma_dc = sigma_ft * 0.95
    p_dc_home, p_dc_away = proba_moneyline(mu_home, mu_away, sigma_dc)
    probas_dc = {
        "p1": round(p_dc_home, 4),
        "px": 0.0,
        "p2": round(p_dc_away, 4),
    }

    # 3. Monte Carlo
    compteurs, n = monte_carlo_basket(mu_home, mu_away, sigma_ft, n=5000)
    probas_mc = extraire_probas_mc_basket(compteurs, n)

    # 4. Bayesien : moyenne ponderee 60% baseline + 40% MC
    p_bayes_home = 0.6 * probas_baseline["p1"] + 0.4 * probas_mc["p1"]
    p_bayes_away = 0.6 * probas_baseline["p2"] + 0.4 * probas_mc["p2"]
    probas_bayes = {
        "p1": round(p_bayes_home, 4),
        "px": 0.0,
        "p2": round(p_bayes_away, 4),
    }

    return {
        "probas_poisson": probas_baseline,
        "probas_dc": probas_dc,
        "probas_mc": probas_mc,
        "probas_bayes": probas_bayes,
        "total_points_liste": compteurs["totaux"],
    }



def analyser_match_basket(
    home_ctx, home_glob, away_ctx, away_glob,
    h2h_matchs, hcp_lignes, ou_lignes,
    bd, be, fd, fe, pd, pe, te,
    ml_ft=None, ml_1h=None, ml_2h=None,
    total_1h=None, total_2h=None,
    ligue=None,
    pace_dom=None, offrtg_dom=None, defrtg_dom=None,
    pace_ext=None, offrtg_ext=None, defrtg_ext=None,
    q1=None, q2=None, q3=None, q4=None,
    open_1=None, open_2=None,
    curr_1=None, curr_2=None
):
    from qfte_engine.stacking import analyser_meta_ensemble, ajuster_fiabilite_pcs

    if h2h_matchs is None:
        h2h_matchs = []
    if hcp_lignes is None:
        hcp_lignes = []
    if ou_lignes is None:
        ou_lignes = []

    # === QFTE SIGNATURE - True Sigma ===
    signature = analyser_true_sigma(home_ctx, away_ctx, home_glob, away_glob, ligue)
    sigma_ft = signature["sigma_final"]
    sigma_mt = sigma_mt_depuis_ft(sigma_ft)
    sigma_quart = sigma_quart_depuis_ft(sigma_ft)

    mu_home, mu_away, details = compute_lambdas_basket(
        home_ctx, home_glob, away_ctx, away_glob,
        h2h_matchs, bd, be, fd, fe, pd, pe, te,
        pace_dom, offrtg_dom, defrtg_dom,
        pace_ext, offrtg_ext, defrtg_ext
    )
    mu_total = mu_home + mu_away

    # === META-ENSEMBLE STACKING ===
    sous_probas = calculer_sous_probas_basket(mu_home, mu_away, sigma_ft)

    sigma_ligue_ref = get_sigmas(ligue)[0] if ligue else 11.0
    volatilite_norm = min(sigma_ft / max(sigma_ligue_ref, 1.0), 1.0)
    ecart_forces_norm = min(abs(mu_home - mu_away) / 30.0, 1.0)

    # Forensics avant le stacking (pour sharpe_signal dans le contexte)
    forensics = analyser_market_forensics(open_1, 0, open_2, curr_1, 0, curr_2)
    forensics_sharpe = 0.0
    if forensics and forensics.get("disponible"):
        forensics_sharpe = forensics["sharpe_signal"]["sharpe_signal"]

    contexte_stack = {
        "volatilite": volatilite_norm,
        "ecart_forces": ecart_forces_norm,
        "ligue": ligue,
        "forensics_sharpe": forensics_sharpe,
    }

    stacking = analyser_meta_ensemble(
        sous_probas["probas_poisson"],
        sous_probas["probas_dc"],
        sous_probas["probas_mc"],
        sous_probas["probas_bayes"],
        contexte_stack
    )

    p1 = stacking["p1_final"]
    p2 = stacking["p2_final"]
    px = 0.0

    # === MARKET FORENSICS ===
    # deja calcule ci-dessus

    # Candidats Moneyline
    ml_candidats = []
    if ml_ft and len(ml_ft) == 2:
        c = eval_candidat("FT - Domicile", p1, ml_ft[0], "Moneyline FT")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            ml_candidats.append(c)
        c = eval_candidat("FT - Exterieur", p2, ml_ft[1], "Moneyline FT")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            ml_candidats.append(c)

    # Spread
    spread_candidats = []
    for l in hcp_lignes:
        hd = l.get("hcp_dom")
        he = l.get("hcp_ext")
        cd = l.get("cote_dom")
        ce = l.get("cote_ext")
        if hd is not None and cd:
            p_dom, _ = proba_spread(mu_home, mu_away, hd, sigma_ft)
            c = eval_candidat("Spread " + str(hd) + " (Dom)", p_dom, cd, "Spread FT")
            if c:
                c = appliquer_forensics_au_candidat(c, forensics)
                c = appliquer_stacking_au_candidat(c, stacking)
                spread_candidats.append(c)
        if he is not None and ce:
            _, p_ext = proba_spread(mu_home, mu_away, he, sigma_ft)
            c = eval_candidat("Spread " + str(he) + " (Ext)", p_ext, ce, "Spread FT")
            if c:
                c = appliquer_forensics_au_candidat(c, forensics)
                c = appliquer_stacking_au_candidat(c, stacking)
                spread_candidats.append(c)

    # Total FT
    total_ft_candidats = []
    for l in ou_lignes:
        ligne = l.get("ligne")
        co = l.get("cote_over")
        cu = l.get("cote_under")
        if ligne is None:
            continue
        p_over, p_under = proba_total(mu_total, ligne, sigma_ft)
        if co:
            c = eval_candidat("Over " + str(ligne), p_over, co, "Total FT")
            if c:
                c = appliquer_forensics_au_candidat(c, forensics)
                c = appliquer_stacking_au_candidat(c, stacking)
                total_ft_candidats.append(c)
        if cu:
            c = eval_candidat("Under " + str(ligne), p_under, cu, "Total FT")
            if c:
                c = appliquer_forensics_au_candidat(c, forensics)
                c = appliquer_stacking_au_candidat(c, stacking)
                total_ft_candidats.append(c)

    # 1H
    mu_total_1h = mu_total * RATIO_1H
    mu_home_1h = mu_home * RATIO_1H
    mu_away_1h = mu_away * RATIO_1H
    ml_1h_candidats = []
    total_1h_candidats = []
    p_1h_home, p_1h_away = proba_moneyline(mu_home_1h, mu_away_1h, sigma_mt)
    if ml_1h and len(ml_1h) == 2:
        c = eval_candidat("1H - Domicile", p_1h_home, ml_1h[0], "Moneyline 1H")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            ml_1h_candidats.append(c)
        c = eval_candidat("1H - Exterieur", p_1h_away, ml_1h[1], "Moneyline 1H")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            ml_1h_candidats.append(c)
    if total_1h and len(total_1h) == 3:
        ligne_1h = total_1h[0]
        co = total_1h[1]
        cu = total_1h[2]
        p_over, p_under = proba_total(mu_total_1h, ligne_1h, sigma_mt)
        c = eval_candidat("1H Over " + str(ligne_1h), p_over, co, "Total 1H")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            total_1h_candidats.append(c)
        c = eval_candidat("1H Under " + str(ligne_1h), p_under, cu, "Total 1H")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            total_1h_candidats.append(c)

    # 2H
    mu_total_2h = mu_total * RATIO_2H
    mu_home_2h = mu_home * RATIO_2H
    mu_away_2h = mu_away * RATIO_2H
    ml_2h_candidats = []
    total_2h_candidats = []
    p_2h_home, p_2h_away = proba_moneyline(mu_home_2h, mu_away_2h, sigma_mt)
    if ml_2h and len(ml_2h) == 2:
        c = eval_candidat("2H - Domicile", p_2h_home, ml_2h[0], "Moneyline 2H")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            ml_2h_candidats.append(c)
        c = eval_candidat("2H - Exterieur", p_2h_away, ml_2h[1], "Moneyline 2H")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            ml_2h_candidats.append(c)
    if total_2h and len(total_2h) == 3:
        ligne_2h = total_2h[0]
        co = total_2h[1]
        cu = total_2h[2]
        p_over, p_under = proba_total(mu_total_2h, ligne_2h, sigma_mt)
        c = eval_candidat("2H Over " + str(ligne_2h), p_over, co, "Total 2H")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            total_2h_candidats.append(c)
        c = eval_candidat("2H Under " + str(ligne_2h), p_under, cu, "Total 2H")
        if c:
            c = appliquer_forensics_au_candidat(c, forensics)
            c = appliquer_stacking_au_candidat(c, stacking)
            total_2h_candidats.append(c)

    # Quarts
    quart_data = [
        ("Q1", q1, RATIO_Q1),
        ("Q2", q2, RATIO_Q2),
        ("Q3", q3, RATIO_Q3),
        ("Q4", q4, RATIO_Q4),
    ]
    quarts_resultats = {}
    for nom, data, ratio in quart_data:
        resultats_q = {"ml": [], "total": [], "mu": round(mu_total * ratio, 1)}
        if data:
            mu_q = mu_total * ratio
            mu_h = mu_home * ratio
            mu_a = mu_away * ratio
            total_cfg = data.get("total")
            ml_cfg = data.get("ml")
            if total_cfg and len(total_cfg) == 3:
                ligne_q = total_cfg[0]
                co_q = total_cfg[1]
                cu_q = total_cfg[2]
                p_o, p_u = proba_total(mu_q, ligne_q, sigma_quart)
                c = eval_candidat(nom + " Over " + str(ligne_q), p_o, co_q, "Total " + nom)
                if c:
                    c = appliquer_forensics_au_candidat(c, forensics)
                    c = appliquer_stacking_au_candidat(c, stacking)
                    resultats_q["total"].append(c)
                c = eval_candidat(nom + " Under " + str(ligne_q), p_u, cu_q, "Total " + nom)
                if c:
                    c = appliquer_forensics_au_candidat(c, forensics)
                    c = appliquer_stacking_au_candidat(c, stacking)
                    resultats_q["total"].append(c)
            if ml_cfg and len(ml_cfg) == 2:
                p_h, p_a = proba_moneyline(mu_h, mu_a, sigma_quart)
                c = eval_candidat(nom + " - Domicile", p_h, ml_cfg[0], "Moneyline " + nom)
                if c:
                    c = appliquer_forensics_au_candidat(c, forensics)
                    c = appliquer_stacking_au_candidat(c, stacking)
                    resultats_q["ml"].append(c)
                c = eval_candidat(nom + " - Exterieur", p_a, ml_cfg[1], "Moneyline " + nom)
                if c:
                    c = appliquer_forensics_au_candidat(c, forensics)
                    c = appliquer_stacking_au_candidat(c, stacking)
                    resultats_q["ml"].append(c)
        quarts_resultats[nom] = resultats_q

    tous = []
    tous.extend(ml_candidats)
    tous.extend(spread_candidats)
    tous.extend(total_ft_candidats)
    tous.extend(ml_1h_candidats)
    tous.extend(total_1h_candidats)
    tous.extend(ml_2h_candidats)
    tous.extend(total_2h_candidats)
    for nom in ["Q1", "Q2", "Q3", "Q4"]:
        tous.extend(quarts_resultats[nom]["ml"])
        tous.extend(quarts_resultats[nom]["total"])

    tous.sort(key=lambda x: x["fiabilite"], reverse=True)

    pari_retenu = None
    for c in tous:
        if c["passe_filtres"] and c["stake"] > 0:
            pari_retenu = c
            break

    if pari_retenu:
        multi = signature["multiplicateur_stake"]
        pari_retenu["stake_origine"] = pari_retenu["stake"]
        pari_retenu["stake"] = round(pari_retenu["stake"] * multi, 2)

    return {
        "mu_home": round(mu_home, 1),
        "mu_away": round(mu_away, 1),
        "mu_total": round(mu_total, 1),
        "mu_total_1h": round(mu_total_1h, 1),
        "mu_total_2h": round(mu_total_2h, 1),
        "sigma_ft": sigma_ft,
        "sigma_mt": sigma_mt,
        "sigma_quart": sigma_quart,
        "signature": signature,
        "forensics": forensics,
        "stacking": stacking,
        "details": details,
        "p_ml_home": round(p1, 4),
        "p_ml_away": round(p2, 4),
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
        "quarts": quarts_resultats,
        "pari_retenu": pari_retenu,
    }


def appliquer_stacking_au_candidat(c, stacking):
    """Ajuste la fiabilite d'un candidat selon le PCS du stacking."""
    if not stacking or not stacking.get("disponible"):
        c["pcs_label"] = None
        c["ajustement_stacking"] = 0.0
        return c

    from qfte_engine.stacking import ajuster_fiabilite_pcs

    pcs = stacking["pcs"]
    fiab_avant = c["fiabilite"]
    fiab_apres = ajuster_fiabilite_pcs(fiab_avant, pcs)
    ajustement = round(fiab_apres - fiab_avant, 3)

    c["fiabilite"] = fiab_apres
    c["pcs_label"] = pcs["label"]
    c["ajustement_stacking"] = ajustement

    dec, niv = classify(c["fiabilite"], c["ev"])
    c["decision"] = dec
    c["niveau"] = niv

    passe, raisons = appliquer_filtres(c["p"], c["cote"], c["ev"], c["fiabilite"])
    c["passe_filtres"] = passe
    c["raisons_rejet"] = raisons
    c["stake"] = compute_stake(c["p"], c["cote"], c["fiabilite"], c["ev"]) if passe else 0.0

    return c
