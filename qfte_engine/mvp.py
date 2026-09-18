"""
qfte_engine/mvp.py
------------------
Moteur QFTE V23.0 - Football
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
from qfte_engine.stacking import (
    analyser_meta_ensemble,
    ajuster_fiabilite_pcs,
)
from qfte_engine.cross_market import (
    analyser_cross_market,
    ajuster_fiabilite_consistency,
)
from qfte_engine.regime import analyser_regime
from qfte_engine.time_decay import (
    extraire_moyennes_ponderees,
    fusion_ponderee,
)


def poisson_pmf(k, lam):
    if lam <= 0:
        lam = 0.01
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def compute_score_matrix(lambda_home, lambda_away, max_goals=8):
    matrix = {}

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            matrix[(i, j)] = (
                poisson_pmf(i, lambda_home)
                * poisson_pmf(j, lambda_away)
            )

    return matrix


def compute_1x2(matrix):
    p1 = 0.0
    px = 0.0
    p2 = 0.0

    for (i, j), p in matrix.items():
        if i > j:
            p1 += p
        elif i == j:
            px += p
        else:
            p2 += p

    total = p1 + px + p2

    if total > 0:
        p1 = p1 / total
        px = px / total
        p2 = p2 / total

    return p1, px, p2


def compute_ratio_ht(matchs):
    m_ht = [
        m for m in matchs
        if m.get("ht_bp") is not None
    ]

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

    inv = [1 / c for c in cotes]
    total = sum(inv)

    if total <= 0:
        return None

    return [i / total for i in inv]


def proba_handicap_dom(matrix, hcp):
    p_gain = 0.0
    p_remb = 0.0

    for (i, j), p in matrix.items():
        marge = i - j
        seuil = -hcp

        if marge > seuil:
            p_gain += p

        elif (
            marge == seuil
            and abs(seuil - round(seuil)) < 1e-9
        ):
            p_remb += p

    return p_gain, p_remb


def proba_handicap_ext(matrix, hcp):
    p_gain = 0.0
    p_remb = 0.0

    for (i, j), p in matrix.items():
        marge = j - i
        seuil = -hcp

        if marge > seuil:
            p_gain += p

        elif (
            marge == seuil
            and abs(seuil - round(seuil)) < 1e-9
        ):
            p_remb += p

    return p_gain, p_remb


def moy(vals):
    v = [x for x in vals if x is not None]

    if not v:
        return 0.0

    return sum(v) / len(v)


def facteur_meteo(m):
    return {
        "normale": 1.00,
        "pluie": 0.90,
        "neige": 0.85,
        "chaleur_extreme": 0.90,
        "vent_fort": 0.92,
    }.get(m, 1.00)


def facteur_enjeu(e):
    return {
        "normal": 1.00,
        "derby": 0.95,
        "finale": 0.92,
        "fin_saison": 0.97,
        "relegation": 0.95,
    }.get(e, 1.00)


def facteur_blessures(a):
    return 0.85 if a else 1.00


def facteur_fatigue(a):
    return 0.90 if a else 1.00


def facteur_classement(pos_dom, pos_ext, total):
    if (
        pos_dom is None
        or pos_ext is None
        or total is None
        or total <= 1
    ):
        return (1.0, 1.0)

    ecart = max(
        min((pos_ext - pos_dom) / total, 1.0),
        -1.0,
    )

    ajust = ecart * 0.15

    return (
        round(1.0 + ajust, 3),
        round(1.0 - ajust, 3),
    )


def facteur_ht(matchs):
    m_ht = [
        m for m in matchs
        if m.get("ht_bp") is not None
    ]

    if not m_ht:
        return 1.00

    total_bp = sum(m["bp"] for m in m_ht)
    total_ht_bp = sum(m["ht_bp"] for m in m_ht)

    if total_bp == 0:
        return 1.00

    ratio_2e = (
        total_bp - total_ht_bp
    ) / total_bp

    ecart = (
        ratio_2e - 0.5
    ) * 0.20

    ecart = max(
        min(ecart, 0.05),
        -0.05,
    )

    return 1.00 + ecart


def facteur_forme_recente(matchs):
    if len(matchs) < 5:
        return 1.00

    points = []

    for m in matchs:
        diff = m["bp"] - m["bc"]

        if diff > 0:
            points.append(3)
        elif diff == 0:
            points.append(1)
        else:
            points.append(0)

    moy_5 = sum(points) / len(points)
    moy_3 = sum(points[:3]) / 3.0

    ecart = max(
        min((moy_3 - moy_5) / 3.0, 1.0),
        -1.0,
    )

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

    return (
        round(1.0 + ajust, 3),
        round(1.0 - ajust, 3),
    )


def compute_ev(p, cote):
    if cote <= 0:
        return 0.0

    return p * cote - 1.0


def compute_reliability(p, cote, ev):
    f_p = p

    if ev < 0:
        f_v = 0.0
    else:
        f_v = min(ev / 0.15, 1.0)

    if cote < 1.3:
        f_c = 0.7
    elif cote > 8.0:
        f_c = 0.5
    else:
        f_c = 1.0

    fiab = (
        0.50 * f_p
        + 0.30 * f_v
        + 0.20 * f_c
    )

    fiab = min(
        max(fiab, 0.0),
        1.0,
    )

    return round(fiab, 3)


def compute_stake(p, cote, fiab, ev):
    if ev <= 0 or cote <= 1:
        return 0.0

    f_star = (
        p * cote - 1.0
    ) / (cote - 1.0)

    if fiab >= 0.85:
        lam = 0.30
        plaf = 1.5

    elif fiab >= 0.75:
        lam = 0.25
        plaf = 1.0

    elif fiab >= 0.65:
        lam = 0.15
        plaf = 0.5

    else:
        lam = 0.10
        plaf = 0.25

    stake = f_star * lam * 100

    stake = min(
        stake,
        plaf,
    )

    stake = max(
        stake,
        0.0,
    )

    return round(stake, 2)


SEUIL_FIABILITE = 0.75
SEUIL_VALUE_1X2 = 0.05
SEUIL_CONFIANCE = 0.70


def appliquer_filtres_discipline(
    p,
    cote,
    ev,
    fiab,
):
    r = []

    if fiab < SEUIL_FIABILITE:
        r.append(
            "Fiabilite "
            + str(fiab)
            + " < "
            + str(SEUIL_FIABILITE)
        )

    if ev < SEUIL_VALUE_1X2:
        r.append(
            "Value "
            + str(round(ev * 100, 2))
            + "% < "
            + str(int(SEUIL_VALUE_1X2 * 100))
            + "%"
        )

    if p < SEUIL_CONFIANCE:
        r.append(
            "Confiance "
            + str(round(p * 100, 2))
            + "% < "
            + str(int(SEUIL_CONFIANCE * 100))
            + "%"
        )

    return (
        len(r) == 0,
        r,
    )


def classify_decision(fiab, ev):
    if (
        fiab >= 0.85
        and ev >= SEUIL_VALUE_1X2
    ):
        return "ATTAQUE FORTE", "ELITE"

    elif (
        fiab >= 0.75
        and ev >= SEUIL_VALUE_1X2
    ):
        return "ATTAQUE", "PREMIUM"

    elif fiab >= 0.65:
        return "LEAN", "GOOD"

    elif fiab >= 0.55:
        return "SURVEILLANCE", "SURVEILLANCE"

    else:
        return "EVITER", "AVOID"


def eval_candidat_simple(
    label,
    p,
    cote,
    marche=None,
):
    if not cote or cote <= 0:
        return None

    ev = compute_ev(
        p,
        cote,
    )

    fiab = compute_reliability(
        p,
        cote,
        ev,
    )

    passe, raisons = appliquer_filtres_discipline(
        p,
        cote,
        ev,
        fiab,
    )

    dec, niv = classify_decision(
        fiab,
        ev,
    )

    stake = (
        compute_stake(
            p,
            cote,
            fiab,
            ev,
        )
        if passe
        else 0.0
    )

    return {
        "selection": label,
        "marche": marche or "1X2",
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

def appliquer_forensics_au_candidat(candidat, forensics):
    if not candidat or not forensics:
        return candidat

    fiab_adj = ajuster_fiabilite(
        candidat["fiabilite"],
        forensics,
    )

    candidat["fiabilite"] = round(
        max(0.0, min(fiab_adj, 1.0)),
        3,
    )

    candidat["ev"] = round(
        candidat["p"] * candidat["cote"] - 1.0,
        4,
    )

    candidat["passe_filtres"] = (
        candidat["fiabilite"] >= SEUIL_FIABILITE
        and candidat["ev"] >= SEUIL_VALUE_1X2
        and candidat["p"] >= SEUIL_CONFIANCE
    )

    candidat["decision"], candidat["niveau"] = classify_decision(
        candidat["fiabilite"],
        candidat["ev"],
    )

    candidat["stake"] = (
        compute_stake(
            candidat["p"],
            candidat["cote"],
            candidat["fiabilite"],
            candidat["ev"],
        )
        if candidat["passe_filtres"]
        else 0.0
    )

    return candidat


def appliquer_stacking_au_candidat(candidat, stacking):
    if not candidat or not stacking:
        return candidat

    fiab_adj = ajuster_fiabilite_pcs(
        candidat["fiabilite"],
        stacking,
    )

    candidat["fiabilite"] = round(
        max(0.0, min(fiab_adj, 1.0)),
        3,
    )

    candidat["passe_filtres"] = (
        candidat["fiabilite"] >= SEUIL_FIABILITE
        and candidat["ev"] >= SEUIL_VALUE_1X2
        and candidat["p"] >= SEUIL_CONFIANCE
    )

    candidat["decision"], candidat["niveau"] = classify_decision(
        candidat["fiabilite"],
        candidat["ev"],
    )

    candidat["stake"] = (
        compute_stake(
            candidat["p"],
            candidat["cote"],
            candidat["fiabilite"],
            candidat["ev"],
        )
        if candidat["passe_filtres"]
        else 0.0
    )

    return candidat


def calcul_handicap_complet(
    matrix,
    cote_dom,
    cote_ext,
    hcp,
):
    p_dom_gain, p_dom_remb = proba_handicap_dom(
        matrix,
        hcp,
    )

    p_ext_gain, p_ext_remb = proba_handicap_ext(
        matrix,
        hcp,
    )

    candidats = []

    if cote_dom and cote_dom > 0:
        candidats.append(
            eval_candidat_simple(
                "Domicile AH " + str(hcp),
                p_dom_gain,
                cote_dom,
                "Asian Handicap",
            )
        )

    if cote_ext and cote_ext > 0:
        candidats.append(
            eval_candidat_simple(
                "Exterieur AH " + str(hcp),
                p_ext_gain,
                cote_ext,
                "Asian Handicap",
            )
        )

    return {
        "handicap": hcp,
        "p_dom_gain": round(p_dom_gain, 4),
        "p_dom_remb": round(p_dom_remb, 4),
        "p_ext_gain": round(p_ext_gain, 4),
        "p_ext_remb": round(p_ext_remb, 4),
        "candidats": [
            c for c in candidats
            if c is not None
        ],
    }


def calcul_ou_complet_from_signature(
    matchs_dom,
    matchs_ext,
    cote_over,
    cote_under,
    ligne,
    contexte=None,
):
    signature = analyser_signature_foot(
        matchs_dom,
        matchs_ext,
        contexte or {},
    )

    ou = calculer_over_under_avec_ic(
        signature,
        ligne,
    )

    p_over = ou.get(
        "p_over",
        ou.get("prob_over", 0.0),
    )

    p_under = ou.get(
        "p_under",
        ou.get("prob_under", 0.0),
    )

    candidats = []

    if cote_over and cote_over > 0:
        candidats.append(
            eval_candidat_simple(
                "Over " + str(ligne),
                p_over,
                cote_over,
                "Over/Under",
            )
        )

    if cote_under and cote_under > 0:
        candidats.append(
            eval_candidat_simple(
                "Under " + str(ligne),
                p_under,
                cote_under,
                "Over/Under",
            )
        )

    return {
        "signature": signature,
        "ou": ou,
        "candidats": [
            c for c in candidats
            if c is not None
        ],
    }


def calcul_marches_2mt(
    lambda_total,
    ratio_ht,
    cote_over_ht,
    cote_under_ht,
    cote_btts,
):
    lambda_ht = max(
        lambda_total * ratio_ht,
        0.01,
    )

    lambda_2mt = max(
        lambda_total - lambda_ht,
        0.01,
    )

    p_over_ht = 1.0 - poisson_pmf(
        0,
        lambda_ht,
    )

    p_over_2mt = 1.0 - poisson_pmf(
        0,
        lambda_2mt,
    )

    p_btts = (
        (1.0 - math.exp(-lambda_ht))
        * (1.0 - math.exp(-lambda_2mt))
    )

    candidats = []

    if cote_over_ht and cote_over_ht > 0:
        candidats.append(
            eval_candidat_simple(
                "Over 0.5 HT",
                p_over_ht,
                cote_over_ht,
                "Mi-temps",
            )
        )

    if cote_under_ht and cote_under_ht > 0:
        candidats.append(
            eval_candidat_simple(
                "Under 0.5 HT",
                1.0 - p_over_ht,
                cote_under_ht,
                "Mi-temps",
            )
        )

    if cote_btts and cote_btts > 0:
        candidats.append(
            eval_candidat_simple(
                "BTTS Oui",
                p_btts,
                cote_btts,
                "BTTS",
            )
        )

    return {
        "lambda_ht": round(lambda_ht, 4),
        "lambda_2mt": round(lambda_2mt, 4),
        "p_over_ht": round(p_over_ht, 4),
        "p_over_2mt": round(p_over_2mt, 4),
        "p_btts": round(p_btts, 4),
        "candidats": [
            c for c in candidats
            if c is not None
        ],
    }


def detecter_divergences(
    p_model,
    p_market,
    seuil=0.10,
):
    if p_market is None:
        return {
            "divergence": False,
            "ecart": None,
            "type": None,
        }

    ecart = p_model - p_market

    if abs(ecart) < seuil:
        typ = "faible"

    elif ecart > 0:
        typ = "modele_superieur_marche"

    else:
        typ = "marche_superieur_modele"

    return {
        "divergence": abs(ecart) >= seuil,
        "ecart": round(ecart, 4),
        "type": typ,
    }


def analyser_match_football(
    nom_match,
    matchs_dom,
    matchs_ext,
    h2h_matchs=None,
    contexte=None,
    cotes=None,
    classement=None,
    blessures_dom=False,
    blessures_ext=False,
    fatigue_dom=False,
    fatigue_ext=False,
):
    h2h_matchs = h2h_matchs or []
    contexte = contexte or {}
    cotes = cotes or {}
    classement = classement or {}

    pos_dom = classement.get("dom")
    pos_ext = classement.get("ext")
    total_equipes = classement.get("total")

    bp_dom = moy([
        m.get("bp")
        for m in matchs_dom
    ])

    bc_dom = moy([
        m.get("bc")
        for m in matchs_dom
    ])

    bp_ext = moy([
        m.get("bp")
        for m in matchs_ext
    ])

    bc_ext = moy([
        m.get("bc")
        for m in matchs_ext
    ])

    lh_brut = (
        bp_dom
        + bc_ext
    ) / 2.0

    la_brut = (
        bp_ext
        + bc_dom
    ) / 2.0

    f_dom_classement, f_ext_classement = facteur_classement(
        pos_dom,
        pos_ext,
        total_equipes,
    )

    lh_brut *= f_dom_classement
    la_brut *= f_ext_classement

    lh_brut *= facteur_forme_recente(
        matchs_dom
    )

    la_brut *= facteur_forme_recente(
        matchs_ext
    )

    f_h2h_dom, f_h2h_ext = facteur_h2h(
        h2h_matchs
    )

    lh_brut *= f_h2h_dom
    la_brut *= f_h2h_ext

    lh_brut *= facteur_blessures(
        blessures_dom
    )

    lh_brut *= facteur_blessures(
        blessures_ext
    )

    lh_brut *= facteur_fatigue(
        fatigue_dom
    )

    la_brut *= facteur_fatigue(
        fatigue_ext
    )

    meteo = contexte.get(
        "meteo",
        "normale",
    )

    enjeu = contexte.get(
        "enjeu",
        "normal",
    )

    lh_brut *= facteur_meteo(
        meteo
    )

    la_brut *= facteur_meteo(
        meteo
    )

    lh_brut *= facteur_enjeu(
        enjeu
    )

    la_brut *= facteur_enjeu(
        enjeu
    )

    f_ht = facteur_ht(
        matchs_dom + matchs_ext
    )

    lh_brut *= f_ht
    la_brut *= f_ht

    lambda_home = max(
        lh_brut,
        0.05,
    )

    lambda_away = max(
        la_brut,
        0.05,
    )

    matrix = compute_score_matrix(
        lambda_home,
        lambda_away,
    )

    p1, px, p2 = compute_1x2(
        matrix
    )

    lambda_total = (
        lambda_home
        + lambda_away
    )

    resultat = {
        "match": nom_match,
        "lambda_home": round(
            lambda_home,
            4,
        ),
        "lambda_away": round(
            lambda_away,
            4,
        ),
        "lambda_total": round(
            lambda_total,
            4,
        ),
        "probabilites_1x2": {
            "1": round(p1, 4),
            "X": round(px, 4),
            "2": round(p2, 4),
        },
        "score_matrix": matrix,
    }

    c1 = eval_candidat_simple(
        "Domicile",
        p1,
        cotes.get("1"),
        "1X2",
    )

    cx = eval_candidat_simple(
        "Nul",
        px,
        cotes.get("X"),
        "1X2",
    )

    c2 = eval_candidat_simple(
        "Exterieur",
        p2,
        cotes.get("2"),
        "1X2",
    )

    candidats_1x2 = [
        c for c in [c1, cx, c2]
        if c is not None
    ]

    resultat["marches"] = {
        "1x2": candidats_1x2,
    }

    ratio_ht = compute_ratio_ht(
        matchs_dom + matchs_ext
    )

    candidats_ou = []

    lignes_ou = [
        (
            1.5,
            cotes.get("over_1_5"),
            cotes.get("under_1_5"),
        ),
        (
            2.5,
            cotes.get("over_2_5"),
            cotes.get("under_2_5"),
        ),
        (
            3.5,
            cotes.get("over_3_5"),
            cotes.get("under_3_5"),
        ),
    ]

    for ligne, cote_over, cote_under in lignes_ou:
        ou_result = calcul_ou_complet_from_signature(
            matchs_dom,
            matchs_ext,
            cote_over,
            cote_under,
            ligne,
            contexte,
        )

        candidats_ou.extend(
            ou_result["candidats"]
        )

    resultat["marches"]["over_under"] = candidats_ou

    handicap = calcul_handicap_complet(
        matrix,
        cotes.get("ah_dom"),
        cotes.get("ah_ext"),
        cotes.get("ah_ligne", 0),
    )

    resultat["marches"]["handicap"] = handicap

    marches_2mt = calcul_marches_2mt(
        lambda_total,
        ratio_ht,
        cotes.get("over_ht"),
        cotes.get("under_ht"),
        cotes.get("btts"),
    )

    resultat["marches"]["mi_temps_btts"] = marches_2mt

    tous_candidats = []

    tous_candidats.extend(
        candidats_1x2
    )

    tous_candidats.extend(
        candidats_ou
    )

    tous_candidats.extend(
        handicap.get(
            "candidats",
            [],
        )
    )

    tous_candidats.extend(
        marches_2mt.get(
            "candidats",
            [],
        )
    )

    if tous_candidats:
        candidats_valides = [
            c for c in tous_candidats
            if c is not None
        ]

        candidats_valides.sort(
            key=lambda x: (
                x.get("ev", 0.0),
                x.get("fiabilite", 0.0),
            ),
            reverse=True,
        )

        resultat["meilleurs_candidats"] = (
            candidats_valides[:5]
        )

    else:
        resultat["meilleurs_candidats"] = []

    cote_1 = cotes.get("1")
    cote_x = cotes.get("X")
    cote_2 = cotes.get("2")

    marche_1x2 = [
        c for c in [
            cote_1,
            cote_x,
            cote_2,
        ]
        if c is not None
        and c > 0
    ]

    resultat["marche"] = {
        "probabilites_implicites": (
            demargeage_proportionnel(
                marche_1x2
            )
            if marche_1x2
            else None
        ),
    }

    if cote_1 and cote_1 > 0:
        resultat["divergences_1"] = detecter_divergences(
            p1,
            1.0 / cote_1,
        )

    if cote_x and cote_x > 0:
        resultat["divergences_X"] = detecter_divergences(
            px,
            1.0 / cote_x,
        )

    if cote_2 and cote_2 > 0:
        resultat["divergences_2"] = detecter_divergences(
            p2,
            1.0 / cote_2,
        )

    try:
        signature_foot = analyser_signature_foot(
            matchs_dom,
            matchs_ext,
            contexte,
        )

        resultat["signature_foot"] = signature_foot

    except Exception as e:
        resultat["signature_foot"] = {
            "erreur": str(e),
        }

    try:
        forensics = analyser_market_forensics(
            resultat,
            cotes,
            contexte,
        )

        resultat["market_forensics"] = forensics

    except Exception as e:
        resultat["market_forensics"] = {
            "erreur": str(e),
        }

    try:
        stacking = analyser_meta_ensemble(
            resultat,
            contexte,
        )

        resultat["meta_ensemble"] = stacking

    except Exception as e:
        resultat["meta_ensemble"] = {
            "erreur": str(e),
        }

    try:
        cross_market = analyser_cross_market(
            resultat,
            cotes,
        )

        resultat["cross_market"] = cross_market

    except Exception as e:
        resultat["cross_market"] = {
            "erreur": str(e),
        }

    try:
        regime = analyser_regime(
            matchs_dom,
            matchs_ext,
            contexte,
        )

        resultat["regime"] = regime

    except Exception as e:
        resultat["regime"] = {
            "erreur": str(e),
        }

    try:
        moy_dom = extraire_moyennes_ponderees(
            matchs_dom
        )

        moy_ext = extraire_moyennes_ponderees(
            matchs_ext
        )

        resultat["time_decay"] = {
            "dom": moy_dom,
            "ext": moy_ext,
        }

    except Exception as e:
        resultat["time_decay"] = {
            "erreur": str(e),
        }

    resultat["diagnostic"] = {
        "nb_matchs_dom": len(matchs_dom),
        "nb_matchs_ext": len(matchs_ext),
        "nb_h2h": len(h2h_matchs),
        "ratio_ht": round(
            ratio_ht,
            4,
        ),
        "meteo": meteo,
        "enjeu": enjeu,
        "lambda_total": round(
            lambda_total,
            4,
        ),
    }

    return resultat
