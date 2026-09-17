import json
import re
from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from qfte_engine.mvp import analyser_match_football
from qfte_engine.basket import analyser_match_basket

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")


def parse_matchs(t):
    r = []
    if not t:
        return r
    for m in [x.strip() for x in t.split(",") if x.strip()]:
        mh = re.match(r"^(\d+)\s*-\s*(\d+)\s*\(\s*(\d+)\s*-\s*(\d+)\s*\)$", m)
        ms = re.match(r"^(\d+)\s*-\s*(\d+)$", m)
        if mh:
            r.append({"bp": int(mh.group(1)), "bc": int(mh.group(2)), "ht_bp": int(mh.group(3)), "ht_bc": int(mh.group(4))})
        elif ms:
            r.append({"bp": int(ms.group(1)), "bc": int(ms.group(2)), "ht_bp": None, "ht_bc": None})
    return r


def parse_hcp(t):
    r = []
    if not t:
        return r
    for m in [x.strip() for x in t.split(",") if x.strip()]:
        p = [x.strip() for x in m.split("/") if x.strip()]
        if len(p) != 4:
            continue
        try:
            r.append({"hcp_dom": float(p[0]), "cote_dom": float(p[1]), "hcp_ext": float(p[2]), "cote_ext": float(p[3])})
        except:
            pass
    return r


def parse_ou(t):
    r = []
    if not t:
        return r
    for m in [x.strip() for x in t.split(",") if x.strip()]:
        p = [x.strip() for x in m.split("/") if x.strip()]
        if len(p) != 3:
            continue
        try:
            r.append({"ligne": float(p[0]), "cote_over": float(p[1]), "cote_under": float(p[2])})
        except:
            pass
    return r


def parse_ml(t):
    if not t:
        return None
    p = [x.strip() for x in t.split("/") if x.strip()]
    if len(p) != 2:
        return None
    try:
        return [float(p[0]), float(p[1])]
    except:
        return None


def parse_total_mt(t):
    if not t:
        return None
    p = [x.strip() for x in t.split("/") if x.strip()]
    if len(p) != 3:
        return None
    try:
        return [float(p[0]), float(p[1]), float(p[2])]
    except:
        return None


def parse_quart(t):
    if not t:
        return None
    resultat = {}
    for bloc in t.split("|"):
        bloc = bloc.strip()
        if bloc.upper().startswith("TOTAL="):
            val = bloc.split("=", 1)[1].strip()
            p = [x.strip() for x in val.split("/") if x.strip()]
            if len(p) == 3:
                try:
                    resultat["total"] = [float(p[0]), float(p[1]), float(p[2])]
                except:
                    pass
        elif bloc.upper().startswith("ML="):
            val = bloc.split("=", 1)[1].strip()
            p = [x.strip() for x in val.split("/") if x.strip()]
            if len(p) == 2:
                try:
                    resultat["ml"] = [float(p[0]), float(p[1])]
                except:
                    pass
    return resultat if resultat else None


def ff(form, k, d=0.0):
    v = form.get(k, "")
    if v is None or v == "":
        return d
    try:
        return float(v)
    except:
        return d


def fi(form, k):
    v = form.get(k, "")
    if v is None or v == "":
        return None
    try:
        return int(v)
    except:
        return None



def bloc_candidat(c):
    ec = "#4ade80" if c["ev"] >= 0 else "#ef4444"
    if c["passe_filtres"]:
        st = '<span style="color:#4ade80;font-weight:bold;">PASSE</span>'
        rh = ""
    else:
        st = '<span style="color:#ef4444;font-weight:bold;">REJETE</span>'
        rh = "".join(['<p style="color:#ef4444;font-size:12px;">-> ' + x + '</p>' for x in c["raisons_rejet"]])

    out = '<div style="border:1px solid #262636;background:#14141f;padding:10px;margin-top:8px;border-radius:8px;">'
    if c.get("marche"):
        out += '<p><b>Marche :</b> ' + c["marche"] + '</p>'
    out += '<p><b>Selection :</b> ' + c["selection"] + '</p>'
    out += '<p><b>Proba :</b> ' + str(round(c["p"] * 100, 2)) + '%</p>'
    out += '<p><b>Cote :</b> ' + str(c["cote"]) + '</p>'
    out += '<p><b>EV :</b> <span style="color:' + ec + ';">' + str(round(c["ev"] * 100, 2)) + '%</span></p>'
    if c.get("ajustement_forensics") and c["ajustement_forensics"] != 0:
        s = "+" if c["ajustement_forensics"] > 0 else ""
        col = "#4ade80" if c["ajustement_forensics"] > 0 else "#ef4444"
        out += '<p><b>Ajust. Forensics :</b> <span style="color:' + col + ';">' + s + str(c["ajustement_forensics"]) + '</span></p>'
    if c.get("ajustement_stacking") and c["ajustement_stacking"] != 0:
        s = "+" if c["ajustement_stacking"] > 0 else ""
        col = "#4ade80" if c["ajustement_stacking"] > 0 else "#ef4444"
        out += '<p><b>Ajust. Stacking :</b> <span style="color:' + col + ';">' + s + str(c["ajustement_stacking"]) + '</span></p>'
    if c.get("ajustement_consistency") and c["ajustement_consistency"] != 0:
        s = "+" if c["ajustement_consistency"] > 0 else ""
        col = "#4ade80" if c["ajustement_consistency"] > 0 else "#ef4444"
        out += '<p><b>Ajust. Cross-Market :</b> <span style="color:' + col + ';">' + s + str(c["ajustement_consistency"]) + '</span></p>'
    out += '<p><b>Fiabilite :</b> ' + str(c["fiabilite"]) + '</p>'
    out += '<p><b>Filtres :</b> ' + st + '</p>'
    out += rh
    out += '</div>'
    return out


def bloc_visuel(r, sport):
    html = ''

    rg = r.get("regime")
    if rg and rg.get("disponible"):
        col_reg = "#4ade80"
        if rg["regime"] == "CHAOS":
            col_reg = "#ef4444"
        elif rg["regime"] == "VOLATIL":
            col_reg = "#eab308"
        elif rg["regime"] == "TENDANCE":
            col_reg = "#22c55e"
        html += '<div style="border:2px solid #f97316;background:#1a0f00;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#f97316;margin-top:0;">📊 MARKET REGIME</h3>'
        html += '<p>Regime : <b style="color:' + col_reg + ';">' + rg["regime"] + '</b></p>'
        html += '<p>Volatilite : ' + str(rg["volatilite"]) + ' | Amplitude : ' + str(rg["amplitude"]) + '</p>'
        html += '<p>Directionnalite : ' + str(rg["directionnalite"]) + '</p>'
        html += '<p>Seuils : fiab ' + str(rg["seuil_fiabilite"]) + ' | value ' + str(round(rg["seuil_value"] * 100, 1)) + '% | conf ' + str(rg["seuil_confiance"]) + '</p>'
        html += '<p>Multiplicateur stake : x' + str(rg["multiplicateur_stake"]) + '</p>'
        html += '<p style="font-size:12px;color:#aaa;">' + rg["description"] + '</p>'
        html += '</div>'

    f = r.get("forensics")
    if f and f.get("disponible"):
        sh = f["sharpe_signal"]
        html += '<div style="border:2px solid #0ea5e9;background:#0a1620;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#0ea5e9;margin-top:0;">🔎 MARKET FORENSICS</h3>'
        m = f["mouvements"]
        for k in ["1", "X", "2"]:
            mo = m.get(k)
            if not mo:
                continue
            if mo["delta"] <= -0.05:
                col = "#4ade80"
            elif mo["delta"] >= 0.05:
                col = "#ef4444"
            else:
                col = "#eab308"
            html += '<p>' + k + ' : ' + str(mo["open"]) + ' -> ' + str(mo["curr"]) + ' <span style="color:' + col + ';">' + str(mo["delta_pct"]) + '%</span></p>'
        html += '<p>Pattern : <b>' + f["pattern"]["pattern"] + '</b></p>'
        html += '<p>CLV pred. : ' + str(round(f["clv"]["clv_predictif"] * 100, 2)) + '%</p>'
        html += '<p>Sharp Money : ' + str(f["sharp_money"]["score"]) + ' (' + f["sharp_money"]["label"] + ')</p>'
        html += '<p>Efficience : ' + str(f["efficience"]["efficience"]) + '</p>'
        html += '<p style="color:' + sh["couleur"] + ';font-size:16px;">⭐ SHARPE : ' + str(sh["sharpe_signal"]) + ' (' + sh["label"] + ')</p>'
        html += '</div>'

    s = r.get("stacking")
    if s and s.get("disponible"):
        p = s["poids"]
        html += '<div style="border:2px solid #a855f7;background:#1a0f2a;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#a855f7;margin-top:0;">🧠 META-ENSEMBLE STACKING</h3>'
        html += '<p>Consensus : ' + str(s["consensus_global"]) + '</p>'
        html += '<p>Poisson : ' + str(p["w_poisson"]) + ' | DC : ' + str(p["w_dc"]) + ' | MC : ' + str(p["w_mc"]) + ' | Bayes : ' + str(p["w_bayes"]) + '</p>'
        html += '<p>P(1) : ' + str(round(s["p1_final"] * 100, 2)) + '% | P(X) : ' + str(round(s["px_final"] * 100, 2)) + '% | P(2) : ' + str(round(s["p2_final"] * 100, 2)) + '%</p>'
        html += '<p>PCS : ' + str(s["pcs"]["pcs"]) + ' (' + s["pcs"]["label"] + ')</p>'
        html += '</div>'

    cm = r.get("cross_market")
    if cm and cm.get("disponible"):
        html += '<div style="border:2px solid #14b8a6;background:#0a1a1a;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#14b8a6;margin-top:0;">🔀 CROSS-MARKET</h3>'
        html += '<p>Incoherences : ' + str(cm["nb_incoherences"]) + '</p>'
        for inc in cm["incoherences"]:
            html += '<p>' + inc.get("marche", "?") + ' : ' + str(round(inc["ecart_relatif"] * 100, 1)) + '% (' + inc["niveau"] + ')</p>'
        html += '<p>Consistency : ' + str(cm["consistency"]["consistency"]) + ' (' + cm["consistency"]["label"] + ')</p>'
        html += '</div>'

    if sport == "basketball" and r.get("signature"):
        sig = r["signature"]
        html += '<div style="border:2px solid #a855f7;background:#1a0f2a;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#a855f7;margin-top:0;">🔬 TRUE SIGMA</h3>'
        html += '<p>Sigma final : ' + str(sig["sigma_final"]) + ' (ligue ' + str(sig["sigma_ligue"]) + ')</p>'
        html += '<p>Alerte : ' + sig["niveau_alerte"] + ' | Multiplicateur : x' + str(sig["multiplicateur_stake"]) + '</p>'
        html += '</div>'

    if sport == "football" and r.get("signature"):
        sigf = r["signature"]
        html += '<div style="border:2px solid #f59e0b;background:#1a150a;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#f59e0b;margin-top:0;">🔬 SIGNATURE FOOT</h3>'
        html += '<p>Prior ligue : ' + str(sigf["prior_ligue"]) + '</p>'
        html += '<p>Lambda dom : ' + str(sigf["lambda_home_brut"]) + ' -> ' + str(sigf["lambda_home_bayesien"]) + '</p>'
        html += '<p>Lambda ext : ' + str(sigf["lambda_away_brut"]) + ' -> ' + str(sigf["lambda_away_bayesien"]) + '</p>'
        html += '</div>'

    return html



@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "titre": "QFTE V23.0"})


@app.get("/football", response_class=HTMLResponse)
async def page_football(request: Request):
    return templates.TemplateResponse("football.html", {"request": request, "titre": "QFTE Football"})


@app.get("/basketball", response_class=HTMLResponse)
async def page_basketball(request: Request):
    return templates.TemplateResponse("basketball.html", {"request": request, "titre": "QFTE Basketball"})


@app.get("/health")
async def health():
    return {"status": "ok", "version": "V23.0"}


@app.post("/analyser", response_class=HTMLResponse)
async def analyser(request: Request):
    form = await request.form()

    sport = form.get("sport", "football")
    ligue = form.get("ligue", "autre")
    competition = form.get("competition", "")
    eq_dom = form.get("equipe_domicile", "")
    eq_ext = form.get("equipe_exterieur", "")

    home_ctx = parse_matchs(form.get("home_contextuel", ""))
    home_glob = parse_matchs(form.get("home_global", ""))
    away_ctx = parse_matchs(form.get("away_contextuel", ""))
    away_glob = parse_matchs(form.get("away_global", ""))
    h2h = parse_matchs(form.get("h2h", ""))
    hcp_lignes = parse_hcp(form.get("handicap", ""))
    ou_lignes = parse_ou(form.get("ou_buts", ""))

    o1 = ff(form, "open_1")
    ox = ff(form, "open_x")
    o2 = ff(form, "open_2")
    c1 = ff(form, "curr_1")
    cx = ff(form, "curr_x")
    c2 = ff(form, "curr_2")

    pd = fi(form, "pos_dom")
    pe = fi(form, "pos_ext")
    te = fi(form, "total_equipes")

    if sport == "football":
        r = analyser_match_football(
            home_ctx, home_glob, away_ctx, away_glob,
            o1, ox, o2, c1, cx, c2,
            "normale", "normal",
            False, False, False, False,
            h2h, hcp_lignes, ou_lignes,
            pd, pe, te,
            None, None,
            ligue
        )

        html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>QFTE</title></head><body style="background:#0f0f1a;color:#eee;padding:20px;font-family:Arial;">'
        html += '<h1 style="color:#ffcc00;">Analyse Football</h1>'
        html += '<p>' + eq_dom + ' vs ' + eq_ext + ' (' + ligue + ')</p>'

        p = r.get("pari_retenu")
        if p:
            html += '<div style="border:2px solid #4ade80;background:#0a1a0a;padding:12px;border-radius:8px;margin-top:12px;">'
            html += '<h2 style="color:#4ade80;margin-top:0;">PARI RETENU</h2>'
            html += '<p><b>Marche :</b> ' + p.get("marche", "?") + '</p>'
            html += '<p><b>Selection :</b> ' + p["selection"] + '</p>'
            html += '<p><b>Cote :</b> ' + str(p["cote"]) + '</p>'
            html += '<p><b>Probabilite :</b> ' + str(round(p["p"] * 100, 2)) + '%</p>'
            html += '<p><b>EV :</b> ' + str(round(p["ev"] * 100, 2)) + '%</p>'
            html += '<p><b>Fiabilite :</b> ' + str(p["fiabilite"]) + '</p>'
            html += '<p><b>Niveau :</b> ' + p["niveau"] + '</p>'
            html += '<p><b>Decision :</b> ' + p["decision"] + '</p>'
            if p.get("stake_origine"):
                html += '<p><b>Stake origine :</b> ' + str(p["stake_origine"]) + '%</p>'
            html += '<p><b>Stake final :</b> ' + str(p["stake"]) + '% bankroll</p>'
            html += '</div>'
        else:
            html += '<div style="border:2px solid #ef4444;background:#1a0a0a;padding:12px;border-radius:8px;margin-top:12px;">'
            html += '<h2 style="color:#ef4444;margin-top:0;">AUCUN PARI RETENU</h2>'
            html += '<p>Aucune selection ne respecte les filtres V23.0.</p>'
            html += '</div>'

        html += '<div style="border:1px solid #262636;background:#14141f;padding:12px;border-radius:8px;margin-top:12px;">'
        html += '<h2 style="color:#ffcc00;margin-top:0;">Buts attendus (lambda)</h2>'
        html += '<p>' + eq_dom + ' : ' + str(r["lambda_home"]) + '</p>'
        html += '<p>' + eq_ext + ' : ' + str(r["lambda_away"]) + '</p>'
        html += '</div>'

        html += '<div style="border:1px solid #262636;background:#14141f;padding:12px;border-radius:8px;margin-top:12px;">'
        html += '<h2 style="color:#ffcc00;margin-top:0;">Probabilites 1X2</h2>'
        html += '<p>P(1) : ' + str(round(r["p1"] * 100, 2)) + '%</p>'
        html += '<p>P(X) : ' + str(round(r["px"] * 100, 2)) + '%</p>'
        html += '<p>P(2) : ' + str(round(r["p2"] * 100, 2)) + '%</p>'
        html += '</div>'

        html += bloc_visuel(r, "football")

        if r.get("ou_securite"):
            s = r["ou_securite"]
            html += '<div style="border:2px solid #60a5fa;background:#0a1020;padding:12px;border-radius:8px;margin-top:12px;">'
            html += '<h2 style="color:#60a5fa;margin-top:0;">🛡️ SECURITE O/U</h2>'
            html += '<p><b>Marche :</b> ' + s.get("type_ou", "?") + ' ' + str(s.get("ligne", "?")) + '</p>'
            html += '<p><b>Cote :</b> ' + str(s["cote"]) + '</p>'
            html += '<p><b>P(effective) :</b> ' + str(round(s["p"] * 100, 2)) + '%</p>'
            html += '<p><b>EV :</b> ' + str(round(s["ev"] * 100, 2)) + '%</p>'
            html += '<p><b>Fiabilite :</b> ' + str(s["fiabilite"]) + '</p>'
            html += '</div>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - 1X2</h2>'
        for c in r["candidats"]:
            html += bloc_candidat(c)

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Handicap</h2>'
        if r["handicap_resultats"]:
            for h in r["handicap_resultats"]:
                html += bloc_candidat(h)
        else:
            html += '<p style="color:#666;">Aucun handicap saisi.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Over / Under</h2>'
        if r["ou_resultats"]:
            for o in r["ou_resultats"]:
                html += bloc_candidat(o)
        else:
            html += '<p style="color:#666;">Aucun O/U saisi.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - 2 Mi-temps</h2>'
        m2 = r["marches_2mt"]
        if m2.get("ht"):
            html += '<p><b>P 1 / X / 2 HT :</b> ' + str(round(m2["p1_ht"] * 100, 1)) + '% / ' + str(round(m2["px_ht"] * 100, 1)) + '% / ' + str(round(m2["p2_ht"] * 100, 1)) + '%</p>'
            for c in m2["ht"]:
                html += bloc_candidat(c)
        if m2.get("2h"):
            html += '<p><b>P 1 / X / 2 2H :</b> ' + str(round(m2["p1_2h"] * 100, 1)) + '% / ' + str(round(m2["px_2h"] * 100, 1)) + '% / ' + str(round(m2["p2_2h"] * 100, 1)) + '%</p>'
            for c in m2["2h"]:
                html += bloc_candidat(c)
        if not m2.get("ht") and not m2.get("2h"):
            html += '<p style="color:#666;">Aucune cote 2 mi-temps saisie.</p>'

        html += '<p style="margin-top:20px;"><a href="/football" style="color:#ffcc00;">Retour</a></p>'
        html += '</body></html>'
        return HTMLResponse(content=html)

    else:
        ml_ft = parse_ml(form.get("ml_ft", ""))
        ml_1h = parse_ml(form.get("ml_1h", ""))
        ml_2h = parse_ml(form.get("ml_2h", ""))
        total_1h = parse_total_mt(form.get("total_1h", ""))
        total_2h = parse_total_mt(form.get("total_2h", ""))
        q1 = parse_quart(form.get("q1", ""))
        q2 = parse_quart(form.get("q2", ""))
        q3 = parse_quart(form.get("q3", ""))
        q4 = parse_quart(form.get("q4", ""))

        r = analyser_match_basket(
            home_ctx, home_glob, away_ctx, away_glob,
            h2h, hcp_lignes, ou_lignes,
            False, False, False, False, pd, pe, te,
            ml_ft, ml_1h, ml_2h, total_1h, total_2h,
            ligue,
            None, None, None,
            None, None, None,
            q1, q2, q3, q4,
            o1, o2, c1, c2
        )

        html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>QFTE</title></head><body style="background:#0f0f1a;color:#eee;padding:20px;font-family:Arial;">'
        html += '<h1 style="color:#ffcc00;">Analyse Basketball</h1>'
        html += '<p>' + eq_dom + ' vs ' + eq_ext + ' (' + ligue + ')</p>'

        p = r.get("pari_retenu")
        if p:
            html += '<div style="border:2px solid #4ade80;background:#0a1a0a;padding:12px;border-radius:8px;margin-top:12px;">'
            html += '<h2 style="color:#4ade80;margin-top:0;">PARI RETENU</h2>'
            html += '<p><b>Marche :</b> ' + p.get("marche", "?") + '</p>'
            html += '<p><b>Selection :</b> ' + p["selection"] + '</p>'
            html += '<p><b>Cote :</b> ' + str(p["cote"]) + '</p>'
            html += '<p><b>Probabilite :</b> ' + str(round(p["p"] * 100, 2)) + '%</p>'
            html += '<p><b>EV :</b> ' + str(round(p["ev"] * 100, 2)) + '%</p>'
            html += '<p><b>Fiabilite :</b> ' + str(p["fiabilite"]) + '</p>'
            html += '<p><b>Niveau :</b> ' + p["niveau"] + '</p>'
            html += '<p><b>Decision :</b> ' + p["decision"] + '</p>'
            if p.get("stake_origine"):
                html += '<p><b>Stake origine :</b> ' + str(p["stake_origine"]) + '%</p>'
            html += '<p><b>Stake final :</b> ' + str(p["stake"]) + '% bankroll</p>'
            html += '</div>'
        else:
            html += '<div style="border:2px solid #ef4444;background:#1a0a0a;padding:12px;border-radius:8px;margin-top:12px;">'
            html += '<h2 style="color:#ef4444;margin-top:0;">AUCUN PARI RETENU</h2>'
            html += '<p>Aucune selection ne respecte les filtres V23.0.</p>'
            html += '</div>'

        html += '<div style="border:1px solid #262636;background:#14141f;padding:12px;border-radius:8px;margin-top:12px;">'
        html += '<h2 style="color:#ffcc00;margin-top:0;">Points attendus (mu)</h2>'
        html += '<p>' + eq_dom + ' : ' + str(r["mu_home"]) + '</p>'
        html += '<p>' + eq_ext + ' : ' + str(r["mu_away"]) + '</p>'
        html += '<p>Total FT : ' + str(r["mu_total"]) + '</p>'
        html += '<p>Total 1H : ' + str(r["mu_total_1h"]) + '</p>'
        html += '<p>Total 2H : ' + str(r["mu_total_2h"]) + '</p>'
        html += '</div>'

        html += bloc_visuel(r, "basketball")

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Moneyline</h2>'
        if r["ml_candidats"]:
            for c in r["ml_candidats"]:
                html += bloc_candidat(c)
        else:
            html += '<p style="color:#666;">Aucune cote ML saisie.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Spread</h2>'
        if r["spread_candidats"]:
            for c in r["spread_candidats"]:
                html += bloc_candidat(c)
        else:
            html += '<p style="color:#666;">Aucun spread saisi.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Total Points FT</h2>'
        if r["total_ft_candidats"]:
            for c in r["total_ft_candidats"]:
                html += bloc_candidat(c)
        else:
            html += '<p style="color:#666;">Aucun total FT saisi.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - 1ere Mi-temps (1H)</h2>'
        if r["ml_1h_candidats"]:
            for c in r["ml_1h_candidats"]:
                html += bloc_candidat(c)
        if r["total_1h_candidats"]:
            for c in r["total_1h_candidats"]:
                html += bloc_candidat(c)
        if not r["ml_1h_candidats"] and not r["total_1h_candidats"]:
            html += '<p style="color:#666;">Aucune cote 1H saisie.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - 2eme Mi-temps (2H)</h2>'
        if r["ml_2h_candidats"]:
            for c in r["ml_2h_candidats"]:
                html += bloc_candidat(c)
        if r["total_2h_candidats"]:
            for c in r["total_2h_candidats"]:
                html += bloc_candidat(c)
        if not r["ml_2h_candidats"] and not r["total_2h_candidats"]:
            html += '<p style="color:#666;">Aucune cote 2H saisie.</p>'

        for nom_q in ["Q1", "Q2", "Q3", "Q4"]:
            qd = r["quarts"][nom_q]
            html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - ' + nom_q + '</h2>'
            if qd.get("mu"):
                html += '<p><b>Mu total ' + nom_q + ' :</b> ' + str(qd["mu"]) + '</p>'
            if qd["total"]:
                for c in qd["total"]:
                    html += bloc_candidat(c)
            if qd["ml"]:
                for c in qd["ml"]:
                    html += bloc_candidat(c)
            if not qd["total"] and not qd["ml"]:
                html += '<p style="color:#666;">Aucune cote ' + nom_q + ' saisie.</p>'

        html += '<p style="margin-top:20px;"><a href="/basketball" style="color:#ffcc00;">Retour</a></p>'
        html += '</body></html>'
        return HTMLResponse(content=html)
