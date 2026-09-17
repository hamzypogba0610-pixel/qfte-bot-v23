"""
qfte_engine/regime.py
---------------------
MARKET REGIME DETECTOR - QFTE V23.0

Detecte le regime du marche (CALME / VOLATIL / TENDANCE / CHAOS)
et adapte les seuils de discipline + le multiplicateur de stake.
"""

import math


REGIME_CALME = "CALME"
REGIME_VOLATIL = "VOLATIL"
REGIME_TENDANCE = "TENDANCE"
REGIME_CHAOS = "CHAOS"


def moyenne(valeurs):
    v = [x for x in valeurs if x is not None]
    if not v:
        return 0.0
    return sum(v) / len(v)


def ecart_type(valeurs):
    v = [x for x in valeurs if x is not None]
    if len(v) < 2:
        return 0.0
    m = moyenne(v)
    variance = sum((x - m) ** 2 for x in v) / len(v)
    return math.sqrt(variance)


def detecter_regime(mouvements):
    """
    Analyse les mouvements de cotes et detecte le regime.

    Parametres :
      mouvements : dict avec cles "1", "X", "2", chaque valeur = dict
                   avec "delta" (variation relative).

    Retourne un dict complet avec regime, metriques et seuils adaptes.
    """
    if not mouvements:
        return _regime_defaut()

    deltas = []
    for k in ["1", "X", "2"]:
        m = mouvements.get(k)
        if m and m.get("delta") is not None:
            deltas.append(m["delta"])

    if len(deltas) < 2:
        return _regime_defaut()

    abs_deltas = [abs(d) for d in deltas]
    volatilite = moyenne(abs_deltas)
    amplitude = max(abs_deltas) - min(abs_deltas)
    et = ecart_type(deltas)

    positifs = sum(1 for d in deltas if d > 0.02)
    negatifs = sum(1 for d in deltas if d < -0.02)
    stables = len(deltas) - positifs - negatifs

    if positifs == len(deltas) or negatifs == len(deltas):
        directionnalite = 1.0
    elif stables == len(deltas):
        directionnalite = 0.0
    else:
        directionnalite = max(positifs, negatifs) / len(deltas)

    if volatilite > 0.10 and directionnalite < 0.5:
        regime = REGIME_CHAOS
    elif volatilite > 0.08:
        regime = REGIME_VOLATIL
    elif directionnalite >= 0.66:
        regime = REGIME_TENDANCE
    elif volatilite < 0.03 and directionnalite < 0.4:
        regime = REGIME_CALME
    else:
        regime = REGIME_VOLATIL

    seuils = _seuils_par_regime(regime)

    return {
        "disponible": True,
        "regime": regime,
        "volatilite": round(volatilite, 4),
        "amplitude": round(amplitude, 4),
        "ecart_type": round(et, 4),
        "directionnalite": round(directionnalite, 4),
        "nb_positifs": positifs,
        "nb_negatifs": negatifs,
        "nb_stables": stables,
        "seuil_fiabilite": seuils["fiabilite"],
        "seuil_value": seuils["value"],
        "seuil_confiance": seuils["confiance"],
        "multiplicateur_stake": seuils["stake"],
        "description": seuils["description"],
}



def _seuils_par_regime(regime):
    if regime == REGIME_CALME:
        return {
            "fiabilite": 0.80,
            "value": 0.06,
            "confiance": 0.72,
            "stake": 0.90,
            "description": "Marche efficient - seuils stricts",
        }
    elif regime == REGIME_VOLATIL:
        return {
            "fiabilite": 0.75,
            "value": 0.05,
            "confiance": 0.70,
            "stake": 1.00,
            "description": "Sharp actif - seuils normaux",
        }
    elif regime == REGIME_TENDANCE:
        return {
            "fiabilite": 0.73,
            "value": 0.045,
            "confiance": 0.68,
            "stake": 1.05,
            "description": "Mouvement directionnel - seuils souples",
        }
    else:
        return {
            "fiabilite": 0.82,
            "value": 0.07,
            "confiance": 0.74,
            "stake": 0.70,
            "description": "Marche chaotique - seuils tres stricts",
        }


def _regime_defaut():
    return {
        "disponible": False,
        "regime": "INCONNU",
        "volatilite": 0.0,
        "amplitude": 0.0,
        "ecart_type": 0.0,
        "directionnalite": 0.0,
        "nb_positifs": 0,
        "nb_negatifs": 0,
        "nb_stables": 0,
        "seuil_fiabilite": 0.75,
        "seuil_value": 0.05,
        "seuil_confiance": 0.70,
        "multiplicateur_stake": 1.00,
        "description": "Regime non determine - seuils par defaut",
    }


def analyser_regime(forensics_result):
    """
    Wrapper : prend le resultat de forensics et detecte le regime.

    Parametres :
      forensics_result : dict retourne par analyser_market_forensics

    Retourne le dict regime.
    """
    if not forensics_result or not forensics_result.get("disponible"):
        return _regime_defaut()

    mouvements = forensics_result.get("mouvements", {})
    return detecter_regime(mouvements)


def appliquer_regime_aux_seuils(seuil_fiab_base, seuil_value_base, seuil_conf_base, regime):
    """
    Combine les seuils de base avec ceux du regime.

    Le seuil final = moyenne ponderee (60% base, 40% regime).
    """
    if not regime or not regime.get("disponible"):
        return {
            "fiabilite": seuil_fiab_base,
            "value": seuil_value_base,
            "confiance": seuil_conf_base,
            "multiplicateur_stake": 1.0,
        }

    fiab = 0.6 * seuil_fiab_base + 0.4 * regime["seuil_fiabilite"]
    val = 0.6 * seuil_value_base + 0.4 * regime["seuil_value"]
    conf = 0.6 * seuil_conf_base + 0.4 * regime["seuil_confiance"]

    return {
        "fiabilite": round(fiab, 4),
        "value": round(val, 4),
        "confiance": round(conf, 4),
        "multiplicateur_stake": regime["multiplicateur_stake"],
  }
