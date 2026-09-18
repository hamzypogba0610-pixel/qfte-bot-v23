"""
qfte_engine/mvp.py
==================

QFTE V23.0 — Moteur principal

Interface compatible avec main.py V23.0.
"""

import math

try:
    from qfte_engine.signature_foot import (
        analyser_signature_foot,
        calculer_over_under_avec_ic,
    )
except Exception:
    analyser_signature_foot = None
    calculer_over_under_avec_ic = None

try:
    from qfte_engine.forensics import (
        analyser_market_forensics,
        ajuster_fiabilite,
    )
except Exception:
    analyser_market_forensics = None
    ajuster_fiabilite = None

try:
    from qfte_engine.stacking import (
        analyser_meta_ensemble,
        ajuster_fiabilite_pcs,
    )
except Exception:
    analyser_meta_ensemble = None
    ajuster_fiabilite_pcs = None

try:
    from qfte_engine.cross_market import (
        analyser_cross_market,
        ajuster_fiabilite_consistency,
    )
except Exception:
    analyser_cross_market = None
    ajuster_fiabilite_consistency = None

try:
    from qfte_engine.regime import analyser_regime
except Exception:
    analyser_regime = None

try:
    from qfte_engine.time_decay import (
        extraire_moyennes_ponderees,
        fusion_ponderee,
    )
except Exception:
    extraire_moyennes_ponderees = None
    fusion_ponderee = None


SEUIL_FIABILITE = 0.75
SEUIL_VALUE_1X2 = 0.05
SEUIL_CONFIANCE = 0.70
EPS = 1e-9


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        if isinstance(value, bool):
            return float(value)

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except Exception:
        return default


def _clamp(
    value,
    minimum=0.0,
    maximum=1.0,
):
    return max(
        minimum,
        min(
            maximum,
            _safe_float(value),
        ),
    )


def _safe_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [value]


def moy(
    values,
    default=0.0,
):
    vals = []

    for value in _safe_list(values):
        try:
            v = float(value)

            if math.isfinite(v):
                vals.append(v)

        except Exception:
            continue

    if not vals:
        return default

    return sum(vals) / len(vals)


def poisson_pmf(
    k,
    lam,
):
    k = int(
        max(
            0,
            k,
        )
    )

    lam = max(
        0.0,
        _safe_float(lam),
    )

    if lam == 0:
        return (
            1.0
            if k == 0
            else 0.0
        )

    try:
        return math.exp(
            -lam
            + k * math.log(lam)
            - math.lgamma(k + 1)
        )

    except Exception:
        return 0.0


def compute_score_matrix(
    lambda_home,
    lambda_away,
    max_goals=8,
):
    lambda_home = max(
        0.0,
        _safe_float(lambda_home),
    )

    lambda_away = max(
        0.0,
        _safe_float(lambda_away),
    )

    max_goals = max(
        3,
        int(max_goals),
    )

    home_probs = [
        poisson_pmf(
            i,
            lambda_home,
        )
        for i in range(
            max_goals + 1
        )
    ]

    away_probs = [
        poisson_pmf(
            j,
            lambda_away,
        )
        for j in range(
            max_goals + 1
        )
    ]

    matrix = []

    for i in range(
        max_goals + 1
    ):
        row = []

        for j in range(
            max_goals + 1
        ):
            row.append(
                home_probs[i]
                * away_probs[j]
            )

        matrix.append(row)

    total = sum(
        sum(row)
        for row in matrix
    )

    if total > EPS:
        matrix = [
            [
                value / total
                for value in row
            ]
            for row in matrix
        ]

    return matrix


def compute_1x2(matrix):
    p1 = 0.0
    px = 0.0
    p2 = 0.0

    if not matrix:
        return (
            0.0,
            0.0,
            0.0,
        )

    for i, row in enumerate(matrix):

        for j, probability in enumerate(row):

            probability = _safe_float(
                probability
            )

            if i > j:
                p1 += probability

            elif i == j:
                px += probability

            else:
                p2 += probability

    total = (
        p1
        + px
        + p2
    )

    if total > EPS:
        p1 /= total
        px /= total
        p2 /= total

    return (
        p1,
        px,
        p2,
    )


def compute_ratio_ht(x):
    x = max(
        0.0,
        _safe_float(x),
    )

    if x <= 1.0:
        ratio = 0.45

    elif x <= 2.0:
        ratio = 0.46

    elif x <= 3.0:
        ratio = 0.47

    elif x <= 4.0:
        ratio = 0.48

    else:
        ratio = 0.49

    return _clamp(
        ratio,
        0.35,
        0.60,
    )


def demargeage_proportionnel(
    cote_1,
    cote_x,
    cote_2,
):
    odds = [
        _safe_float(cote_1),
        _safe_float(cote_x),
        _safe_float(cote_2),
    ]

    implied = []

    for odd in odds:

        if odd > 1.0:
            implied.append(
                1.0 / odd
            )

        else:
            implied.append(0.0)

    total = sum(implied)

    if total <= EPS:
        return {
            "1": 0.0,
            "X": 0.0,
            "2": 0.0,
            "marge": 0.0,
        }

    return {
        "1": implied[0] / total,
        "X": implied[1] / total,
        "2": implied[2] / total,
        "marge": max(
            0.0,
            total - 1.0,
        ),
    }


def proba_handicap_dom(
    matrix,
    handicap=0.0,
):
    handicap = _safe_float(
        handicap
    )

    win = 0.0
    push = 0.0

    for i, row in enumerate(matrix):

        for j, probability in enumerate(row):

            diff = (
                i
                - j
                + handicap
            )

            probability = _safe_float(
                probability
            )

            if diff > EPS:
                win += probability

            elif abs(diff) <= EPS:
                push += probability

    return {
        "win": win,
        "push": push,
        "lose": max(
            0.0,
            1.0 - win - push,
        ),
    }


def proba_handicap_ext(
    matrix,
    handicap=0.0,
):
    handicap = _safe_float(
        handicap
    )

    win = 0.0
    push = 0.0

    for i, row in enumerate(matrix):

        for j, probability in enumerate(row):

            diff = (
                j
                - i
                + handicap
            )

            probability = _safe_float(
                probability
            )

            if diff > EPS:
                win += probability

            elif abs(diff) <= EPS:
                push += probability

    return {
        "win": win,
        "push": push,
        "lose": max(
            0.0,
            1.0 - win - push,
        ),
    }


def facteur_meteo(meteo):
    if isinstance(
        meteo,
        (int, float),
    ):
        return _clamp(
            float(meteo),
            0.85,
            1.10,
        )

    texte = str(
        meteo or "normale"
    ).lower()

    if any(
        mot in texte
        for mot in (
            "orage",
            "tempête",
            "forte pluie",
            "neige",
        )
    ):
        return 0.90

    if any(
        mot in texte
        for mot in (
            "pluie",
            "vent",
            "mauvaise",
        )
    ):
        return 0.96

    if any(
        mot in texte
        for mot in (
            "bonne",
            "favorable",
            "normale",
            "normal",
        )
    ):
        return 1.00

    return 1.00


def facteur_enjeu(enjeu):
    if isinstance(
        enjeu,
        (int, float),
    ):
        return _clamp(
            float(enjeu),
            0.90,
            1.10,
        )

    texte = str(
        enjeu or "normal"
    ).lower()

    if any(
        mot in texte
        for mot in (
            "décisif",
            "finale",
            "qualification",
            "maintien",
        )
    ):
        return 0.98

    if any(
        mot in texte
        for mot in (
            "faible",
            "amical",
        )
    ):
        return 1.02

    return 1.00


def facteur_blessures(value):
    if isinstance(
        value,
        bool,
    ):
        return (
            0.96
            if value
            else 1.00
        )

    value = _safe_float(
        value,
        default=0.0,
    )

    if value <= 0:
        return 1.00

    return _clamp(
        1.0 - 0.015 * value,
        0.80,
        1.00,
    )


def facteur_fatigue(value):
    if isinstance(
        value,
        bool,
    ):
        return (
            0.96
            if value
            else 1.00
        )

    value = _safe_float(
        value,
        default=0.0,
    )

    if value <= 0:
        return 1.00

    return _clamp(
        1.0 - 0.012 * value,
        0.80,
        1.00,
    )


def facteur_classement(
    pos_dom=None,
    pos_ext=None,
    total_equipes=None,
):
    if (
        pos_dom is None
        or pos_ext is None
    ):
        return 1.00

    pos_dom = _safe_float(
        pos_dom
    )

    pos_ext = _safe_float(
        pos_ext
    )

    if (
        pos_dom <= 0
        or pos_ext <= 0
    ):
        return 1.00

    difference = (
        pos_ext
        - pos_dom
    )

    adjustment = (
        1.0
        + 0.008 * difference
    )

    return _clamp(
        adjustment,
        0.90,
        1.10,
    )


def facteur_ht(ratio_ht):
    return _clamp(
        ratio_ht,
        0.35,
        0.60,
    )


def facteur_forme_recente(
    matchs,
    domicile=True,
):
    matchs = _safe_list(
        matchs
    )

    if not matchs:
        return 1.00

    scores = []

    for match in matchs:

        if isinstance(
            match,
            dict,
        ):

            gf = (
                match.get("gf")
                if match.get("gf")
                is not None
                else match.get(
                    "goals_for"
                )
            )

            ga = (
                match.get("ga")
                if match.get("ga")
                is not None
                else match.get(
                    "goals_against"
                )
            )

            if (
                gf is not None
                and ga is not None
            ):
                scores.append(
                    _safe_float(gf)
                    - _safe_float(ga)
                )

        elif isinstance(
            match,
            (list, tuple),
        ):

            if len(match) >= 2:
                scores.append(
                    _safe_float(
                        match[0]
                    )
                    - _safe_float(
                        match[1]
                    )
                )

    if not scores:
        return 1.00

    diff = moy(
        scores
    )

    adjustment = (
        1.0
        + 0.025 * diff
    )

    return _clamp(
        adjustment,
        0.90,
        1.10,
    )

def facteur_h2h(h2h):
    matchs = _safe_list(
        h2h
    )

    if not matchs:
        return 1.00

    differentiels = []

    for match in matchs:

        if isinstance(
            match,
            dict,
        ):

            gf = match.get(
                "gf"
            )

            ga = match.get(
                "ga"
            )

            if (
                gf is not None
                and ga is not None
            ):
                differentiels.append(
                    _safe_float(gf)
                    - _safe_float(ga)
                )

        elif isinstance(
            match,
            (list, tuple),
        ):

            if len(match) >= 2:
                differentiels.append(
                    _safe_float(
                        match[0]
                    )
                    - _safe_float(
                        match[1]
                    )
                )

    if not differentiels:
        return 1.00

    return _clamp(
        1.0
        + 0.01 * moy(
            differentiels
        ),
        0.94,
        1.06,
    )


def compute_ev(
    probabilite,
    cote,
):
    p = _clamp(
        probabilite
    )

    cote = _safe_float(
        cote
    )

    if cote <= 1.0:
        return 0.0

    return (
        p * cote
    ) - 1.0


def compute_reliability(
    probabilite,
    cote=0.0,
):
    p = _clamp(
        probabilite
    )

    cote = _safe_float(
        cote
    )

    if cote > 1.0:

        implied = 1.0 / cote

        coherence = (
            1.0
            - abs(
                p - implied
            )
        )

    else:
        coherence = 0.50

    reliability = (
        0.70 * p
        + 0.30 * coherence
    )

    return _clamp(
        reliability
    )


def compute_stake(
    ev,
    fiabilite,
    confiance=1.0,
):
    ev = max(
        0.0,
        _safe_float(ev),
    )

    fiabilite = _clamp(
        fiabilite
    )

    confiance = _clamp(
        confiance
    )

    base = (
        ev * 100.0
    )

    stake = (
        base
        * fiabilite
        * confiance
    )

    return round(
        _clamp(
            stake,
            0.0,
            5.0,
        ),
        2,
    )


def appliquer_filtres_discipline(
    candidat,
):
    if not isinstance(
        candidat,
        dict,
    ):
        return None

    candidat = dict(
        candidat
    )

    probabilite = _clamp(
        candidat.get(
            "probabilite",
            candidat.get(
                "proba",
                0.0,
            ),
        )
    )

    cote = _safe_float(
        candidat.get(
            "cote",
            0.0,
        )
    )

    ev = compute_ev(
        probabilite,
        cote,
    )

    fiabilite = _clamp(
        candidat.get(
            "fiabilite",
            compute_reliability(
                probabilite,
                cote,
            ),
        )
    )

    candidat["probabilite"] = (
        probabilite
    )

    candidat["proba"] = (
        probabilite
    )

    candidat["p"] = (
        probabilite
    )

    candidat["cote"] = (
        cote
    )

    candidat["ev"] = (
        ev
    )

    candidat["fiabilite"] = (
        fiabilite
    )

    candidat["stake"] = compute_stake(
        ev,
        fiabilite,
    )

    candidat["decision"] = (
        classify_decision(
            ev,
            fiabilite,
            probabilite,
        )
    )

    return candidat


def classify_decision(
    ev,
    fiabilite,
    probabilite,
):
    ev = _safe_float(
        ev
    )

    fiabilite = _clamp(
        fiabilite
    )

    probabilite = _clamp(
        probabilite
    )

    if (
        ev >= SEUIL_VALUE_1X2
        and fiabilite
        >= SEUIL_FIABILITE
        and probabilite
        >= SEUIL_CONFIANCE
    ):
        return "VALUE"

    if (
        ev >= 0.0
        and fiabilite >= 0.60
    ):
        return "WATCH"

    return "NO BET"


def eval_candidat_simple(
    marche,
    selection,
    probabilite,
    cote=None,
    ligne=None,
    direction=None,
):
    probabilite = _clamp(
        probabilite
    )

    cote = _safe_float(
        cote
    )

    ev = compute_ev(
        probabilite,
        cote,
    )

    fiabilite = compute_reliability(
        probabilite,
        cote,
    )

    decision = classify_decision(
        ev,
        fiabilite,
        probabilite,
    )

    stake = compute_stake(
        ev,
        fiabilite,
    )

    return {
        "marche": marche,
        "selection": selection,
        "direction": direction,
        "ligne": ligne,
        "probabilite": round(
            probabilite,
            4,
        ),
        "proba": round(
            probabilite,
            4,
        ),
        "p": round(
            probabilite,
            4,
        ),
        "cote": round(
            cote,
            4,
        ),
        "ev": round(
            ev,
            4,
        ),
        "fiabilite": round(
            fiabilite,
            4,
        ),
        "stake": stake,
        "decision": decision,
    }


# ============================================================
# BLOC 2A/2B
# AJUSTEMENTS QFTE — HANDICAP — OVER/UNDER
# ============================================================


# ============================================================
# AJUSTEMENTS FORENSICS
# ============================================================

def appliquer_forensics_au_candidat(
    candidat,
    forensics=None,
):
    """
    Applique l'analyse Market Forensics au candidat.
    """

    if not isinstance(candidat, dict):
        return None

    resultat = dict(candidat)

    if not forensics:
        return resultat

    try:
        if ajuster_fiabilite is not None:

            valeur = ajuster_fiabilite(
                resultat,
                forensics,
            )

            if isinstance(valeur, dict):
                resultat.update(valeur)

            elif isinstance(valeur, (int, float)):
                resultat["fiabilite"] = _clamp(
                    valeur
                )

    except Exception:
        pass

    return resultat


# ============================================================
# AJUSTEMENTS STACKING
# ============================================================

def appliquer_stacking_au_candidat(
    candidat,
    stacking=None,
):
    """
    Applique le méta-ensemble / stacking QFTE.
    """

    if not isinstance(candidat, dict):
        return None

    resultat = dict(candidat)

    if not stacking:
        return resultat

    try:
        if ajuster_fiabilite_pcs is not None:

            valeur = ajuster_fiabilite_pcs(
                resultat,
                stacking,
            )

            if isinstance(valeur, dict):
                resultat.update(valeur)

            elif isinstance(valeur, (int, float)):
                resultat["fiabilite"] = _clamp(
                    valeur
                )

    except Exception:
        pass

    return resultat


# ============================================================
# AJUSTEMENTS CROSS-MARKET
# ============================================================

def appliquer_consistency_au_candidat(
    candidat,
    cross_market=None,
):
    """
    Applique le contrôle de cohérence cross-market.
    """

    if not isinstance(candidat, dict):
        return None

    resultat = dict(candidat)

    if not cross_market:
        return resultat

    try:
        if ajuster_fiabilite_consistency is not None:

            valeur = ajuster_fiabilite_consistency(
                resultat,
                cross_market,
            )

            if isinstance(valeur, dict):
                resultat.update(valeur)

            elif isinstance(valeur, (int, float)):
                resultat["fiabilite"] = _clamp(
                    valeur
                )

    except Exception:
        pass

    return resultat


# ============================================================
# HANDICAP — DOMICILE
# ============================================================

def calcul_handicap_complet(
    matrice,
    hcp_dom,
    hcp_ext=None,
    cote_dom=None,
    cote_ext=None,
):
    """
    Calcul du handicap domicile / extérieur.

    La matrice de scores reste la base probabiliste.
    """

    hcp_dom = _safe_float(
        hcp_dom
    )

    resultat_dom = proba_handicap_dom(
        matrice,
        hcp_dom,
    )

    candidats = []

    # --------------------------------------------------------
    # Candidat domicile
    # --------------------------------------------------------

    if cote_dom is not None:

        candidat_dom = eval_candidat_simple(
            marche="Handicap",
            selection="Domicile",
            probabilite=resultat_dom["win"],
            cote=cote_dom,
            ligne=hcp_dom,
            direction="home",
        )

        candidats.append(
            candidat_dom
        )

    # --------------------------------------------------------
    # Candidat extérieur
    # --------------------------------------------------------

    if hcp_ext is not None:

        hcp_ext = _safe_float(
            hcp_ext
        )

        resultat_ext = proba_handicap_ext(
            matrice,
            hcp_ext,
        )

        if cote_ext is not None:

            candidat_ext = eval_candidat_simple(
                marche="Handicap",
                selection="Extérieur",
                probabilite=resultat_ext["win"],
                cote=cote_ext,
                ligne=hcp_ext,
                direction="away",
            )

            candidats.append(
                candidat_ext
            )

    else:

        resultat_ext = {
            "win": 0.0,
            "push": 0.0,
            "lose": 0.0,
        }

    return {
        "ligne_dom": hcp_dom,
        "ligne_ext": hcp_ext,
        "domicile": resultat_dom,
        "exterieur": resultat_ext,
        "candidats": candidats,
    }


# ============================================================
# DISTRIBUTION DU TOTAL DE BUTS
# ============================================================

def _probs_total_goals(
    lambda_total,
    max_goals=15,
):
    """
    Distribution Poisson du nombre total de buts.
    """

    lambda_total = max(
        0.0,
        _safe_float(lambda_total),
    )

    max_goals = max(
        5,
        int(max_goals),
    )

    probs = [
        poisson_pmf(
            k,
            lambda_total,
        )
        for k in range(
            max_goals + 1
        )
    ]

    total = sum(probs)

    if total > EPS:

        probs = [
            p / total
            for p in probs
        ]

    return probs


# ============================================================
# OVER / UNDER — POISSON
# ============================================================

def calcul_ou_poisson(
    lambda_total,
    ligne,
):
    """
    Calcul Over / Under.

    Ligne entière :
        Under = total < ligne
        Push  = total = ligne
        Over  = total > ligne

    Ligne .5 :
        aucun push.
    """

    lambda_total = max(
        0.0,
        _safe_float(lambda_total),
    )

    ligne = _safe_float(
        ligne
    )

    probs = _probs_total_goals(
        lambda_total
    )

    # --------------------------------------------------------
    # Ligne entière
    # --------------------------------------------------------

    if abs(
        ligne - round(ligne)
    ) < 1e-9:

        seuil = int(
            round(ligne)
        )

        p_under = sum(
            probs[:seuil]
        )

        if (
            0 <= seuil
            < len(probs)
        ):
            p_push = probs[seuil]
        else:
            p_push = 0.0

        p_over = max(
            0.0,
            1.0
            - p_under
            - p_push,
        )

    # --------------------------------------------------------
    # Ligne décimale
    # --------------------------------------------------------

    else:

        seuil = math.floor(
            ligne
        )

        p_under = sum(
            probs[:seuil + 1]
        )

        p_push = 0.0

        p_over = max(
            0.0,
            1.0 - p_under,
        )

    return {
        "ligne": ligne,

        "p_over": _clamp(
            p_over
        ),

        "p_under": _clamp(
            p_under
        ),

        "p_push": _clamp(
            p_push
        ),

        "distribution": probs,
        }

def calcul_ou_complet_from_signature(
    home,
    away,
    ligne,
    lambda_total,
):
    """
    Calcule l'Over/Under via signature_foot lorsque
    disponible, avec fallback Poisson.
    """

    if calculer_over_under_avec_ic is not None:

        try:

            resultat = calculer_over_under_avec_ic(
                home,
                away,
                ligne,
            )

            if isinstance(
                resultat,
                dict,
            ):

                p_over = _safe_float(
                    resultat.get(
                        "p_over",
                        resultat.get(
                            "over",
                            0.0,
                        ),
                    )
                )

                p_under = _safe_float(
                    resultat.get(
                        "p_under",
                        resultat.get(
                            "under",
                            0.0,
                        ),
                    )
                )

                total = (
                    p_over
                    + p_under
                )

                if total > EPS:

                    p_over /= total
                    p_under /= total

                    return {
                        "ligne": ligne,
                        "p_over": _clamp(
                            p_over
                        ),
                        "p_under": _clamp(
                            p_under
                        ),
                        "p_push": 0.0,
                        "source": "signature_foot",
                    }

        except Exception:
            pass

    # --------------------------------------------------------
    # Fallback Poisson
    # --------------------------------------------------------

    resultat = calcul_ou_poisson(
        lambda_total,
        ligne,
    )

    resultat["source"] = "poisson"

    return resultat


# ============================================================
# CANDIDAT 1X2
# ============================================================

def _construire_candidat_1x2(
    selection,
    probabilite,
    cote,
):
    """
    Construit un candidat 1X2 standardisé.
    """

    return eval_candidat_simple(
        marche="1X2",
        selection=selection,
        probabilite=probabilite,
        cote=cote,
    )


# ============================================================
# MARCHÉS MI-TEMPS / 2e MI-TEMPS
# ============================================================

def calcul_marches_2mt(
    p1_ht,
    px_ht,
    p2_ht,
    p1_2h,
    px_2h,
    p2_2h,
    cotes_ht=None,
    cotes_2h=None,
):
    """
    Construit la structure des marchés HT / 2H.

    main.py V23.0 attend notamment :
        p1_ht
        px_ht
        p2_ht
        p1_2h
        px_2h
        p2_2h
        ht
        2h
    """

    cotes_ht = (
        cotes_ht
        if isinstance(
            cotes_ht,
            dict,
        )
        else {}
    )

    cotes_2h = (
        cotes_2h
        if isinstance(
            cotes_2h,
            dict,
        )
        else {}
    )

    candidats_ht = []
    candidats_2h = []

    # --------------------------------------------------------
    # Première mi-temps
    # --------------------------------------------------------

    if cotes_ht:

        if cotes_ht.get("1") is not None:

            candidats_ht.append(
                _construire_candidat_1x2(
                    "1 HT",
                    p1_ht,
                    cotes_ht.get("1"),
                )
            )

        if cotes_ht.get("X") is not None:

            candidats_ht.append(
                _construire_candidat_1x2(
                    "X HT",
                    px_ht,
                    cotes_ht.get("X"),
                )
            )

        if cotes_ht.get("2") is not None:

            candidats_ht.append(
                _construire_candidat_1x2(
                    "2 HT",
                    p2_ht,
                    cotes_ht.get("2"),
                )
            )

    # --------------------------------------------------------
    # Deuxième mi-temps
    # --------------------------------------------------------

    if cotes_2h:

        if cotes_2h.get("1") is not None:

            candidats_2h.append(
                _construire_candidat_1x2(
                    "1 2H",
                    p1_2h,
                    cotes_2h.get("1"),
                )
            )

        if cotes_2h.get("X") is not None:

            candidats_2h.append(
                _construire_candidat_1x2(
                    "X 2H",
                    px_2h,
                    cotes_2h.get("X"),
                )
            )

        if cotes_2h.get("2") is not None:

            candidats_2h.append(
                _construire_candidat_1x2(
                    "2 2H",
                    p2_2h,
                    cotes_2h.get("2"),
                )
            )

    return {
        "p1_ht": round(
            _safe_float(p1_ht),
            4,
        ),

        "px_ht": round(
            _safe_float(px_ht),
            4,
        ),

        "p2_ht": round(
            _safe_float(p2_ht),
            4,
        ),

        "p1_2h": round(
            _safe_float(p1_2h),
            4,
        ),

        "px_2h": round(
            _safe_float(px_2h),
            4,
        ),

        "p2_2h": round(
            _safe_float(p2_2h),
            4,
        ),

        "ht": candidats_ht,
        "2h": candidats_2h,
    }


# ============================================================
# DIVERGENCES MODÈLE / MARCHÉ
# ============================================================

def detecter_divergences(
    p1,
    px,
    p2,
    probabilites_marche=None,
):
    """
    Détecte les écarts importants entre modèle et marché.
    """

    divergences = []

    if not isinstance(
        probabilites_marche,
        dict,
    ):
        return divergences

    modele = {
        "1": _safe_float(p1),
        "X": _safe_float(px),
        "2": _safe_float(p2),
    }

    for selection in (
        "1",
        "X",
        "2",
    ):

        marche = _safe_float(
            probabilites_marche.get(
                selection,
                0.0,
            )
        )

        ecart = (
            modele[selection]
            - marche
        )

        if abs(ecart) >= 0.08:

            divergences.append({
                "selection": selection,

                "modele": round(
                    modele[selection],
                    4,
                ),

                "marche": round(
                    marche,
                    4,
                ),

                "ecart": round(
                    ecart,
                    4,
                ),
            })

    return divergences


# ============================================================
# NORMALISATION DES HISTORIQUES
# ============================================================

def _normaliser_matchs(
    matchs,
):
    """
    Normalise les différentes structures historiques.
    """

    if matchs is None:
        return []

    if isinstance(
        matchs,
        list,
    ):
        return matchs

    if isinstance(
        matchs,
        tuple,
    ):
        return list(matchs)

    if isinstance(
        matchs,
        dict,
    ):

        for key in (
            "matchs",
            "matches",
            "results",
            "data",
            "historique",
        ):

            if key in matchs:

                valeur = matchs[key]

                if isinstance(
                    valeur,
                    list,
                ):
                    return valeur

        return [matchs]

    return [matchs]


def _fusionner_historiques(
    contextuel,
    global_,
):
    """
    Fusionne historique contextuel et global.

    Le contexte récent reçoit davantage de poids.
    """

    contextuel = _normaliser_matchs(
        contextuel
    )

    global_ = _normaliser_matchs(
        global_
    )

    return (
        contextuel * 2
        + global_
    )


# ============================================================
# EXTRACTION DES BUTS
# ============================================================

def _extraire_buts(
    matchs,
    domicile=True,
):
    """
    Extrait buts pour / contre depuis plusieurs formats.
    """

    matchs = _normaliser_matchs(
        matchs
    )

    pour = []
    contre = []

    for match in matchs:

        if isinstance(
            match,
            dict,
        ):

            gf = None
            ga = None

            for key in (
                "gf",
                "goals_for",
                "buts_pour",
                "goals_scored",
                "score_for",
            ):

                if key in match:

                    gf = match[key]
                    break

            for key in (
                "ga",
                "goals_against",
                "buts_contre",
                "goals_conceded",
                "score_against",
            ):

                if key in match:

                    ga = match[key]
                    break

            if (
                gf is not None
                and ga is not None
            ):

                pour.append(
                    _safe_float(gf)
                )

                contre.append(
                    _safe_float(ga)
                )

                continue

            score = match.get(
                "score"
            )

            if (
                isinstance(
                    score,
                    str,
                )
                and "-"
                in score
            ):

                try:

                    a, b = score.split(
                        "-",
                        1,
                    )

                    pour.append(
                        _safe_float(a)
                    )

                    contre.append(
                        _safe_float(b)
                    )

                except Exception:
                    pass

        elif isinstance(
            match,
            (list, tuple),
        ):

            if len(match) >= 2:

                pour.append(
                    _safe_float(
                        match[0]
                    )
                )

                contre.append(
                    _safe_float(
                        match[1]
                    )
                )

    return (
        pour,
        contre,
    )


# ============================================================
# ESTIMATION LAMBDA
# ============================================================

def _estimer_lambda_equipe(
    matchs,
    moyenne_def_adverse=None,
    domicile=True,
):
    """
    Estime le potentiel offensif d'une équipe.
    """

    pour, contre = _extraire_buts(
        matchs,
        domicile=domicile,
    )

    attaque = moy(
        pour,
        default=1.20,
    )

    defense = moy(
        contre,
        default=1.20,
    )

    if moyenne_def_adverse is not None:

        defense = _safe_float(
            moyenne_def_adverse,
            default=defense,
        )

    lambda_estime = (
        0.65 * attaque
        + 0.35 * defense
    )

    if domicile:
        lambda_estime *= 1.05

    return max(
        0.15,
        min(
            lambda_estime,
            4.50,
        ),
    )


# ============================================================
# PROBABILITÉS DE MARCHÉ
# ============================================================

def _probas_marche(
    cotes,
):
    """
    Transforme les cotes 1X2 en probabilités
    de marché sans marge.
    """

    if not isinstance(
        cotes,
        dict,
    ):

        return {
            "1": 0.0,
            "X": 0.0,
            "2": 0.0,
            "marge": 0.0,
        }

    return demargeage_proportionnel(
        cotes.get(
            "1",
            0.0,
        ),
        cotes.get(
            "X",
            0.0,
        ),
        cotes.get(
            "2",
            0.0,
        ),
    )


# ============================================================
# CONSTRUCTION DES COTES MARCHÉ
# ============================================================

def _construire_cotes_marche(
    open_1,
    open_x,
    open_2,
    curr_1,
    curr_x,
    curr_2,
):
    """
    Structure normalisée des cotes.
    """

    return {
        "ouverture": {
            "1": _safe_float(
                open_1
            ),
            "X": _safe_float(
                open_x
            ),
            "2": _safe_float(
                open_2
            ),
        },

        "actuelles": {
            "1": _safe_float(
                curr_1
            ),
            "X": _safe_float(
                curr_x
            ),
            "2": _safe_float(
                curr_2
            ),
        },
    }


# ============================================================
# SÉLECTION DU MEILLEUR CANDIDAT
# ============================================================

def _selectionner_meilleur_candidat(
    candidats,
):
    """
    Sélection finale selon :
    - Value éventuelle
    - EV
    - fiabilité
    - probabilité
    """

    candidats = [
        candidat
        for candidat in _safe_list(
            candidats
        )
        if isinstance(
            candidat,
            dict,
        )
    ]

    if not candidats:
        return None

    def score(candidat):

        ev = _safe_float(
            candidat.get(
                "ev",
                0.0,
            )
        )

        fiabilite = _safe_float(
            candidat.get(
                "fiabilite",
                0.0,
            )
        )

        probabilite = _safe_float(
            candidat.get(
                "probabilite",
                candidat.get(
                    "proba",
                    0.0,
                ),
            )
        )

        decision = candidat.get(
            "decision",
            "",
        )

        bonus = (
            0.20
            if decision == "VALUE"
            else 0.0
        )

        return (
            bonus
            + 0.40 * ev
            + 0.35 * fiabilite
            + 0.25 * probabilite
        )

    return max(
        candidats,
        key=score,
    )


# ============================================================
# BLOC 3A/3B
# ANALYSEUR FOOTBALL — ENTRÉE + CALCUL CENTRAL
# ============================================================

def _extraire_ligne_et_cotes(
    structure,
    default_line=None,
):
    resultats = []

    if structure is None:
        return resultats

    if isinstance(structure, dict):

        if (
            "ligne" in structure
            or "line" in structure
        ):
            ligne = structure.get(
                "ligne",
                structure.get("line", default_line),
            )

            over = structure.get(
                "over",
                structure.get(
                    "cote_over",
                    structure.get("odds_over"),
                ),
            )

            under = structure.get(
                "under",
                structure.get(
                    "cote_under",
                    structure.get("odds_under"),
                ),
            )

            if ligne is not None:
                resultats.append({
                    "ligne": _safe_float(ligne),
                    "over": _safe_float(over),
                    "under": _safe_float(under),
                })

            return resultats

        for cle, valeur in structure.items():

            try:
                ligne = float(cle)
            except Exception:
                continue

            if isinstance(valeur, dict):

                over = valeur.get(
                    "over",
                    valeur.get("cote_over"),
                )

                under = valeur.get(
                    "under",
                    valeur.get("cote_under"),
                )

                resultats.append({
                    "ligne": ligne,
                    "over": _safe_float(over),
                    "under": _safe_float(under),
                })

        return resultats

    if isinstance(structure, (list, tuple)):

        for item in structure:

            if isinstance(item, dict):

                ligne = item.get(
                    "ligne",
                    item.get("line", default_line),
                )

                if ligne is None:
                    continue

                resultats.append({
                    "ligne": _safe_float(ligne),
                    "over": _safe_float(
                        item.get(
                            "over",
                            item.get("cote_over", 0.0),
                        )
                    ),
                    "under": _safe_float(
                        item.get(
                            "under",
                            item.get("cote_under", 0.0),
                        )
                    ),
                })

            elif isinstance(item, (list, tuple)):

                if len(item) >= 3:
                    resultats.append({
                        "ligne": _safe_float(item[0]),
                        "over": _safe_float(item[1]),
                        "under": _safe_float(item[2]),
                    })

    return resultats

def _construire_ou_resultats(
    lambda_total,
    ou_lignes,
):
    marches = _extraire_ligne_et_cotes(
        ou_lignes
    )

    if not marches:
        marches = [
            {
                "ligne": 2.5,
                "over": 0.0,
                "under": 0.0,
            }
        ]

    resultats = []

    for marche in marches:

        ligne = marche.get(
            "ligne",
            2.5,
        )

        probabilites = calcul_ou_poisson(
            lambda_total,
            ligne,
        )

        candidats = []

        cote_over = _safe_float(
            marche.get("over", 0.0)
        )

        cote_under = _safe_float(
            marche.get("under", 0.0)
        )

        if cote_over > 1.0:

            candidat_over = eval_candidat_simple(
                marche="Over/Under",
                selection=f"Over {ligne}",
                probabilite=probabilites["p_over"],
                cote=cote_over,
                ligne=ligne,
                direction="over",
            )

            candidats.append(
                candidat_over
            )

        if cote_under > 1.0:

            candidat_under = eval_candidat_simple(
                marche="Over/Under",
                selection=f"Under {ligne}",
                probabilite=probabilites["p_under"],
                cote=cote_under,
                ligne=ligne,
                direction="under",
            )

            candidats.append(
                candidat_under
            )

        resultats.append({
            "ligne": ligne,
            "p_over": probabilites["p_over"],
            "p_under": probabilites["p_under"],
            "p_push": probabilites["p_push"],
            "cote_over": cote_over,
            "cote_under": cote_under,
            "candidats": candidats,
            "distribution": probabilites.get(
                "distribution",
                [],
            ),
        })

    return resultats


def _normaliser_candidats(
    candidats,
    forensics=None,
    stacking=None,
    cross_market=None,
):
    resultats = []

    for candidat in _safe_list(candidats):

        if not isinstance(candidat, dict):
            continue

        candidat = appliquer_filtres_discipline(
            candidat
        )

        if candidat is None:
            continue

        candidat = appliquer_forensics_au_candidat(
            candidat,
            forensics,
        )

        candidat = appliquer_stacking_au_candidat(
            candidat,
            stacking,
        )

        candidat = appliquer_consistency_au_candidat(
            candidat,
            cross_market,
        )

        candidat = appliquer_filtres_discipline(
            candidat
        )

        if candidat is not None:
            resultats.append(candidat)

    return resultats


def _appel_module(
    fonction,
    *args,
    default=None,
    **kwargs,
):
    if fonction is None:
        return default

    try:
        return fonction(
            *args,
            **kwargs,
        )

    except TypeError:

        try:
            return fonction(
                *args,
            )
        except Exception:
            return default

    except Exception:
        return default


def analyser_match_football(
    home_ctx,
    home_glob,
    away_ctx,
    away_glob,
    cote_1,
    cote_x,
    cote_2,
    cote_1_ouverture,
    cote_x_ouverture,
    cote_2_ouverture,
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
    reserve_1=None,
    reserve_2=None,
    ligue=None,
):

    home_ctx = _normaliser_matchs(
        home_ctx
    )

    home_glob = _normaliser_matchs(
        home_glob
    )

    away_ctx = _normaliser_matchs(
        away_ctx
    )

    away_glob = _normaliser_matchs(
        away_glob
    )

    h2h = _normaliser_matchs(
        h2h
    )

    home_matches = _fusionner_historiques(
        home_ctx,
        home_glob,
    )

    away_matches = _fusionner_historiques(
        away_ctx,
        away_glob,
    )

    lambda_home = _estimer_lambda_equipe(
        home_matches,
        domicile=True,
    )

    lambda_away = _estimer_lambda_equipe(
        away_matches,
        domicile=False,
    )

    facteur_home = 1.0
    facteur_away = 1.0

    facteur_home *= facteur_meteo(
        meteo
    )

    facteur_away *= facteur_meteo(
        meteo
    )

    facteur_home *= facteur_enjeu(
        enjeu
    )

    facteur_away *= facteur_enjeu(
        enjeu
    )

    facteur_home *= facteur_blessures(
        blessures_dom
    )

    facteur_away *= facteur_blessures(
        blessures_ext
    )

    facteur_home *= facteur_fatigue(
        fatigue_dom
    )

    facteur_away *= facteur_fatigue(
        fatigue_ext
    )

    facteur_home *= facteur_classement(
        pos_dom,
        pos_ext,
        total_equipes,
    )

    facteur_away *= facteur_classement(
        pos_ext,
        pos_dom,
        total_equipes,
    )

    facteur_home *= facteur_forme_recente(
        home_matches,
        domicile=True,
    )

    facteur_away *= facteur_forme_recente(
        away_matches,
        domicile=False,
    )

    facteur_h2h_value = facteur_h2h(
        h2h
    )

    facteur_home *= facteur_h2h_value

    facteur_away /= max(
        facteur_h2h_value,
        0.90,
    )

    lambda_home *= facteur_home
    lambda_away *= facteur_away

    lambda_home = max(
        0.15,
        min(lambda_home, 4.50),
    )

    lambda_away = max(
        0.15,
        min(lambda_away, 4.50),
    )

    lambda_total = (
        lambda_home
        + lambda_away
    )

    ratio_ht = compute_ratio_ht(
        lambda_total
    )

    lambda_home_ht = (
        lambda_home
        * ratio_ht
    )

    lambda_away_ht = (
        lambda_away
        * ratio_ht
    )

    lambda_home_2h = max(
        0.0,
        lambda_home - lambda_home_ht,
    )

    lambda_away_2h = max(
        0.0,
        lambda_away - lambda_away_ht,
    )

    matrice = compute_score_matrix(
        lambda_home,
        lambda_away,
        max_goals=8,
    )

    p1, px, p2 = compute_1x2(
        matrice
    )

    matrice_ht = compute_score_matrix(
        lambda_home_ht,
        lambda_away_ht,
        max_goals=7,
    )

    p1_ht, px_ht, p2_ht = compute_1x2(
        matrice_ht
    )

    matrice_2h = compute_score_matrix(
        lambda_home_2h,
        lambda_away_2h,
        max_goals=7,
    )

    p1_2h, px_2h, p2_2h = compute_1x2(
        matrice_2h
    )

    cotes_actuelles = {
        "1": _safe_float(cote_1),
        "X": _safe_float(cote_x),
        "2": _safe_float(cote_2),
    }

    cotes_ouverture = {
        "1": _safe_float(cote_1_ouverture),
        "X": _safe_float(cote_x_ouverture),
        "2": _safe_float(cote_2_ouverture),
    }

    marche_actuel = demargeage_proportionnel(
        cote_1,
        cote_x,
        cote_2,
    )

    marche_ouverture = demargeage_proportionnel(
        cote_1_ouverture,
        cote_x_ouverture,
        cote_2_ouverture,
    )

    candidats_1x2 = [
        _construire_candidat_1x2(
            "1",
            p1,
            cote_1,
        ),
        _construire_candidat_1x2(
            "X",
            px,
            cote_x,
        ),
        _construire_candidat_1x2(
            "2",
            p2,
            cote_2,
        ),
    ]

    divergences = detecter_divergences(
        p1,
        px,
        p2,
        {
            "1": marche_actuel.get(
                "1",
                0.0,
            ),
            "X": marche_actuel.get(
                "X",
                0.0,
            ),
            "2": marche_actuel.get(
                "2",
                0.0,
            ),
        },
    )

    regime = _appel_module(
        analyser_regime,
        home_matches,
        away_matches,
        default={
            "regime": "normal",
            "fiabilite": 0.50,
        },
    )

    signature = _appel_module(
        analyser_signature_foot,
        home_ctx,
        home_glob,
        away_ctx,
        away_glob,
        default={
            "score": 0.50,
            "classification": "neutre",
        },
    )

    forensics = _appel_module(
        analyser_market_forensics,
        cotes_actuelles,
        cotes_ouverture,
        {
            "1": p1,
            "X": px,
            "2": p2,
        },
        default={
            "fiabilite": 0.50,
            "alertes": [],
        },
    )

    stacking = _appel_module(
        analyser_meta_ensemble,
        {
            "p1": p1,
            "px": px,
            "p2": p2,
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "regime": regime,
            "signature": signature,
        },
        default={
            "fiabilite": 0.50,
            "score": 0.50,
        },
    )

    cross_market = _appel_module(
        analyser_cross_market,
        {
            "p1": p1,
            "px": px,
            "p2": p2,
            "lambda_total": lambda_total,
        },
        default={
            "consistency": 0.50,
            "alertes": [],
        },
    )

    candidats_1x2 = _normaliser_candidats(
        candidats_1x2,
        forensics=forensics,
        stacking=stacking,
        cross_market=cross_market,
    )

    meilleur_1x2 = _selectionner_meilleur_candidat(
        candidats_1x2
    )

    handicap_resultats = []

    lignes_hcp = _safe_list(
        hcp_lignes
    )

    for ligne in lignes_hcp:

        if isinstance(ligne, dict):

            ligne_dom = ligne.get(
                "dom",
                ligne.get(
                    "home",
                    ligne.get(
                        "ligne",
                        0.0,
                    ),
                ),
            )

            ligne_ext = ligne.get(
                "ext",
                ligne.get(
                    "away",
                    None,
                ),
            )

            cote_dom = ligne.get(
                "cote_dom",
                ligne.get(
                    "home_odds",
                ),
            )

            cote_ext = ligne.get(
                "cote_ext",
                ligne.get(
                    "away_odds",
                ),
            )

        elif isinstance(ligne, (list, tuple)):

            ligne_dom = (
                ligne[0]
                if len(ligne) >= 1
                else 0.0
            )

            ligne_ext = (
                ligne[1]
                if len(ligne) >= 2
                else None
            )

            cote_dom = (
                ligne[2]
                if len(ligne) >= 3
                else None
            )

            cote_ext = (
                ligne[3]
                if len(ligne) >= 4
                else None
            )

        else:

            ligne_dom = ligne
            ligne_ext = None
            cote_dom = None
            cote_ext = None

        handicap_resultats.append(
            calcul_handicap_complet(
                matrice,
                ligne_dom,
                ligne_ext,
                cote_dom,
                cote_ext,
            )
        )

    ou_resultats = _construire_ou_resultats(
        lambda_total,
        ou_lignes,
    )

    marches_2mt = calcul_marches_2mt(
        p1_ht,
        px_ht,
        p2_ht,
        p1_2h,
        px_2h,
        p2_2h,
        cotes_ht=None,
        cotes_2h=None,
                 )

tous_candidats = []

    tous_candidats.extend(
        candidats_1x2
    )

    for resultat_hcp in handicap_resultats:

        if not isinstance(resultat_hcp, dict):
            continue

        tous_candidats.extend(
            _safe_list(
                resultat_hcp.get(
                    "candidats",
                    [],
                )
            )
        )

    for resultat_ou in ou_resultats:

        if not isinstance(resultat_ou, dict):
            continue

        candidats_ou = resultat_ou.get(
            "candidats",
            [],
        )

        candidats_ou = _normaliser_candidats(
            candidats_ou,
            forensics=forensics,
            stacking=stacking,
            cross_market=cross_market,
        )

        resultat_ou["candidats"] = candidats_ou

        tous_candidats.extend(
            candidats_ou
        )

    tous_candidats = _normaliser_candidats(
        tous_candidats,
        forensics=forensics,
        stacking=stacking,
        cross_market=cross_market,
    )

    meilleur_candidat = _selectionner_meilleur_candidat(
        tous_candidats
    )

    if meilleur_candidat is None:

        pari_retenu = {
            "marche": "Aucun",
            "selection": "NO BET",
            "probabilite": 0.0,
            "proba": 0.0,
            "p": 0.0,                 # ← correction KeyError
            "cote": 0.0,
            "ev": 0.0,
            "fiabilite": 0.0,
            "stake": 0.0,
            "decision": "NO BET",
        }

    else:

        pari_retenu = dict(
            meilleur_candidat
        )

    # --------------------------------------------------------
    # OU SÉCURITÉ
    # --------------------------------------------------------

    ou_securite = []

    for resultat in ou_resultats:

        if not isinstance(resultat, dict):
            continue

        ligne = resultat.get(
            "ligne"
        )

        p_over = _safe_float(
            resultat.get(
                "p_over",
                0.0,
            )
        )

        p_under = _safe_float(
            resultat.get(
                "p_under",
                0.0,
            )
        )

        if p_under >= 0.70:

            ou_securite.append({
                "marche": "Under",
                "selection": f"Under {ligne}",
                "ligne": ligne,
                "probabilite": round(p_under, 4),
                "proba": round(p_under, 4),
                "p": round(p_under, 4),
                "fiabilite": round(
                    compute_reliability(
                        p_under,
                        resultat.get("cote_under", 0.0),
                    ),
                    4,
                ),
            })

        if p_over >= 0.70:

            ou_securite.append({
                "marche": "Over",
                "selection": f"Over {ligne}",
                "ligne": ligne,
                "probabilite": round(p_over, 4),
                "proba": round(p_over, 4),
                "p": round(p_over, 4),
                "fiabilite": round(
                    compute_reliability(
                        p_over,
                        resultat.get("cote_over", 0.0),
                    ),
                    4,
                ),
            })

    # --------------------------------------------------------
    # DIAGNOSTIC
    # --------------------------------------------------------

    regime_nom = "normal"

    if isinstance(regime, dict):

        regime_nom = regime.get(
            "regime",
            regime.get(
                "classification",
                "normal",
            ),
        )

    fiabilite_regime = 0.50

    if isinstance(regime, dict):

        fiabilite_regime = _clamp(
            regime.get(
                "fiabilite",
                regime.get(
                    "confidence",
                    0.50,
                ),
            )
        )

    fiabilite_forensics = 0.50

    if isinstance(forensics, dict):

        fiabilite_forensics = _clamp(
            forensics.get(
                "fiabilite",
                forensics.get(
                    "reliability",
                    0.50,
                ),
            )
        )

    fiabilite_stacking = 0.50

    if isinstance(stacking, dict):

        fiabilite_stacking = _clamp(
            stacking.get(
                "fiabilite",
                stacking.get(
                    "reliability",
                    stacking.get(
                        "score",
                        0.50,
                    ),
                ),
            )
        )

    consistency = 0.50

    if isinstance(cross_market, dict):

        consistency = _clamp(
            cross_market.get(
                "consistency",
                cross_market.get(
                    "score",
                    0.50,
                ),
            )
        )

    diagnostic = {
        "ligue": ligue,
        "regime": regime_nom,
        "fiabilite_regime": round(
            fiabilite_regime,
            4,
        ),
        "fiabilite_forensics": round(
            fiabilite_forensics,
            4,
        ),
        "fiabilite_stacking": round(
            fiabilite_stacking,
            4,
        ),
        "cross_market_consistency": round(
            consistency,
            4,
        ),
        "divergences_marche": divergences,
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
        "ratio_ht": round(
            ratio_ht,
            4,
        ),
        "nb_candidats": len(
            tous_candidats
        ),
    }

    # --------------------------------------------------------
    # STRUCTURE MODERNE V23
    # --------------------------------------------------------

    probabilites_1x2 = {
        "1": round(
            p1,
            4,
        ),
        "X": round(
            px,
            4,
        ),
        "2": round(
            p2,
            4,
        ),
    }

    marches = {
        "1X2": candidats_1x2,
        "handicap": handicap_resultats,
        "over_under": ou_resultats,
    }

    meta_ensemble = stacking

    market_forensics = forensics

    signature_foot = signature

    resultat = {
        # ----------------------------------------------------
        # IDENTIFICATION
        # ----------------------------------------------------

        "ligue": ligue,

        # ----------------------------------------------------
        # PROBABILITÉS
        # ----------------------------------------------------

        "probabilites_1x2": probabilites_1x2,

        "p1": round(
            p1,
            4,
        ),

        "px": round(
            px,
            4,
        ),

        "p2": round(
            p2,
            4,
        ),

        # ----------------------------------------------------
        # LAMBDAS
        # ----------------------------------------------------

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

        "lambda_home_ht": round(
            lambda_home_ht,
            4,
        ),

        "lambda_away_ht": round(
            lambda_away_ht,
            4,
        ),

        "lambda_home_2h": round(
            lambda_home_2h,
            4,
        ),

        "lambda_away_2h": round(
            lambda_away_2h,
            4,
        ),

        "ratio_ht": round(
            ratio_ht,
            4,
        ),

        # ----------------------------------------------------
        # MARCHÉS MODERNES
        # ----------------------------------------------------

        "marches": marches,

        "meilleurs_candidats": tous_candidats,

        "signature_foot": signature_foot,

        "market_forensics": market_forensics,

        "meta_ensemble": meta_ensemble,

        "cross_market": cross_market,

        "regime": regime,

        "diagnostic": diagnostic,

        # ----------------------------------------------------
        # DONNÉES MARCHÉ
        # ----------------------------------------------------

        "marche_actuel": marche_actuel,

        "marche_ouverture": marche_ouverture,

        "cotes_actuelles": cotes_actuelles,

        "cotes_ouverture": cotes_ouverture,

        "divergences": divergences,

        # ----------------------------------------------------
        # CHOIX FINAL
        # ----------------------------------------------------

        "meilleur_candidat": meilleur_candidat,

        "pari_retenu": pari_retenu,

        "decision": pari_retenu.get(
            "decision",
            "NO BET",
        ),

        # ----------------------------------------------------
        # MARCHÉS FOOTBALL
        # ----------------------------------------------------

        "candidats": candidats_1x2,

        "handicap_resultats": handicap_resultats,

        "ou_resultats": ou_resultats,

        "ou_securite": ou_securite,

        "marches_2mt": marches_2mt,

        # ----------------------------------------------------
        # MATRICES / DISTRIBUTIONS
        # ----------------------------------------------------

        "matrice_score": matrice,

        "matrice_ht": matrice_ht,

        "matrice_2h": matrice_2h,

        # ----------------------------------------------------
        # PROBABILITÉS HT / 2H
        # ----------------------------------------------------

        "p1_ht": round(
            p1_ht,
            4,
        ),

        "px_ht": round(
            px_ht,
            4,
        ),

        "p2_ht": round(
            p2_ht,
            4,
        ),

        "p1_2h": round(
            p1_2h,
            4,
        ),

        "px_2h": round(
            p2_2h,
            4,
        ),

        "p2_2h": round(
            p2_2h,
            4,
        ),

        # ----------------------------------------------------
        # ALIASES COMPATIBILITÉ MAIN.PY V23
        # ----------------------------------------------------

        "forensics": market_forensics,

        "stacking": meta_ensemble,

        "signature": signature_foot,
    }

    # --------------------------------------------------------
    # ALIAS DE COMPATIBILITÉ SUPPLÉMENTAIRES
    # --------------------------------------------------------

    resultat["probabilites"] = probabilites_1x2

    resultat["1x2"] = candidats_1x2

    resultat["handicap"] = handicap_resultats

    resultat["over_under"] = ou_resultats

    resultat["ou"] = ou_resultats

    resultat["meilleur"] = meilleur_candidat

    resultat["regime_nom"] = regime_nom

    return resultat
