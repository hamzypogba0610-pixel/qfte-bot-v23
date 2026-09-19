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
    if not isinstance(c, dict):
        return ""
    ev = float(c.get("ev", 0))
    proba = float(c.get("p", c.get("probabilite", 0)))
    ec = "#4ade80" if ev >= 0 else "#ef4444"
    if c.get("passe_filtres"):
        st = '<span style="color:#4ade80;font-weight:bold;">PASSE</span>'
        rh = ""
    else:
        st = '<span style="color:#ef4444;font-weight:bold;">REJETE</span>'
        rh = "".join(['<p style="color:#ef4444;font-size:12px;">-> ' + str(x) + '</p>' for x in c.get("raisons_rejet") or []])
    out = '<div style="border:1px solid #262636;background:#14141f;padding:10px;margin-top:8px;border-radius:8px;">'
    if c.get("marche"):
        out += '<p><b>Marche :</b> ' + str(c.get("marche", "")) + '</p>'
    out += '<p><b>Selection :</b> ' + str(c.get("selection", "?")) + '</p>'
    out += '<p><b>Proba :</b> ' + str(round(proba * 100, 2)) + '%</p>'
    out += '<p><b>Cote :</b> ' + str(c.get("cote", 0)) + '</p>'
    out += '<p><b>EV :</b> <span style="color:' + ec + ';">' + str(round(ev * 100, 2)) + '%</span></p>'
    out += '<p><b>Fiabilite :</b> ' + str(c.get("fiabilite", 0)) + '</p>'
    out += '<p><b>Filtres :</b> ' + st + '</p>'
    out += rh
    out += '</div>'
    return out



def bloc_visuel(r, sport):
    html = ''

    rg = r.get("regime")
    if rg and rg.get("disponible"):
        col_reg = "#4ade80"
        if rg.get("regime") == "CHAOS":
            col_reg = "#ef4444"
        elif rg.get("regime") == "VOLATIL":
            col_reg = "#eab308"
        elif rg.get("regime") == "TENDANCE":
            col_reg = "#22c55e"
        html += '<div style="border:2px solid #f97316;background:#1a0f00;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#f97316;margin-top:0;">📊 MARKET REGIME</h3>'
        html += '<p>Regime : <b style="color:' + col_reg + ';">' + str(rg.get("regime", "N/A")) + '</b></p>'
        html += '<p>Volatilite : ' + str(rg.get("volatilite", 0)) + ' | Amplitude : ' + str(rg.get("amplitude", 0)) + '</p>'
        html += '<p>Directionnalite : ' + str(rg.get("directionnalite", 0)) + '</p>'
        html += '<p>Seuils : fiab ' + str(rg.get("seuil_fiabilite", 0)) + ' | value ' + str(round(float(rg.get("seuil_value", 0)) * 100, 1)) + '% | conf ' + str(rg.get("seuil_confiance", 0)) + '</p>'
        html += '<p>Multiplicateur stake : x' + str(rg.get("multiplicateur_stake", 1)) + '</p>'
        html += '<p style="font-size:12px;color:#aaa;">' + str(rg.get("description", "")) + '</p>'
        html += '</div>'

    td = r.get("time_decay")
    if td:
        html += '<div style="border:2px solid #8b5cf6;background:#150f2a;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#8b5cf6;margin-top:0;">⏱️ TIME-DECAY</h3>'
        html += '<p>Ponderation par rang (recent = poids max)</p>'
        html += '<p>BP dom ctx (pond.) : ' + str(td.get("home_bp_ctx_pond", 0)) + '</p>'
        html += '<p>BP dom glob (pond.) : ' + str(td.get("home_bp_glob_pond", 0)) + '</p>'
        html += '<p>BP ext ctx (pond.) : ' + str(td.get("away_bp_ctx_pond", 0)) + '</p>'
        html += '<p>BP ext glob (pond.) : ' + str(td.get("away_bp_glob_pond", 0)) + '</p>'
        html += '</div>'

    f = r.get("forensics")
    if f and f.get("disponible"):
        sh = f.get("sharpe_signal", {})
        html += '<div style="border:2px solid #0ea5e9;background:#0a1620;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#0ea5e9;margin-top:0;">🔎 MARKET FORENSICS</h3>'
        m = f.get("mouvements", {})
        for k in ["1", "X", "2"]:
            mo = m.get(k)
            if not mo:
                continue
            if mo.get("delta", 0) <= -0.05:
                col = "#4ade80"
            elif mo.get("delta", 0) >= 0.05:
                col = "#ef4444"
            else:
                col = "#eab308"
            html += '<p>' + k + ' : ' + str(mo.get("open", 0)) + ' -> ' + str(mo.get("curr", 0)) + ' <span style="color:' + col + ';">' + str(mo.get("delta_pct", 0)) + '%</span></p>'
        html += '<p>Pattern : <b>' + str(f.get("pattern", {}).get("pattern", "N/A")) + '</b></p>'
        html += '<p>CLV pred. : ' + str(round(float(f.get("clv", {}).get("clv_predictif", 0)) * 100, 2)) + '%</p>'
        html += '<p>Sharp Money : ' + str(f.get("sharp_money", {}).get("score", 0)) + ' (' + str(f.get("sharp_money", {}).get("label", "")) + ')</p>'
        html += '<p>Efficience : ' + str(f.get("efficience", {}).get("efficience", 0)) + '</p>'
        html += '<p style="color:' + str(sh.get("couleur", "#fff")) + ';font-size:16px;">⭐ SHARPE : ' + str(sh.get("sharpe_signal", 0)) + ' (' + str(sh.get("label", "")) + ')</p>'
        html += '</div>'

    s = r.get("stacking")
    if s and s.get("disponible"):
        p = s.get("poids", {})
        html += '<div style="border:2px solid #a855f7;background:#1a0f2a;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#a855f7;margin-top:0;">🧠 META-ENSEMBLE STACKING</h3>'
        html += '<p>Consensus : ' + str(s.get("consensus_global", 0)) + '</p>'
        html += '<p>Poisson : ' + str(p.get("w_poisson", 0)) + ' | DC : ' + str(p.get("w_dc", 0)) + ' | MC : ' + str(p.get("w_mc", 0)) + ' | Bayes : ' + str(p.get("w_bayes", 0)) + '</p>'
        html += '<p>P(1) : ' + str(round(float(s.get("p1_final", 0)) * 100, 2)) + '% | P(X) : ' + str(round(float(s.get("px_final", 0)) * 100, 2)) + '% | P(2) : ' + str(round(float(s.get("p2_final", 0)) * 100, 2)) + '%</p>'
        html += '<p>PCS : ' + str(s.get("pcs", {}).get("pcs", 0)) + ' (' + str(s.get("pcs", {}).get("label", "")) + ')</p>'
        html += '</div>'

    cm = r.get("cross_market")
    if cm and cm.get("disponible"):
        html += '<div style="border:2px solid #14b8a6;background:#0a1a1a;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#14b8a6;margin-top:0;">🔀 CROSS-MARKET</h3>'
        html += '<p>Incoherences : ' + str(cm.get("nb_incoherences", 0)) + '</p>'
        for inc in cm.get("incoherences", []):
            html += '<p>' + str(inc.get("marche", "?")) + ' : ' + str(round(float(inc.get("ecart_relatif", 0)) * 100, 1)) + '% (' + str(inc.get("niveau", "")) + ')</p>'
        html += '<p>Consistency : ' + str(cm.get("consistency", {}).get("consistency", 0)) + ' (' + str(cm.get("consistency", {}).get("label", "")) + ')</p>'
        html += '</div>'

    if sport == "basketball" and r.get("signature"):
        sig = r["signature"]
        html += '<div style="border:2px solid #a855f7;background:#1a0f2a;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#a855f7;margin-top:0;">🔬 TRUE SIGMA</h3>'
        html += '<p>Sigma final : ' + str(sig.get("sigma_final", "N/A")) + ' (ligue ' + str(sig.get("sigma_ligue", "N/A")) + ')</p>'
        html += '<p>Alerte : ' + str(sig.get("niveau_alerte", "N/A")) + ' | Multiplicateur : x' + str(sig.get("multiplicateur_stake", 1)) + '</p>'
        html += '</div>'

    if sport == "football" and r.get("signature"):
        sigf = r["signature"]
        html += '<div style="border:2px solid #f59e0b;background:#1a150a;padding:10px;margin-top:12px;border-radius:8px;">'
        html += '<h3 style="color:#f59e0b;margin-top:0;">🔬 SIGNATURE FOOT</h3>'
        html += '<p>Prior ligue : ' + str(sigf.get("prior_ligue", "N/A")) + '</p>'
        html += '<p>Lambda dom : ' + str(sigf.get("lambda_home_brut", "N/A")) + ' -> ' + str(sigf.get("lambda_home_bayesien", "N/A")) + '</p>'
        html += '<p>Lambda ext : ' + str(sigf.get("lambda_away_brut", "N/A")) + ' -> ' + str(sigf.get("lambda_away_bayesien", "N/A")) + '</p>'
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
    try:
        return await _analyser_interne(request)
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        err = err.replace("<", "&lt;").replace(">", "&gt;")
        return HTMLResponse(content="<pre style='background:#000;color:#4ade80;padding:20px;font-size:12px;white-space:pre-wrap;'>ERREUR :\n\n" + err + "</pre>")


async def _analyser_interne(request: Request):
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
        html += '<p><b>Marche :</b> ' + str(p.get("marche", "?")) + '</p>'
        html += '<p><b>Selection :</b> ' + str(p.get("selection", "?")) + '</p>'
        html += '<p><b>Cote :</b> ' + str(p.get("cote", 0)) + '</p>'
        html += '<p><b>Probabilite :</b> ' + str(round(float(p.get("p", p.get("probabilite", 0))) * 100, 2)) + '%</p>'
        html += '<p><b>EV :</b> ' + str(round(float(p.get("ev", 0)) * 100, 2)) + '%</p>'
        html += '<p><b>Fiabilite :</b> ' + str(p.get("fiabilite", 0)) + '</p>'
        html += '<p><b>Niveau :</b> ' + str(p.get("niveau", "N/A")) + '</p>'
        html += '<p><b>Decision :</b> ' + str(p.get("decision", "NO BET")) + '</p>'
        if p.get("stake_origine"):
            html += '<p><b>Stake origine :</b> ' + str(p.get("stake_origine", 0)) + '%</p>'
        html += '<p><b>Stake final :</b> ' + str(p.get("stake", 0)) + '% bankroll</p>'
        html += '</div>'
    else:
        html += '<div style="border:2px solid #ef4444;background:#1a0a0a;padding:12px;border-radius:8px;margin-top:12px;">'
        html += '<h2 style="color:#ef4444;margin-top:0;">AUCUN PARI RETENU</h2>'
        html += '<p>Aucune selection ne respecte les filtres V23.0.</p>'
        html += '</div>'

    html += '<div style="border:1px solid #262636;background:#14141f;padding:12px;border-radius:8px;margin-top:12px;">'
    html += '<h2 style="color:#ffcc00;margin-top:0;">Buts attendus (lambda)</h2>'
    html += '<p>' + eq_dom + ' : ' + str(r.get("lambda_home", 0)) + '</p>'
    html += '<p>' + eq_ext + ' : ' + str(r.get("lambda_away", 0)) + '</p>'
    html += '</div>'

    html += '<div style="border:1px solid #262636;background:#14141f;padding:12px;border-radius:8px;margin-top:12px;">'
    html += '<h2 style="color:#ffcc00;margin-top:0;">Probabilites 1X2</h2>'
    html += '<p>P(1) : ' + str(round(float(r.get("p1", 0)) * 100, 2)) + '%</p>'
    html += '<p>P(X) : ' + str(round(float(r.get("px", 0)) * 100, 2)) + '%</p>'
    html += '<p>P(2) : ' + str(round(float(r.get("p2", 0)) * 100, 2)) + '%</p>'
    html += '</div>'

    html += bloc_visuel(r, "football")

    if r.get("ou_securite"):
        s = r["ou_securite"]
        if isinstance(s, list) and s:
            s = s[0]
        if isinstance(s, dict):
            html += '<div style="border:2px solid #60a5fa;background:#0a1020;padding:12px;border-radius:8px;margin-top:12px;">'
            html += '<h2 style="color:#60a5fa;margin-top:0;">SECURITE O/U</h2>'
            html += '<p><b>Marche :</b> ' + str(s.get("marche", s.get("type_ou", "?"))) + ' ' + str(s.get("ligne", "?")) + '</p>'
            html += '<p><b>Cote :</b> ' + str(s.get("cote", 0)) + '</p>'
            html += '<p><b>P(effective) :</b> ' + str(round(float(s.get("p", s.get("probabilite", 0))) * 100, 2)) + '%</p>'
            html += '<p><b>EV :</b> ' + str(round(float(s.get("ev", 0)) * 100, 2)) + '%</p>'
            html += '<p><b>Fiabilite :</b> ' + str(s.get("fiabilite", 0)) + '</p>'
            html += '</div>'

    html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - 1X2</h2>'
    for c in r.get("candidats", []):
        html += bloc_candidat(c)

    html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Handicap</h2>'
    if r.get("handicap_resultats"):
        for h in r["handicap_resultats"]:
            if isinstance(h, dict) and "candidats" in h:
                for c in h.get("candidats", []):
                    html += bloc_candidat(c)
            else:
                html += bloc_candidat(h)
    else:
        html += '<p style="color:#666;">Aucun handicap saisi.</p>'

    html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Over / Under</h2>'
    if r.get("ou_resultats"):
        for o in r["ou_resultats"]:
            if isinstance(o, dict) and "candidats" in o:
                for c in o.get("candidats", []):
                    html += bloc_candidat(c)
            else:
                html += bloc_candidat(o)
    else:
        html += '<p style="color:#666;">Aucun O/U saisi.</p>'

    html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - 2 Mi-temps</h2>'
    m2 = r.get("marches_2mt", {})
    if m2.get("ht"):
        html += '<p><b>P 1 / X / 2 HT :</b> ' + str(round(float(m2.get("p1_ht", 0)) * 100, 1)) + '% / ' + str(round(float(m2.get("px_ht", 0)) * 100, 1)) + '% / ' + str(round(float(m2.get("p2_ht", 0)) * 100, 1)) + '%</p>'
        for c in m2.get("ht", []):
            html += bloc_candidat(c)
    if m2.get("2h"):
        html += '<p><b>P 1 / X / 2 2H :</b> ' + str(round(float(m2.get("p1_2h", 0)) * 100, 1)) + '% / ' + str(round(float(m2.get("px_2h", 0)) * 100, 1)) + '% / ' + str(round(float(m2.get("p2_2h", 0)) * 100, 1)) + '%</p>'
        for c in m2.get("2h", []):
            html += bloc_candidat(c)
    if not m2.get("ht") and not m2.get("2h"):
        html += '<p style="color:#666;">Aucune cote 2 mi-temps saisie.</p>'

    html += '<p style="margin-top:20px;"><a href="/football" style="color:#ffcc00;">Retour</a></p>'
    html += '</body></html>'
    
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
            html += '<p><b>Marche :</b> ' + str(p.get("marche", "?")) + '</p>'
            html += '<p><b>Selection :</b> ' + str(p.get("selection", "?")) + '</p>'
            html += '<p><b>Cote :</b> ' + str(p.get("cote", 0)) + '</p>'
            html += '<p><b>Probabilite :</b> ' + str(round(float(p.get("p", p.get("probabilite", 0))) * 100, 2)) + '%</p>'
            html += '<p><b>EV :</b> ' + str(round(float(p.get("ev", 0)) * 100, 2)) + '%</p>'
            html += '<p><b>Fiabilite :</b> ' + str(p.get("fiabilite", 0)) + '</p>'
            html += '<p><b>Niveau :</b> ' + str(p.get("niveau", "N/A")) + '</p>'
            html += '<p><b>Decision :</b> ' + str(p.get("decision", "NO BET")) + '</p>'
            if p.get("stake_origine"):
                html += '<p><b>Stake origine :</b> ' + str(p.get("stake_origine", 0)) + '%</p>'
            html += '<p><b>Stake final :</b> ' + str(p.get("stake", 0)) + '% bankroll</p>'
            html += '</div>'
        else:
            html += '<div style="border:2px solid #ef4444;background:#1a0a0a;padding:12px;border-radius:8px;margin-top:12px;">'
            html += '<h2 style="color:#ef4444;margin-top:0;">AUCUN PARI RETENU</h2>'
            html += '<p>Aucune selection ne respecte les filtres V23.0.</p>'
            html += '</div>'

        html += '<div style="border:1px solid #262636;background:#14141f;padding:12px;border-radius:8px;margin-top:12px;">'
        html += '<h2 style="color:#ffcc00;margin-top:0;">Points attendus (mu)</h2>'
        html += '<p>' + eq_dom + ' : ' + str(r.get("mu_home", 0)) + '</p>'
        html += '<p>' + eq_ext + ' : ' + str(r.get("mu_away", 0)) + '</p>'
        html += '<p>Total FT : ' + str(r.get("mu_total", 0)) + '</p>'
        html += '<p>Total 1H : ' + str(r.get("mu_total_1h", 0)) + '</p>'
        html += '<p>Total 2H : ' + str(r.get("mu_total_2h", 0)) + '</p>'
        html += '</div>'

        html += bloc_visuel(r, "basketball")

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Moneyline</h2>'
        if r.get("ml_candidats"):
            for c in r["ml_candidats"]:
                html += bloc_candidat(c)
        else:
            html += '<p style="color:#666;">Aucune cote ML saisie.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Spread</h2>'
        if r.get("spread_candidats"):
            for c in r["spread_candidats"]:
                html += bloc_candidat(c)
        else:
            html += '<p style="color:#666;">Aucun spread saisi.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - Total Points FT</h2>'
        if r.get("total_ft_candidats"):
            for c in r["total_ft_candidats"]:
                html += bloc_candidat(c)
        else:
            html += '<p style="color:#666;">Aucun total FT saisi.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - 1ere Mi-temps (1H)</h2>'
        if r.get("ml_1h_candidats"):
            for c in r["ml_1h_candidats"]:
                html += bloc_candidat(c)
        if r.get("total_1h_candidats"):
            for c in r["total_1h_candidats"]:
                html += bloc_candidat(c)
        if not r.get("ml_1h_candidats") and not r.get("total_1h_candidats"):
            html += '<p style="color:#666;">Aucune cote 1H saisie.</p>'

        html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - 2eme Mi-temps (2H)</h2>'
        if r.get("ml_2h_candidats"):
            for c in r["ml_2h_candidats"]:
                html += bloc_candidat(c)
        if r.get("total_2h_candidats"):
            for c in r["total_2h_candidats"]:
                html += bloc_candidat(c)
        if not r.get("ml_2h_candidats") and not r.get("total_2h_candidats"):
            html += '<p style="color:#666;">Aucune cote 2H saisie.</p>'

        for nom_q in ["Q1", "Q2", "Q3", "Q4"]:
            qd = r.get("quarts", {}).get(nom_q, {})
            html += '<h2 style="color:#ffcc00;margin-top:20px;">Detail - ' + nom_q + '</h2>'
            if qd.get("mu"):
                html += '<p><b>Mu total ' + nom_q + ' :</b> ' + str(qd["mu"]) + '</p>'
            if qd.get("total"):
                for c in qd["total"]:
                    html += bloc_candidat(c)
            if qd.get("ml"):
                for c in qd["ml"]:
                    html += bloc_candidat(c)
            if not qd.get("total") and not qd.get("ml"):
                html += '<p style="color:#666;">Aucune cote ' + nom_q + ' saisie.</p>'

        html += '<p style="margin-top:20px;"><a href="/basketball" style="color:#ffcc00;">Retour</a></p>'
        html += '</body></html>'
        

            return HTMLResponse(content=html)


@app.get("/historique", response_class=HTMLResponse)
async def historique(request: Request):
    h = '<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Historique QFTE</title><style>'
    h += 'body{font-family:Arial;background:#0f0f1a;color:#eee;padding:20px;}'
    h += 'h1{color:#ffcc00;}a{color:#ffcc00;text-decoration:none;}'
    h += '.box{background:#14141f;border:1px solid #262636;border-radius:8px;padding:12px;margin-bottom:10px;}'
    h += '.btn{display:inline-block;padding:10px 14px;background:#ffcc00;color:#000;border:none;border-radius:6px;font-weight:bold;cursor:pointer;margin:4px;text-decoration:none;}'
    h += '.btn-danger{background:#ef4444;color:#fff;}'
    h += '</style></head><body>'
    h += '<h1>Historique QFTE V23.0</h1>'
    h += '<div style="text-align:center;margin-bottom:16px;">'
    h += '<a href="/" class="btn">Accueil</a> '
    h += '<button class="btn" onclick="exporter()">Exporter JSON</button> '
    h += '<button class="btn btn-danger" onclick="vider()">Vider</button>'
    h += '</div>'
    h += '<div id="compteur" style="text-align:center;color:#999;font-size:13px;margin-bottom:16px;"></div>'
    h += '<div id="liste"></div>'
    h += '<script>'
    h += 'function charger(){let h=[];try{h=JSON.parse(localStorage.getItem("qfte_analyses")||"[]");}catch(e){}return h;}'
    h += 'function afficher(){const hist=charger();const liste=document.getElementById("liste");const c=document.getElementById("compteur");'
    h += 'if(hist.length===0){c.textContent="";liste.innerHTML="<p style=\\"text-align:center;color:#666;\\">Aucune analyse sauvegardee.</p>";return;}'
    h += 'c.textContent=hist.length+" analyse(s)";let html="";'
    h += 'hist.forEach((a,i)=>{const r=a.resultats||{};const p=r.pari_retenu;'
    h += 'let resume="Aucun pari retenu";'
    h += 'if(p){resume=(p.selection||"?")+" @ "+(p.cote||"?")+" (EV "+((p.ev||0)*100).toFixed(2)+"%)";}'
    h += 'html+="<div class=box>";'
    h += 'html+="<p><b>#"+(i+1)+" - "+(a.date_analyse||"")+"</b></p>";'
    h += 'html+="<p>"+(a.equipe_domicile||"")+" vs "+(a.equipe_exterieur||"")+" ("+(a.sport||"")+")</p>";'
    h += 'html+="<p>"+resume+"</p>";'
    h += 'html+="</div>";});liste.innerHTML=html;}'
    h += 'function exporter(){const hist=charger();if(hist.length===0){alert("Rien a exporter.");return;}'
    h += 'const blob=new Blob([JSON.stringify(hist,null,2)],{type:"application/json"});'
    h += 'const url=URL.createObjectURL(blob);const a=document.createElement("a");'
    h += 'a.href=url;a.download="qfte_historique_"+new Date().toISOString().slice(0,10)+".json";'
    h += 'document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(url);}'
    h += 'function vider(){if(!confirm("Vider tout l historique ?"))return;localStorage.removeItem("qfte_analyses");afficher();}'
    h += 'afficher();</script></body></html>'
    return HTMLResponse(content=h)
