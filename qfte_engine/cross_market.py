"""
qfte_engine/cross_market.py
---------------------------
CROSS-MARKET CORRELATION ENGINE - QFTE V23.0

Detecte les incoherences entre marches 1X2, Handicap, Over/Under, BTTS.
- Calibration Poisson contrainte
- Incoherence Score
- Arbitrage croise
- Consistency Score
- Ajustement fiabilite
"""

import math


# =========================================================
# 1. POISSON HELPERS
# =========================================================
def poisson_pmf(k, lam):
    if lam <= 0:
        lam = 0.01
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def calculer_p1_poisson(mu_h, mu_a, max_goals=8):
    """P(home gagne) pour un Poisson(mu_h, mu_a)."""
    p1 = 0.0
    total = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson_pmf(i, mu_h) * poisson_pmf(j, mu_a)
            total += p
            if i > j:
                p1 += p
    if total > 0:
        p1 /= total
    return p1


def calculer_p_over_poisson(mu_h, mu_a, ligne, max_goals=8):
    """P(Over) pour un Poisson(mu_h, mu_a) et une ligne donnee."""
    p_over = 0.0
    total = 0.0
    est_entiere = abs(ligne - round(ligne)) < 1e-9
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson_pmf(i, mu_h) * poisson_pmf(j, mu_a)
            total += p
            seuil_total = i + j
            if est_entiere:
                if seuil_total > int(round(ligne)):
                    p_over += p
            else:
                if seuil_total > ligne:
                    p_over += p
    if total > 0:
        p_over /= total
    return p_over


def calculer_p_btts_poisson(mu_h, mu_a, max_goals=8):
    """P(BTTS oui) pour un Poisson(mu_h, mu_a)."""
    p_oui = 0.0
    total = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson_pmf(i, mu_h) * poisson_pmf(j, mu_a)
            total += p
            if i >= 1 and j >= 1:
                p_oui += p
    if total > 0:
        p_oui /= total
    return p_oui


# =========================================================
# 2. CALIBRATION POISSON CONTRAINTE
# =========================================================
def calibrer_poisson_pour_p1(p1_cible, ratio_mu=1.3, max_iter=60):
    """
    Trouve (mu_h, mu_a) avec mu_h/mu_a = ratio_mu tel que P(1) = p1_cible.
    Bissection sur mu_total.
    """
    p1_cible = max(min(p1_cible, 0.99), 0.01)

    mu_min = 0.4
    mu_max = 10.0
    mu_h, mu_a = 1.5, 1.0

    for _ in range(max_iter):
        mu_total = (mu_min + mu_max) / 2.0
        mu_h = mu_total * ratio_mu / (1 + ratio_mu)
        mu_a = mu_total / (1 + ratio_mu)

        p1_calc = calculer_p1_poisson(mu_h, mu_a, max_goals=8)

        if abs(p1_calc - p1_cible) < 0.002:
            return round(mu_h, 3), round(mu_a, 3)

        if p1_calc > p1_cible:
            mu_max = mu_total
        else:
            mu_min = mu_total

    return round(mu_h, 3), round(mu_a, 3)


def calibrer_poisson_pour_over(p_over_cible, ligne, ratio_mu=1.3, max_iter=60):
    """
    Trouve (mu_h, mu_a) avec mu_h/mu_a = ratio_mu tel que P(Over) = p_over_cible.
    """
    p_over_cible = max(min(p_over_cible, 0.99), 0.01)

    mu_min = 0.4
    mu_max = 10.0
    mu_h, mu_a = 1.5, 1.0

    for _ in range(max_iter):
        mu_total = (mu_min + mu_max) / 2.0
        mu_h = mu_total * ratio_mu / (1 + ratio_mu)
        mu_a = mu_total / (1 + ratio_mu)

        p_over_calc = calculer_p_over_poisson(mu_h, mu_a, ligne, max_goals=8)

        if abs(p_over_calc - p_over_cible) < 0.002:
            return round(mu_h, 3), round(mu_a, 3)

        if p_over_calc > p_over_cible:
            mu_max = mu_total
        else:
            mu_min = mu_total

    return round(mu_h, 3), round(mu_a, 3)


# =========================================================
# 3. DEMARGEAGE
# =========================================================
def demargeage_proportionnel(cotes):
    if not cotes or any(c is None or c <= 0 for c in cotes):
        return None
    inv = [1/c for c in cotes]
    total = sum(inv)
    if total <= 0:
        return None
    return [i/total for i in inv]


# =========================================================
# 4. INCOHERENCE SCORE
# =========================================================
def calculer_incoherence(p_marche, p_coherente):
    """
    Mesure l'ecart entre P_marche et P_coherente.
    Retourne un dict avec score et niveau.
    """
    if p_coherente is None or p_coherente <= 0:
        return {
            "p_marche": round(p_marche, 4),
            "p_coherente": None,
            "ecart_absolu": 0.0,
            "ecart_relatif": 0.0,
            "niveau": "INCONNU",
            "interpretation": "Pas assez de donnees",
        }

    ecart_absolu = p_marche - p_coherente
    ecart_relatif = ecart_absolu / p_coherente

    niveau_abs = abs(ecart_relatif)

    if niveau_abs >= 0.15:
        niveau = "MAJEURE"
        if ecart_absolu > 0:
            interp = "Marche SURESTIME ce marche - value probable"
        else:
            interp = "Marche SOUS-ESTIME ce marche - piege probable"
    elif niveau_abs >= 0.05:
        niveau = "MODEREE"
        interp = "Incoherence moderee - a surveiller"
    else:
        niveau = "FAIBLE"
        interp = "Marches coherents"

    return {
        "p_marche": round(p_marche, 4),
        "p_coherente": round(p_coherente, 4),
        "ecart_absolu": round(ecart_absolu, 4),
        "ecart_relatif": round(ecart_relatif, 4),
        "niveau": niveau,
        "interpretation": interp,
  }



# =========================================================
# 5. ARBITRAGE CROISE
# =========================================================
def detecter_arbitrage_croise(candidats, seuil_min=0.02):
    """
    Detecte les arbitrages entre marches via les vraies cotes.
    Un arbitrage existe si : 1/c1 + 1/c2 < 1
    """
    arbitrages = []
    n = len(candidats)
    for i in range(n):
        for j in range(i+1, n):
            c1 = candidats[i]
            c2 = candidats[j]
            if not c1 or not c2:
                continue
            if not c1.get("cote") or not c2.get("cote"):
                continue
            if c1["cote"] <= 1 or c2["cote"] <= 1:
                continue
            # Verifier que les 2 marches sont exclusifs (complementaires)
            # Ex: Over 2.5 et Under 2.5
            m1 = c1.get("marche", "")
            m2 = c2.get("marche", "")
            sel1 = c1.get("selection", "")
            sel2 = c2.get("selection", "")
            if m1 != m2:
                continue
            # Verifier complementarite (ex: Over X / Under X)
            if "Over" in sel1 and "Under" in sel2:
                pass
            elif "Under" in sel1 and "Over" in sel2:
                pass
            else:
                continue
            # Verifier meme ligne
            l1 = c1.get("ligne")
            l2 = c2.get("ligne")
            if l1 != l2:
                continue
            # Calcul arbitrage
            inv_sum = 1/c1["cote"] + 1/c2["cote"]
            if inv_sum < 1 - seuil_min:
                profit_pct = (1 - inv_sum) * 100
                arbitrages.append({
                    "marche": m1,
                    "candidat_1": sel1,
                    "cote_1": c1["cote"],
                    "candidat_2": sel2,
                    "cote_2": c2["cote"],
                    "inv_sum": round(inv_sum, 4),
                    "profit_pct": round(profit_pct, 2),
                })
    return arbitrages


# =========================================================
# 6. CONSISTENCY SCORE
# =========================================================
def calculer_consistency_score(incoherences):
    """
    Score global de coherence entre marches.
    1 = tout coherent, 0 = tout incoherent.
    """
    valides = [i for i in incoherences if i.get("ecart_relatif") is not None]
    if not valides:
        return {
            "consistency": 0.5,
            "label": "INCONNU",
            "nb_incoherences_majeures": 0,
            "nb_incoherences_moderees": 0,
            "interpretation": "Pas assez de donnees",
        }

    # Moyenne des ecarts relatifs absolus
    somme_ecarts = sum(abs(i["ecart_relatif"]) for i in valides)
    moyenne_ecart = somme_ecarts / len(valides)

    # Consistency : 1 si ecart 0, decroit jusqu'a 0 pour ecart 0.20
    consistency = 1.0 - min(moyenne_ecart / 0.20, 1.0)
    consistency = round(max(min(consistency, 1.0), 0.0), 3)

    nb_majeures = sum(1 for i in valides if i["niveau"] == "MAJEURE")
    nb_moderees = sum(1 for i in valides if i["niveau"] == "MODEREE")

    if consistency >= 0.85:
        label = "TRES COHERENT"
        interp = "Marches bien alignes"
    elif consistency >= 0.70:
        label = "COHERENT"
        interp = "Marches coherents - legeres variations"
    elif consistency >= 0.50:
        label = "INCOHERENT"
        interp = "Plusieurs incoherences detectees"
    else:
        label = "TRES INCOHERENT"
        interp = "Marches contradictoires - opportunites possibles"

    return {
        "consistency": consistency,
        "label": label,
        "nb_incoherences_majeures": nb_majeures,
        "nb_incoherences_moderees": nb_moderees,
        "interpretation": interp,
    }


# =========================================================
# 7. AJUSTEMENT DE FIABILITE VIA CONSISTENCY
# =========================================================
def ajuster_fiabilite_consistency(fiabilite, consistency):
    """
    Ajuste la fiabilite d'un pari selon le Consistency Score.
    - Consistency elevee : bonus +0.02
    - Consistency faible : malus -0.05
    """
    score = consistency["consistency"]

    if score >= 0.85:
        ajust = 0.02
    elif score >= 0.70:
        ajust = 0.01
    elif score >= 0.50:
        ajust = -0.02
    else:
        ajust = -0.05

    nouvelle = fiabilite + ajust
    return round(max(min(nouvelle, 1.0), 0.0), 3)


# =========================================================
# 8. ANALYSE CROSS-MARKET
# =========================================================
def analyser_cross_market(
    candidats_1x2, candidats_hcp, candidats_ou, candidats_btts,
    mu_total_ref=None
):
    """
    Orchestre l'analyse Cross-Market.

    Utilise les candidats deja evalues (avec marche, selection, p, cote)
    pour detecter les incoherences et arbitrages.
    """
    incoherences = []

    # ===== 1X2 vs O/U =====
    # Si P(1) est eleve, P(Over 2.5) doit etre coherent
    if candidats_1x2:
        c1_1x2 = None
        for c in candidats_1x2:
            if c and "1 (Domicile)" in c.get("selection", ""):
                c1_1x2 = c
                break
        if c1_1x2:
            p1 = c1_1x2["p"]
            # Chercher Over 2.5
            if candidats_ou:
                for c_ou in candidats_ou:
                    if c_ou and "Over 2.5" in c_ou.get("selection", ""):
                        p_over_marche = c_ou["p"]
                        # Recalibrer Poisson pour P(1) et voir P(Over 2.5) implicite
                        mu_h, mu_a = calibrer_poisson_pour_p1(p1, ratio_mu=1.3)
                        p_over_coherente = calculer_p_over_poisson(mu_h, mu_a, 2.5)
                        incoh = calculer_incoherence(p_over_marche, p_over_coherente)
                        incoh["marche"] = "Over 2.5"
                        incoh["reference"] = "1X2 - 1 (Domicile)"
                        incoherences.append(incoh)
                        break
                # Chercher Under 3.5
                for c_ou in candidats_ou:
                    if c_ou and "Under 3.5" in c_ou.get("selection", ""):
                        p_under_marche = c_ou["p"]
                        mu_h, mu_a = calibrer_poisson_pour_p1(p1, ratio_mu=1.3)
                        p_under_coherente = 1.0 - calculer_p_over_poisson(mu_h, mu_a, 3.5)
                        incoh = calculer_incoherence(p_under_marche, p_under_coherente)
                        incoh["marche"] = "Under 3.5"
                        incoh["reference"] = "1X2 - 1 (Domicile)"
                        incoherences.append(incoh)
                        break

    # ===== Hcp vs 1X2 =====
    if candidats_hcp and candidats_1x2:
        c1_1x2 = None
        for c in candidats_1x2:
            if c and "1 (Domicile)" in c.get("selection", ""):
                c1_1x2 = c
                break
        if c1_1x2:
            p1 = c1_1x2["p"]
            for c_hcp in candidats_hcp:
                if c_hcp and c_hcp.get("cible") == "Domicile":
                    hcp = c_hcp.get("hcp")
                    if hcp is None:
                        continue
                    p_hcp_marche = c_hcp["p"]
                    mu_h, mu_a = calibrer_poisson_pour_p1(p1, ratio_mu=1.3)
                    # Recalibrer via P(1) et calculer P(handicap)
                    p_hcp_coherente = _calculer_p_hcp(mu_h, mu_a, hcp)
                    incoh = calculer_incoherence(p_hcp_marche, p_hcp_coherente)
                    incoh["marche"] = "Hcp " + str(hcp) + " (Dom)"
                    incoh["reference"] = "1X2 - 1 (Domicile)"
                    incoherences.append(incoh)
                    break

    # ===== O/U vs O/U (Over 2.5 vs Under 3.5) =====
    if candidats_ou:
        c_over = None
        c_under = None
        for c in candidats_ou:
            if c and "Over 2.5" in c.get("selection", ""):
                c_over = c
            if c and "Under 3.5" in c.get("selection", ""):
                c_under = c
        if c_over and c_under:
            p_over = c_over["p"]
            p_under = c_under["p"]
            # Over 2.5 + Under 3.5 doivent totaliser >= 1 (car total ∈ {3} commun)
            # Plus precisement, P(Over 2.5) + P(Under 3.5) >= 1
            somme = p_over + p_under
            if somme < 0.98:
                incoh = {
                    "marche": "Over 2.5 + Under 3.5",
                    "p_marche": round(somme, 4),
                    "p_coherente": 1.0,
                    "ecart_absolu": round(somme - 1.0, 4),
                    "ecart_relatif": round(somme - 1.0, 4),
                    "niveau": "MAJEURE" if abs(somme - 1.0) > 0.05 else "MODEREE",
                    "interpretation": "Somme des probas complementaires < 100%",
                }
                incoherences.append(incoh)

    # ===== BTTS vs 1X2 =====
    if candidats_btts and candidats_1x2:
        c_btts_oui = None
        for c in candidats_btts:
            if c and "Oui" in c.get("selection", ""):
                c_btts_oui = c
                break
        if c_btts_oui:
            p_btts = c_btts_oui["p"]
            c1_1x2 = None
            for c in candidats_1x2:
                if c and "1 (Domicile)" in c.get("selection", ""):
                    c1_1x2 = c
                    break
            if c1_1x2:
                p1 = c1_1x2["p"]
                mu_h, mu_a = calibrer_poisson_pour_p1(p1, ratio_mu=1.3)
                p_btts_coherente = calculer_p_btts_poisson(mu_h, mu_a)
                incoh = calculer_incoherence(p_btts, p_btts_coherente)
                incoh["marche"] = "BTTS Oui"
                incoh["reference"] = "1X2 - 1 (Domicile)"
                incoherences.append(incoh)

    # ===== ARBITRAGES =====
    tous_candidats = []
    if candidats_ou:
        tous_candidats.extend(candidats_ou)
    if candidats_btts:
        tous_candidats.extend(candidats_btts)
    arbitrages = detecter_arbitrage_croise(tous_candidats)

    # ===== CONSISTENCY =====
    consistency = calculer_consistency_score(incoherences)

    return {
        "disponible": True,
        "incoherences": incoherences,
        "arbitrages": arbitrages,
        "consistency": consistency,
        "nb_incoherences": len(incoherences),
        "nb_arbitrages": len(arbitrages),
    }


def _calculer_p_hcp(mu_h, mu_a, hcp, max_goals=8):
    """P(gain du handicap pour domicile)."""
    p_gain = 0.0
    total = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson_pmf(i, mu_h) * poisson_pmf(j, mu_a)
            total += p
            marge = i - j
            seuil = -hcp
            if marge > seuil:
                p_gain += p
            elif marge == seuil and abs(seuil - round(seuil)) < 1e-9:
                p_gain += 0.5 * p
    if total > 0:
        p_gain /= total
    return p_gain
