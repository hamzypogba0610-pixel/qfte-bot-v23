"""
qfte_engine/mvp.py
------------------
Moteur QFTE V23.0 - Football
Interface compatible avec main.py V23.0
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


# ============================================================
# OUTILS MATHEMATIQUES
# ============================================================

def poisson_pmf(k, lam):
    lam = max(float(lam), 0.0)
    if k < 0:
        return 0.0

    try:
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def compute_score_matrix(
    lambda_home,
    lambda_away,
    max_goals=8,
):
    matrix = []

    for i in range(max_goals + 1):
        ligne = []

        for j in range(max_goals + 1):
            p = (
                poisson_pmf(i, lambda_home)
                * poisson_pmf(j, lambda_away)
            )
            ligne.append(p)

        matrix.append(ligne)

    total = sum(
        sum(ligne)
        for ligne in matrix
    )

    if total > 0:
        matrix = [
            [
                p / total
                for p in ligne
            ]
            for ligne in matrix
        ]

    return matrix


def compute_1x2(matrix):
    p1 = 0.0
    px = 0.0
    p2 = 0.0

    for i, ligne in enumerate(matrix):
        for j, p in enumerate(ligne):
            if i > j:
                p1 += p
            elif i == j:
                px += p
            else:
                p2 += p

    return p1, px, p2


def compute_ratio_ht(matchs):
    if not matchs:
        return 0.45

    vals = []

    for m in matchs:
        bp = m.get("bp")
        bc = m.get("bc")
        ht_bp = m.get("ht_bp")
        ht_bc = m.get("ht_bc")

        if (
            ht_bp is None
            or ht_bc is None
            or bp is None
            or bc is None
        ):
            continue

        total = bp + bc

        if total <= 0:
            continue

        ht_total = ht_bp + ht_bc

        vals.append(
            max(
                0.20,
                min(
                    0.80,
                    ht_total / total,
                ),
            )
        )

    if not vals:
        return 0.45

    return sum(vals) / len(vals)


def demargeage_proportionnel(cotes):
    if not cotes:
        return {}

    inv = {}

    for k, cote in cotes.items():
        try:
            cote = float(cote)

            if cote > 1:
                inv[k] = 1.0 / cote
        except (TypeError, ValueError):
            continue

    total = sum(inv.values())

    if total <= 0:
        return {}

    return {
        k: v / total
        for k, v in inv.items()
    }


# ============================================================
# HANDICAP
# ============================================================

def proba_handicap_dom(matrix, hcp):
    gain = 0.0
    remboursement = 0.0

    for i, ligne in enumerate(matrix):
        for j, p in enumerate(ligne):
            diff = i - j + hcp

            if diff > 0:
                gain += p

            elif abs(diff) < 1e-9:
                remboursement += p

    return gain, remboursement


def proba_handicap_ext(matrix, hcp):
    gain = 0.0
    remboursement = 0.0

    for i, ligne in enumerate(matrix):
        for j, p in enumerate(ligne):
            diff = j - i - hcp

            if diff > 0:
                gain += p

            elif abs(diff) < 1e-9:
                remboursement += p

    return gain, remboursement


# ============================================================
# UTILITAIRES QFTE
# ============================================================

def moy(vals):
    vals = [
        float(v)
        for v in vals
        if v is not None
    ]

    if not vals:
        return 0.0

    return sum(vals) / len(vals)


def facteur_meteo(m):
    if not m:
        return 1.0

    m = str(m).lower()

    facteurs = {
        "normale": 1.0,
        "normal": 1.0,
        "bonne": 1.0,
        "pluie": 0.96,
        "forte_pluie": 0.92,
        "vent": 0.94,
        "fort_vent": 0.90,
        "neige": 0.90,
        "chaleur": 0.96,
    }

    return facteurs.get(m, 1.0)


def facteur_enjeu(e):
    if not e:
        return 1.0

    e = str(e).lower()

    facteurs = {
        "normal": 1.0,
        "faible": 0.96,
        "important": 1.02,
        "tres_important": 1.03,
        "decisif": 1.04,
    }

    return facteurs.get(e, 1.0)


def facteur_blessures(a):
    if not a:
        return 1.0

    if isinstance(a, bool):
        return 0.94 if a else 1.0

    try:
        x = float(a)
    except (TypeError, ValueError):
        return 1.0

    return max(
        0.80,
        min(
            1.05,
            1.0 - x,
        ),
    )


def facteur_fatigue(a):
    if not a:
        return 1.0

    if isinstance(a, bool):
        return 0.95 if a else 1.0

    try:
        x = float(a)
    except (TypeError, ValueError):
        return 1.0

    return max(
        0.80,
        min(
            1.05,
            1.0 - x,
        ),
    )


def facteur_classement(
    pos_dom,
    pos_ext,
    total,
):
    if (
        pos_dom is None
        or pos_ext is None
        or total is None
        or total <= 1
    ):
        return 1.0, 1.0

    try:
        pos_dom = float(pos_dom)
        pos_ext = float(pos_ext)
        total = float(total)
    except (TypeError, ValueError):
        return 1.0, 1.0

    force_dom = (
        total - pos_dom + 1.0
    ) / total

    force_ext = (
        total - pos_ext + 1.0
    ) / total

    diff = force_dom - force_ext

    f_dom = 1.0 + diff * 0.20
    f_ext = 1.0 - diff * 0.20

    return (
        max(0.85, min(1.15, f_dom)),
        max(0.85, min(1.15, f_ext)),
    )


def facteur_ht(matchs):
    ratio = compute_ratio_ht(matchs)

    if ratio <= 0:
        return 1.0

    return 0.98 + ratio * 0.04


def facteur_forme_recente(matchs):
    if not matchs:
        return 1.0

    score = 0.0
    poids_total = 0.0

    n = len(matchs)

    for i, m in enumerate(matchs):
        bp = m.get("bp", 0) or 0
        bc = m.get("bc", 0) or 0

        poids = i + 1
        score += (
            (bp - bc) * poids
        )
        poids_total += poids

    if poids_total <= 0:
        return 1.0

    forme = score / poids_total

    return max(
        0.88,
        min(
            1.12,
            1.0 + forme * 0.025,
        ),
    )


def facteur_h2h(h2h_matchs):
    if not h2h_matchs:
        return 1.0, 1.0

    dom = 0
    ext = 0

    for m in h2h_matchs:
        bp = m.get("bp")
        bc = m.get("bc")

        if bp is None or bc is None:
            continue

        if bp > bc:
            dom += 1
        elif bc > bp:
            ext += 1

    total = dom + ext

    if total <= 0:
        return 1.0, 1.0

    avantage = (
        dom - ext
    ) / total

    return (
        max(
            0.92,
            min(
                1.08,
                1.0 + avantage * 0.06,
            ),
        ),
        max(
            0.92,
            min(
                1.08,
                1.0 - avantage * 0.06,
            ),
        ),
    )


# ============================================================
# EV / FIABILITE / STAKE
# ============================================================

def compute_ev(p, cote):
    try:
        return (
            float(p) * float(cote)
        ) - 1.0
    except (TypeError, ValueError):
        return -1.0


def compute_reliability(
    p,
    cote,
    ev,
):
    try:
        p = float(p)
        cote = float(cote)
        ev = float(ev)
    except (TypeError, ValueError):
        return 0.0

    fiab = p

    if ev > 0:
        fiab += min(
            0.10,
            ev * 0.20,
        )

    return max(
        0.0,
        min(
            1.0,
            fiab,
        ),
    )


def compute_stake(
    p,
    cote,
    fiab,
    ev,
):
    if (
        p <= 0
        or cote <= 1
        or ev <= 0
        or fiab <= 0
    ):
        return 0.0

    edge = max(
        0.0,
        ev,
    )

    if fiab >= 0.85:
        multiplicateur = 1.5
    elif fiab >= 0.80:
        multiplicateur = 1.0
    elif fiab >= 0.75:
        multiplicateur = 0.5
    else:
        multiplicateur = 0.25

    return round(
        min(
            1.5,
            edge * 100 * multiplicateur,
        ),
        2,
    )


SEUIL_FIABILITE = 0.75
SEUIL_VALUE_1X2 = 0.05
SEUIL_CONFIANCE = 0.70


def appliquer_filtres_discipline(
    p,
    cote,
    ev,
    fiab,
):
    raisons = []

    if p < SEUIL_CONFIANCE:
        raisons.append(
            "Confiance insuffisante"
        )

    if ev < SEUIL_VALUE_1X2:
        raisons.append(
            "Value insuffisante"
        )

    if fiab < SEUIL_FIABILITE:
        raisons.append(
            "Fiabilite insuffisante"
        )

    return (
        len(raisons) == 0,
        raisons,
    )


def classify_decision(
    fiab,
    ev,
):
    if (
        fiab >= 0.85
        and ev >= 0.10
    ):
        return "FORTE", "A"

    if (
        fiab >= 0.80
        and ev >= 0.07
    ):
        return "VALIDEE", "B"

    if (
        fiab >= 0.75
        and ev >= 0.05
    ):
        return "PRUDENCE", "C"

    return "REJET", "D"


# ============================================================
# CANDIDAT SIMPLE
# ============================================================

def eval_candidat_simple(
    label,
    p,
    cote,
    marche=None,
):
    if cote is None:
        return None

    try:
        cote = float(cote)
        p = float(p)
    except (TypeError, ValueError):
        return None

    if cote <= 1:
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

    passe, raisons = (
        appliquer_filtres_discipline(
            p,
            cote,
            ev,
            fiab,
        )
    )

    decision, niveau = (
        classify_decision(
            fiab,
            ev,
        )
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
        "marche": marche,
        "p": round(p, 4),
        "cote": round(cote, 3),
        "ev": round(ev, 4),
        "fiabilite": round(fiab, 3),
        "passe_filtres": passe,
        "raisons_rejet": raisons,
        "decision": decision,
        "niveau": niveau,
        "stake": stake,
                }

# ============================================================
# AJUSTEMENTS QFTE
# ============================================================

def appliquer_forensics_au_candidat(
    candidat,
    forensics,
):
    if not candidat or not forensics:
        return candidat

    fiab_adj = ajuster_fiabilite(
        candidat["fiabilite"],
        forensics,
    )

    candidat["ajustement_forensics"] = round(
        fiab_adj - candidat["fiabilite"],
        4,
    )

    candidat["fiabilite"] = round(
        max(
            0.0,
            min(
                fiab_adj,
                1.0,
            ),
        ),
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

    candidat["decision"], candidat["niveau"] = (
        classify_decision(
            candidat["fiabilite"],
            candidat["ev"],
        )
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


def appliquer_stacking_au_candidat(
    candidat,
    stacking,
):
    if not candidat or not stacking:
        return candidat

    fiab_avant = candidat["fiabilite"]

    fiab_adj = ajuster_fiabilite_pcs(
        candidat["fiabilite"],
        stacking,
    )

    candidat["ajustement_stacking"] = round(
        fiab_adj - fiab_avant,
        4,
    )

    candidat["fiabilite"] = round(
        max(
            0.0,
            min(
                fiab_adj,
                1.0,
            ),
        ),
        3,
    )

    candidat["passe_filtres"] = (
        candidat["fiabilite"] >= SEUIL_FIABILITE
        and candidat["ev"] >= SEUIL_VALUE_1X2
        and candidat["p"] >= SEUIL_CONFIANCE
    )

    candidat["decision"], candidat["niveau"] = (
        classify_decision(
            candidat["fiabilite"],
            candidat["ev"],
        )
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


def appliquer_consistency_au_candidat(
    candidat,
    cross_market,
):
    if not candidat or not cross_market:
        return candidat

    fiab_avant = candidat["fiabilite"]

    fiab_adj = ajuster_fiabilite_consistency(
        candidat["fiabilite"],
        cross_market,
    )

    candidat["ajustement_consistency"] = round(
        fiab_adj - fiab_avant,
        4,
    )

    candidat["fiabilite"] = round(
        max(
            0.0,
            min(
                fiab_adj,
                1.0,
            ),
        ),
        3,
    )

    candidat["passe_filtres"] = (
        candidat["fiabilite"] >= SEUIL_FIABILITE
        and candidat["ev"] >= SEUIL_VALUE_1X2
        and candidat["p"] >= SEUIL_CONFIANCE
    )

    candidat["decision"], candidat["niveau"] = (
        classify_decision(
            candidat["fiabilite"],
            candidat["ev"],
        )
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


# ============================================================
# HANDICAP COMPLET
# ============================================================

def calcul_handicap_complet(
    matrix,
    cote_dom,
    cote_ext,
    hcp,
):
    p_dom_gain, p_dom_remb = (
        proba_handicap_dom(
            matrix,
            hcp,
        )
    )

    p_ext_gain, p_ext_remb = (
        proba_handicap_ext(
            matrix,
            hcp,
        )
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
        "p_dom_gain": round(
            p_dom_gain,
            4,
        ),
        "p_dom_remb": round(
            p_dom_remb,
            4,
        ),
        "p_ext_gain": round(
            p_ext_gain,
            4,
        ),
        "p_ext_remb": round(
            p_ext_remb,
            4,
        ),
        "candidats": [
            c
            for c in candidats
            if c is not None
        ],
    }


# ============================================================
# OVER / UNDER
# ============================================================

def calcul_ou_poisson(
    lambda_total,
    ligne,
):
    """
    Calcul générique O/U à partir de la distribution
    de Poisson du total de buts.
    """

    if lambda_total <= 0:
        return {
            "p_over": 0.0,
            "p_under": 1.0,
        }

    max_goals = 15

    probs = [
        poisson_pmf(
            k,
            lambda_total,
        )
        for k in range(max_goals + 1)
    ]

    total = sum(probs)

    if total > 0:
        probs = [
            p / total
            for p in probs
        ]

    ligne = float(ligne)

    # Ligne entière : Over 2.0 / Under 2.0
    if abs(ligne - round(ligne)) < 1e-9:
        seuil = int(round(ligne))

        p_under = sum(
            probs[:seuil]
        )

        p_push = (
            probs[seuil]
            if 0 <= seuil < len(probs)
            else 0.0
        )

        p_over = max(
            0.0,
            1.0 - p_under - p_push,
        )

        return {
            "p_over": p_over,
            "p_under": p_under,
            "p_push": p_push,
        }

    # Ligne .5 : Over 2.5 / Under 2.5
    seuil = math.floor(ligne)

    p_under = sum(
        probs[:seuil + 1]
    )

    p_over = max(
        0.0,
        1.0 - p_under,
    )

    return {
        "p_over": p_over,
        "p_under": p_under,
        "p_push": 0.0,
    }


def calcul_ou_complet_from_signature(
    matchs_dom,
    matchs_ext,
    cote_over,
    cote_under,
    ligne,
    contexte=None,
):
    contexte = contexte or {}

    try:
        signature = analyser_signature_foot(
            matchs_dom,
            matchs_ext,
            contexte,
        )

        ou = calculer_over_under_avec_ic(
            signature,
            ligne,
        )
    except Exception:
        signature = {}

        lambda_total = (
            moy([
                m.get("bp", 0)
                for m in matchs_dom
            ])
            + moy([
                m.get("bp", 0)
                for m in matchs_ext
            ])
        )

        ou = calcul_ou_poisson(
            max(
                lambda_total,
                0.10,
            ),
            ligne,
        )

    p_over = ou.get(
        "p_over",
        ou.get(
            "prob_over",
            0.0,
        ),
    )

    p_under = ou.get(
        "p_under",
        ou.get(
            "prob_under",
            0.0,
        ),
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
        "ligne": ligne,
        "signature": signature,
        "ou": ou,
        "p_over": round(
            p_over,
            4,
        ),
        "p_under": round(
            p_under,
            4,
        ),
        "candidats": [
            c
            for c in candidats
            if c is not None
        ],
    }


# ============================================================
# MARCHES MI-TEMPS / 2E MI-TEMPS
# ============================================================

def calcul_marches_2mt(
    lambda_total,
    ratio_ht,
    cote_over_ht=None,
    cote_under_ht=None,
    cote_btts=None,
):
    lambda_ht = max(
        lambda_total * ratio_ht,
        0.01,
    )

    lambda_2mt = max(
        lambda_total - lambda_ht,
        0.01,
    )

    p_over_ht = (
        1.0
        - poisson_pmf(
            0,
            lambda_ht,
        )
    )

    p_over_2mt = (
        1.0
        - poisson_pmf(
            0,
            lambda_2mt,
        )
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
        "lambda_ht": round(
            lambda_ht,
            4,
        ),
        "lambda_2mt": round(
            lambda_2mt,
            4,
        ),
        "p_over_ht": round(
            p_over_ht,
            4,
        ),
        "p_over_2mt": round(
            p_over_2mt,
            4,
        ),
        "p_btts": round(
            p_btts,
            4,
        ),
        "candidats": [
            c
            for c in candidats
            if c is not None
        ],
    }


# ============================================================
# DIVERGENCES MODELE / MARCHE
# ============================================================

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
        "ecart": round(
            ecart,
            4,
        ),
        "type": typ,
    }


# ============================================================
# NORMALISATION DES HISTORIQUES
# ============================================================

def _normaliser_matchs(
    matchs,
):
    if not matchs:
        return []

    resultat = []

    for m in matchs:
        if not isinstance(m, dict):
            continue

        resultat.append({
            "bp": m.get("bp"),
            "bc": m.get("bc"),
            "ht_bp": m.get("ht_bp"),
            "ht_bc": m.get("ht_bc"),
        })

    return resultat


def _fusionner_historiques(
    contextuel,
    global_,
):
    contextuel = _normaliser_matchs(
        contextuel
    )

    global_ = _normaliser_matchs(
        global_
    )

    if contextuel and global_:
        # Le contextuel est prioritaire car il représente
        # davantage le contexte spécifique domicile/extérieur.
        return (
            contextuel * 2
            + global_
        )

    if contextuel:
        return contextuel

    return global_


def _selectionner_meilleur_candidat(
    candidats,
):
    valides = [
        c
        for c in candidats
        if c
        and c.get("passe_filtres")
    ]

    if not valides:
        return None

    return max(
        valides,
        key=lambda c: (
            c.get("ev", -999),
            c.get("fiabilite", 0),
            c.get("p", 0),
        ),
    )


def _construire_cotes_marche(
    o1,
    ox,
    o2,
    c1,
    cx,
    c2,
):
    return {
        "open_1": o1,
        "open_x": ox,
        "open_2": o2,
        "curr_1": c1,
        "curr_x": cx,
        "curr_2": c2,
    }


def _probas_marche(
    c1,
    cx,
    c2,
):
    return demargeage_proportionnel({
        "1": c1,
        "X": cx,
        "2": c2,
    })

# ============================================================
# ANALYSE FOOTBALL QFTE V23.0
# COMPATIBILITE MAIN.PY V23.0
# ============================================================

def analyser_match_football(
    home_ctx,
    home_glob,
    away_ctx,
    away_glob,
    open_1,
    open_x,
    open_2,
    curr_1,
    curr_x,
    curr_2,
    meteo="normale",
    enjeu="normal",
    blessures_dom=False,
    blessures_ext=False,
    fatigue_dom=False,
    fatigue_ext=False,
    h2h=None,
    hcp_lignes=None,
    ou_lignes=None,
    pos_dom=None,
    pos_ext=None,
    total_equipes=None,
    parametre_23=None,
    parametre_24=None,
    ligue="autre",
):
    """
    Interface historique attendue par main.py.

    Les 25 arguments sont conserves pour compatibilite.
    Le moteur interne QFTE V23.0 travaille ensuite sur
    des structures normalisees.
    """

    h2h = _normaliser_matchs(h2h)
    hcp_lignes = hcp_lignes or []
    ou_lignes = ou_lignes or []

    home_ctx = _normaliser_matchs(home_ctx)
    home_glob = _normaliser_matchs(home_glob)
    away_ctx = _normaliser_matchs(away_ctx)
    away_glob = _normaliser_matchs(away_glob)

    matchs_dom = _fusionner_historiques(
        home_ctx,
        home_glob,
    )

    matchs_ext = _fusionner_historiques(
        away_ctx,
        away_glob,
    )

    contexte = {
        "meteo": meteo,
        "enjeu": enjeu,
        "ligue": ligue,
        "pos_dom": pos_dom,
        "pos_ext": pos_ext,
        "total_equipes": total_equipes,
    }

    cotes = _construire_cotes_marche(
        open_1,
        open_x,
        open_2,
        curr_1,
        curr_x,
        curr_2,
    )

    # ========================================================
    # 1. ESTIMATION BRUTE DES LAMBDA
    # ========================================================

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
        bp_dom + bc_ext
    ) / 2.0

    la_brut = (
        bp_ext + bc_dom
    ) / 2.0

    # ========================================================
    # 2. CLASSEMENT
    # ========================================================

    f_dom_classement, f_ext_classement = (
        facteur_classement(
            pos_dom,
            pos_ext,
            total_equipes,
        )
    )

    lh_brut *= f_dom_classement
    la_brut *= f_ext_classement

    # ========================================================
    # 3. FORME RECENTE
    # ========================================================

    lh_brut *= facteur_forme_recente(
        matchs_dom
    )

    la_brut *= facteur_forme_recente(
        matchs_ext
    )

    # ========================================================
    # 4. H2H
    # ========================================================

    f_h2h_dom, f_h2h_ext = (
        facteur_h2h(h2h)
    )

    lh_brut *= f_h2h_dom
    la_brut *= f_h2h_ext

    # ========================================================
    # 5. BLESSURES / FATIGUE
    # ========================================================

    lh_brut *= facteur_blessures(
        blessures_dom
    )

    la_brut *= facteur_blessures(
        blessures_ext
    )

    lh_brut *= facteur_fatigue(
        fatigue_dom
    )

    la_brut *= facteur_fatigue(
        fatigue_ext
    )

    # ========================================================
    # 6. METEO / ENJEU
    # ========================================================

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

    # ========================================================
    # 7. STRUCTURE MI-TEMPS
    # ========================================================

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

    lambda_total = (
        lambda_home
        + lambda_away
    )

    # ========================================================
    # 8. MATRICE DE SCORES
    # ========================================================

    matrix = compute_score_matrix(
        lambda_home,
        lambda_away,
    )

    p1, px, p2 = compute_1x2(
        matrix
    )

    # ========================================================
    # 9. MARCHE 1X2
    # ========================================================

    probas_marche = _probas_marche(
        curr_1,
        curr_x,
        curr_2,
    )

    candidats = []

    c = eval_candidat_simple(
        "Victoire domicile",
        p1,
        curr_1,
        "1X2",
    )

    if c:
        candidats.append(c)

    c = eval_candidat_simple(
        "Match nul",
        px,
        curr_x,
        "1X2",
    )

    if c:
        candidats.append(c)

    c = eval_candidat_simple(
        "Victoire exterieur",
        p2,
        curr_2,
        "1X2",
    )

    if c:
        candidats.append(c)

    # ========================================================
    # 10. MARKET FORENSICS
    # ========================================================

    market_forensics = {}

    try:
        market_forensics = analyser_market_forensics(
            {
                "1": open_1,
                "X": open_x,
                "2": open_2,
            },
            {
                "1": curr_1,
                "X": curr_x,
                "2": curr_2,
            },
        )
    except Exception:
        market_forensics = {
            "disponible": False,
            "erreur": "Forensics indisponible",
        }

    # ========================================================
    # 11. META-ENSEMBLE / STACKING
    # ========================================================

    meta_ensemble = {}

    try:
        meta_ensemble = analyser_meta_ensemble(
            lambda_home,
            lambda_away,
            p1,
            px,
            p2,
            matchs_dom,
            matchs_ext,
        )
    except Exception:
        try:
            meta_ensemble = analyser_meta_ensemble(
                p1,
                px,
                p2,
            )
        except Exception:
            meta_ensemble = {
                "disponible": False,
                "erreur": "Meta-ensemble indisponible",
            }

    # ========================================================
    # 12. CROSS-MARKET
    # ========================================================

    cross_market = {}

    try:
        cross_market = analyser_cross_market(
            p1,
            px,
            p2,
            lambda_total,
        )
    except Exception:
        cross_market = {
            "disponible": False,
            "erreur": "Cross-market indisponible",
        }

    # ========================================================
    # 13. REGIME
    # ========================================================

    regime = {}

    try:
        regime = analyser_regime(
            matchs_dom,
            matchs_ext,
            lambda_total,
        )
    except Exception:
        try:
            regime = analyser_regime(
                matchs_dom,
                matchs_ext,
            )
        except Exception:
            regime = {
                "disponible": False,
                "erreur": "Regime indisponible",
            }

    # ========================================================
    # 14. TIME DECAY
    # ========================================================

    time_decay = {}

    try:
        moy_dom_pond = extraire_moyennes_ponderees(
            matchs_dom
        )

        moy_ext_pond = extraire_moyennes_ponderees(
            matchs_ext
        )

        time_decay = {
            "dom": moy_dom_pond,
            "ext": moy_ext_pond,
        }
    except Exception:
        time_decay = {
            "disponible": False,
        }

    # ========================================================
    # 15. SIGNATURE FOOT
    # ========================================================

    signature_foot = {}

    try:
        signature_foot = analyser_signature_foot(
            matchs_dom,
            matchs_ext,
            contexte,
        )
    except Exception:
        signature_foot = {
            "disponible": False,
        }

    # ========================================================
    # 16. AJUSTEMENTS DES CANDIDATS
    # ========================================================

    for candidat in candidats:

        if market_forensics.get(
            "disponible",
            False,
        ):
            try:
                appliquer_forensics_au_candidat(
                    candidat,
                    market_forensics,
                )
            except Exception:
                pass

        if meta_ensemble.get(
            "disponible",
            False,
        ):
            try:
                appliquer_stacking_au_candidat(
                    candidat,
                    meta_ensemble,
                )
            except Exception:
                pass

        if cross_market.get(
            "disponible",
            False,
        ):
            try:
                appliquer_consistency_au_candidat(
                    candidat,
                    cross_market,
                )
            except Exception:
                pass

    # ========================================================
    # 17. HANDICAP
    # ========================================================

    handicap_resultats = []

    for h in hcp_lignes:
        if not isinstance(h, dict):
            continue

        hcp_dom = h.get("hcp_dom")
        hcp_ext = h.get("hcp_ext")
        cote_dom = h.get("cote_dom")
        cote_ext = h.get("cote_ext")

        if hcp_dom is None:
            continue

        try:
            resultat_h = calcul_handicap_complet(
                matrix,
                cote_dom,
                cote_ext,
                float(hcp_dom),
            )

            resultat_h["hcp_ext"] = hcp_ext

            handicap_resultats.append(
                resultat_h
            )

        except Exception:
            continue

    # ========================================================
    # 18. OVER / UNDER
    # ========================================================

    ou_resultats = []

    for ligne_data in ou_lignes:

        if not isinstance(
            ligne_data,
            dict,
        ):
            continue

        ligne = ligne_data.get("ligne")
        cote_over = ligne_data.get("cote_over")
        cote_under = ligne_data.get("cote_under")

        if ligne is None:
            continue

        try:
            resultat_ou = (
                calcul_ou_complet_from_signature(
                    matchs_dom,
                    matchs_ext,
                    cote_over,
                    cote_under,
                    float(ligne),
                    contexte,
                )
            )

            ou_resultats.append(
                resultat_ou
            )

        except Exception:

            ou_calc = calcul_ou_poisson(
                lambda_total,
                float(ligne),
            )

            candidats_ou = []

            if cote_over and cote_over > 0:
                candidats_ou.append(
                    eval_candidat_simple(
                        "Over " + str(ligne),
                        ou_calc["p_over"],
                        cote_over,
                        "Over/Under",
                    )
                )

            if cote_under and cote_under > 0:
                candidats_ou.append(
                    eval_candidat_simple(
                        "Under " + str(ligne),
                        ou_calc["p_under"],
                        cote_under,
                        "Over/Under",
                    )
                )

            ou_resultats.append({
                "ligne": ligne,
                "p_over": round(
                    ou_calc["p_over"],
                    4,
                ),
                "p_under": round(
                    ou_calc["p_under"],
                    4,
                ),
                "candidats": [
                    c
                    for c in candidats_ou
                    if c is not None
                ],
            })

    # ============================================================
    # 3B — MI-TEMPS / 2e MI-TEMPS / SÉLECTION FINALE / OUTPUT
    # ============================================================

    # ------------------------------------------------------------
    # Ratio HT / 2e période
    # ------------------------------------------------------------
    ratio_ht = compute_ratio_ht(
        lambda_home,
        lambda_away,
    )

    lambda_total = lambda_home + lambda_away

    lambda_ht = max(
        0.05,
        lambda_total * ratio_ht,
    )

    lambda_2h = max(
        0.05,
        lambda_total - lambda_ht,
    )

    # ------------------------------------------------------------
    # Matrices HT et 2H
    # ------------------------------------------------------------
    matrice_ht = compute_score_matrix(
        lambda_ht * (
            lambda_home / max(lambda_total, 1e-9)
        ),
        lambda_ht * (
            lambda_away / max(lambda_total, 1e-9)
        ),
    )

    matrice_2h = compute_score_matrix(
        lambda_2h * (
            lambda_home / max(lambda_total, 1e-9)
        ),
        lambda_2h * (
            lambda_away / max(lambda_total, 1e-9)
        ),
    )

    p1_ht, px_ht, p2_ht = compute_1x2(matrice_ht)
    p1_2h, px_2h, p2_2h = compute_1x2(matrice_2h)

    # ------------------------------------------------------------
    # Marchés mi-temps / 2e mi-temps
    #
    # main.py V23 attend notamment :
    #   p1_ht / px_ht / p2_ht
    #   p1_2h / px_2h / p2_2h
    #   ht
    #   2h
    #
    # Aucune cote HT/2H n'est actuellement transmise par main.py
    # dans l'appel football. On conserve donc les probabilités
    # calculées sans inventer de prix.
    # ------------------------------------------------------------
    marches_2mt = {
        "p1_ht": round(p1_ht, 4),
        "px_ht": round(px_ht, 4),
        "p2_ht": round(p2_ht, 4),

        "p1_2h": round(p1_2h, 4),
        "px_2h": round(px_2h, 4),
        "p2_2h": round(p2_2h, 4),

        "lambda_ht": round(lambda_ht, 4),
        "lambda_2h": round(lambda_2h, 4),

        "ht": [],
        "2h": [],
    }

    # ------------------------------------------------------------
    # OU sécurité
    # ------------------------------------------------------------
    ou_securite = None

    if ou_resultats:
        tous_ou = []

        for bloc_ou in ou_resultats:
            for candidat in bloc_ou.get("candidats", []):
                if candidat is None:
                    continue

                candidat = dict(candidat)

                if "fiabilite" not in candidat:
                    candidat["fiabilite"] = compute_reliability(
                        candidat.get("probabilite", 0.0),
                        candidat.get("cote", 0.0),
                    )

                tous_ou.append(candidat)

        if tous_ou:
            ou_securite = max(
                tous_ou,
                key=lambda x: (
                    x.get("fiabilite", 0.0),
                    x.get("ev", 0.0),
                    x.get("probabilite", 0.0),
                ),
            )

    # ------------------------------------------------------------
    # Agrégation de TOUS les candidats
    # ------------------------------------------------------------
    tous_candidats = []

    tous_candidats.extend(candidats)

    for bloc_hcp in handicap_resultats:
        for candidat in bloc_hcp.get("candidats", []):
            if candidat is not None:
                tous_candidats.append(candidat)

    for bloc_ou in ou_resultats:
        for candidat in bloc_ou.get("candidats", []):
            if candidat is not None:
                tous_candidats.append(candidat)

    if ou_securite is not None:
        # Évite une duplication inutile
        identite_ou = (
            ou_securite.get("marche"),
            ou_securite.get("ligne"),
            ou_securite.get("direction"),
        )

        deja_present = any(
            (
                c.get("marche"),
                c.get("ligne"),
                c.get("direction"),
            ) == identite_ou
            for c in tous_candidats
        )

        if not deja_present:
            tous_candidats.append(ou_securite)

    # ------------------------------------------------------------
    # Nettoyage / sécurité des candidats
    # ------------------------------------------------------------
    candidats_valides = []

    for candidat in tous_candidats:
        if not isinstance(candidat, dict):
            continue

        candidat = dict(candidat)

        probabilite = float(
            candidat.get(
                "probabilite",
                candidat.get("proba", 0.0),
            ) or 0.0
        )

        cote = float(
            candidat.get("cote", 0.0) or 0.0
        )

        ev = float(
            candidat.get("ev", 0.0) or 0.0
        )

        fiabilite = float(
            candidat.get("fiabilite", 0.0) or 0.0
        )

        candidat["probabilite"] = probabilite
        candidat["cote"] = cote
        candidat["ev"] = ev
        candidat["fiabilite"] = fiabilite

        # Alias utile pour les anciennes parties de l'application
        candidat["proba"] = probabilite

        candidats_valides.append(candidat)

    # ------------------------------------------------------------
    # Tri QFTE
    # ------------------------------------------------------------
    candidats_valides.sort(
        key=lambda x: (
            x.get("decision", "") == "VALUE",
            x.get("ev", 0.0),
            x.get("fiabilite", 0.0),
            x.get("probabilite", 0.0),
        ),
        reverse=True,
    )

    # ------------------------------------------------------------
    # Meilleur candidat
    # ------------------------------------------------------------
    meilleur = _selectionner_meilleur_candidat(
        candidats_valides
    )

    if meilleur is None and candidats_valides:
        meilleur = candidats_valides[0]

    # ------------------------------------------------------------
    # Décision finale
    # ------------------------------------------------------------
    if meilleur is not None:
        pari_retenu = dict(meilleur)
    else:
        pari_retenu = {
            "marche": "NO BET",
            "selection": "Aucune sélection",
            "probabilite": 0.0,
            "proba": 0.0,
            "cote": 0.0,
            "ev": 0.0,
            "fiabilite": 0.0,
            "stake": 0.0,
            "decision": "NO BET",
        }

    # ------------------------------------------------------------
    # Divergences / diagnostic
    # ------------------------------------------------------------
    try:
        divergences = detecter_divergences(
            p1,
            px,
            p2,
            probabilites_marche,
        )
    except Exception:
        divergences = []

    # ------------------------------------------------------------
    # Diagnostic final
    # ------------------------------------------------------------
    diagnostic = {
        "lambda_home": round(lambda_home, 4),
        "lambda_away": round(lambda_away, 4),
        "lambda_total": round(lambda_total, 4),

        "lambda_ht": round(lambda_ht, 4),
        "lambda_2h": round(lambda_2h, 4),

        "p1": round(p1, 4),
        "px": round(px, 4),
        "p2": round(p2, 4),

        "p1_ht": round(p1_ht, 4),
        "px_ht": round(px_ht, 4),
        "p2_ht": round(p2_ht, 4),

        "p1_2h": round(p1_2h, 4),
        "px_2h": round(px_2h, 4),
        "p2_2h": round(p2_2h, 4),

        "ratio_ht": round(ratio_ht, 4),

        "nombre_candidats": len(candidats_valides),

        "divergences": divergences,

        "meteo": meteo,
        "enjeu": enjeu,
        "ligue": ligue,

        "position_dom": pos_dom,
        "position_ext": pos_ext,
    }

    # ------------------------------------------------------------
    # Signature / forensics / stacking / cross-market
    # ------------------------------------------------------------
    # Les variables ont été calculées plus haut dans 3A.
    # On sécurise ici leur présence afin que bloc_visuel()
    # ne provoque jamais de KeyError.
    if not isinstance(signature_foot, dict):
        signature_foot = {}

    if not isinstance(market_forensics, dict):
        market_forensics = {}

    if not isinstance(meta_ensemble, dict):
        meta_ensemble = {}

    if not isinstance(cross_market, dict):
        cross_market = {}

    if not isinstance(regime, dict):
        regime = {}

    if not isinstance(time_decay, dict):
        time_decay = {}

    # ------------------------------------------------------------
    # Construction du résultat principal
    # ------------------------------------------------------------
    resultat = {
        # ========================================================
        # Compatibilité historique / main.py V23
        # ========================================================
        "pari_retenu": pari_retenu,

        "lambda_home": round(lambda_home, 4),
        "lambda_away": round(lambda_away, 4),

        "p1": round(p1, 4),
        "px": round(px, 4),
        "p2": round(p2, 4),

        "candidats": candidats_valides,

        "handicap_resultats": handicap_resultats,

        "ou_resultats": ou_resultats,

        "marches_2mt": marches_2mt,

        "ou_securite": ou_securite,

        # ========================================================
        # Structure moderne QFTE
        # ========================================================
        "probabilites_1x2": {
            "1": round(p1, 4),
            "X": round(px, 4),
            "2": round(p2, 4),
        },

        "marches": {
            "1x2": {
                "p1": round(p1, 4),
                "px": round(px, 4),
                "p2": round(p2, 4),
            },
            "handicap": handicap_resultats,
            "ou": ou_resultats,
            "mi_temps": marches_2mt,
        },

        "meilleurs_candidats": candidats_valides[:10],

        # ========================================================
        # Modules V23
        # ========================================================
        "signature_foot": signature_foot,
        "market_forensics": market_forensics,
        "meta_ensemble": meta_ensemble,
        "cross_market": cross_market,
        "regime": regime,
        "time_decay": time_decay,

        "diagnostic": diagnostic,

        # ========================================================
        # Alias utilisés par bloc_visuel()
        # ========================================================
        "forensics": market_forensics,
        "stacking": meta_ensemble,
        "signature": signature_foot,

        # ========================================================
        # Données marché
        # ========================================================
        "cotes": cotes_marche,
        "probabilites_marche": probabilites_marche,

        # ========================================================
        # Données contexte
        # ========================================================
        "contexte": {
            "meteo": meteo,
            "enjeu": enjeu,
            "ligue": ligue,
            "position_dom": pos_dom,
            "position_ext": pos_ext,
            "total_equipes": total_equipes,
        },

        # ========================================================
        # Données modèle
        # ========================================================
        "matrice_score": matrice,
        "matrice_ht": matrice_ht,
        "matrice_2h": matrice_2h,

        "lambda": {
            "home": round(lambda_home, 4),
            "away": round(lambda_away, 4),
            "total": round(lambda_total, 4),
            "ht": round(lambda_ht, 4),
            "2h": round(lambda_2h, 4),
        },

        # ========================================================
        # Audit
        # ========================================================
        "divergences": divergences,

        "meta": {
            "version": "QFTE V23.0",
            "sport": "football",
            "interface": "main.py V23.0",
        },
    }

    # ------------------------------------------------------------
    # Dernière sécurisation : aucun candidat None dans les listes
    # ------------------------------------------------------------
    resultat["candidats"] = [
        c for c in resultat["candidats"]
        if isinstance(c, dict)
    ]

    resultat["meilleurs_candidats"] = [
        c
        for c in resultat["meilleurs_candidats"]
        if isinstance(c, dict)
    ]

    # ------------------------------------------------------------
    # Retour
    # ------------------------------------------------------------
    return resultat
