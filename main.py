import json
import re
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from qfte_engine.mvp import analyser_match_football
from qfte_engine.basket import analyser_match_basket

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")

STYLE = "body{font-family:-apple-system,Arial;background:#0f0f1a;color:#eee;padding:16px;line-height:1.5}h1{color:#ffcc00;font-size:20px;text-align:center}h2{color:#ffcc00;font-size:15px;margin:10px 0 8px;border-bottom:1px solid #333;padding-bottom:6px}.box{background:#14141f;border:1px solid #262636;border-radius:10px;padding:12px;margin-bottom:14px}.ligne{display:flex;justify-content:space-between;padding:4px 0;font-size:14px}.label{color:#999}.val{color:#fff;font-weight:bold}a{color:#ffcc00;text-decoration:none}.btn{display:inline-block;padding:12px 16px;background:#ffcc00;color:#000;border:none;border-radius:8px;font-size:14px;font-weight:bold;cursor:pointer;margin:6px 4px;text-decoration:none}.btn-secondary{background:#262636;color:#ffcc00}.btn-danger{background:#ef4444;color:#fff}.empty{text-align:center;color:#666;padding:40px 20px}.badge{display:inline-block;padding:3px 8px;border-radius:4px;font-size:11px;font-weight:bold}.badge-elite{background:#4ade80;color:#000}.badge-premium{background:#22c55e;color:#000}.badge-good{background:#eab308;color:#000}.badge-avoid{background:#ef4444;color:#fff}"


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


def fopt(form, k):
    v = form.get(k, "")
    if v is None or v == "":
        return None
    try:
        return float(v)
    except:
        return None



def bloc_candidat(c):
    ec = "#4ade80" if c["ev"] >= 0 else "#ef4444"
    if c["passe_filtres"]:
        st = '<span style="color:#4ade80;font-weight:bold;">PASSE</span>'
        rh = ""
    else:
        st = '<span style="color:#ef4444;font-weight:bold;">REJETE</span>'
        rh = "".join(['<div class="ligne"><span class="label" style="color:#ef4444;font-size:12px;">-> ' + x + '</span></div>' for x in c["raisons_rejet"]])
    out = '<div class="box">'
    if c.get("marche"):
        out += '<div class="ligne"><span class="label">Marche</span><span class="val">' + c["marche"] + '</span></div>'
    out += '<div class="ligne"><span class="label">Selection</span><span class="val">' + c["selection"] + '</span></div>'
    out += '<div class="ligne"><span class="label">Proba</span><span class="val">' + str(round(c["p"] * 100, 2)) + '%</span></div>'
    out += '<div class="ligne"><span class="label">Cote</span><span class="val">' + str(c["cote"]) + '</span></div>'
    out += '<div class="ligne"><span class="label">EV net</span><span class="val" style="color:' + ec + ';">' + str(round(c["ev"] * 100, 2)) + '%</span></div>'
    if c.get("ajustement_forensics") and c["ajustement_forensics"] != 0:
        signe = "+" if c["ajustement_forensics"] > 0 else ""
        col_aj = "#4ade80" if c["ajustement_forensics"] > 0 else "#ef4444"
        out += '<div class="ligne"><span class="label">Ajust. Forensic</span><span class="val" style="color:' + col_aj + ';">' + signe + str(c["ajustement_forensics"]) + '</span></div>'
    if c.get("ajustement_stacking") and c["ajustement_stacking"] != 0:
        signe = "+" if c["ajustement_stacking"] > 0 else ""
        col_aj = "#4ade80" if c["ajustement_stacking"] > 0 else "#ef4444"
        out += '<div class="ligne"><span class="label">Ajust. Stacking</span><span class="val" style="color:' + col_aj + ';">' + signe + str(c["ajustement_stacking"]) + '</span></div>'
    if c.get("ajustement_consistency") and c["ajustement_consistency"] != 0:
        signe = "+" if c["ajustement_consistency"] > 0 else ""
        col_aj = "#4ade80" if c["ajustement_consistency"] > 0 else "#ef4444"
        out += '<div class="ligne"><span class="label">Ajust. Cross-Market</span><span class="val" style="color:' + col_aj + ';">' + signe + str(c["ajustement_consistency"]) + '</span></div>'
    out += '<div class="ligne"><span class="label">Fiabilite</span><span class="val">' + str(c["fiabilite"]) + '</span></div>'
    out += '<div class="ligne"><span class="label">Filtres</span><span class="val">' + st + '</span></div>'
    out += rh
    out += '</div>'
    return out


def bloc_forensics(f):
    if not f or not f.get("disponible"):
        return '<div class="box" style="border:2px solid #64748b;"><h2 style="color:#64748b;">🔎 MARKET FORENSICS</h2><p style="color:#666;font-size:13px;">Donnees insuffisantes.</p></div>'
    m = f["mouvements"]
    sh = f["sharpe_signal"]
    html = '<div class="box" style="border:2px solid #0ea5e9;background:#0a1620;">'
    html += '<h2 style="color:#0ea5e9;">🔎 MARKET FORENSICS</h2>'
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
        html += '<div class="ligne"><span class="label">' + k + ' : ' + str(mo["open"]) + ' -> ' + str(mo["curr"]) + '</span><span class="val" style="color:' + col + ';">' + str(mo["delta_pct"]) + '%</span></div>'
    html += '<div class="ligne"><span class="label">Pattern</span><span class="val">' + f["pattern"]["pattern"] + '</span></div>'
    html += '<div class="ligne"><span class="label">CLV pred.</span><span class="val">' + str(round(f["clv"]["clv_predictif"] * 100, 2)) + '%</span></div>'
    html += '<div class="ligne"><span class="label">Sharp Money</span><span class="val">' + str(f["sharp_money"]["score"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Efficience</span><span class="val">' + str(f["efficience"]["efficience"]) + '</span></div>'
    html += '<div class="box" style="margin-top:10px;background:#0a0a14;border-color:' + sh["couleur"] + ';">'
    html += '<div class="ligne"><span class="label" style="color:' + sh["couleur"] + ';">⭐ SHARPE SIGNAL</span><span class="val" style="color:' + sh["couleur"] + ';font-size:16px;">' + str(sh["sharpe_signal"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">' + sh["label"] + '</span><span class="val" style="font-size:12px;color:#ccc;">' + sh["interpretation"] + '</span></div>'
    html += '</div></div>'
    return html


def bloc_stacking(s):
    if not s or not s.get("disponible"):
        return '<div class="box" style="border:2px solid #64748b;"><h2 style="color:#64748b;">🧠 STACKING</h2><p style="color:#666;font-size:13px;">Non disponible.</p></div>'
    p = s["poids"]
    cons = s["consensus_global"]
    pcs = s["pcs"]
    if cons >= 0.90:
        col = "#4ade80"
    elif cons >= 0.75:
        col = "#22c55e"
    elif cons >= 0.50:
        col = "#eab308"
    else:
        col = "#ef4444"
    html = '<div class="box" style="border:2px solid #a855f7;background:#1a0f2a;">'
    html += '<h2 style="color:#a855f7;">🧠 META-ENSEMBLE STACKING</h2>'
    html += '<div class="ligne"><span class="label">Consensus</span><span class="val" style="color:' + col + ';">' + str(cons) + '</span></div>'
    html += '<div class="ligne"><span class="label">Ecart-type</span><span class="val">' + str(s["ecart_type_global"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Poids Poisson</span><span class="val">' + str(p["w_poisson"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Poids DC</span><span class="val">' + str(p["w_dc"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Poids MC</span><span class="val">' + str(p["w_mc"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Poids Bayes</span><span class="val">' + str(p["w_bayes"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">P(1)</span><span class="val">' + str(round(s["p1_final"] * 100, 2)) + '%</span></div>'
    html += '<div class="ligne"><span class="label">P(X)</span><span class="val">' + str(round(s["px_final"] * 100, 2)) + '%</span></div>'
    html += '<div class="ligne"><span class="label">P(2)</span><span class="val">' + str(round(s["p2_final"] * 100, 2)) + '%</span></div>'
    html += '<div class="ligne"><span class="label">PCS</span><span class="val">' + str(pcs["pcs"]) + ' (' + pcs["label"] + ')</span></div>'
    html += '</div>'
    return html


def bloc_cross(cm):
    if not cm or not cm.get("disponible"):
        return '<div class="box" style="border:2px solid #64748b;"><h2 style="color:#64748b;">🔀 CROSS-MARKET</h2><p style="color:#666;font-size:13px;">Non disponible.</p></div>'
    cons = cm["consistency"]
    if cons["consistency"] >= 0.85:
        col = "#4ade80"
    elif cons["consistency"] >= 0.70:
        col = "#22c55e"
    elif cons["consistency"] >= 0.50:
        col = "#eab308"
    else:
        col = "#ef4444"
    html = '<div class="box" style="border:2px solid #14b8a6;background:#0a1a1a;">'
    html += '<h2 style="color:#14b8a6;">🔀 CROSS-MARKET</h2>'
    html += '<div class="ligne"><span class="label">Incoherences</span><span class="val">' + str(cm["nb_incoherences"]) + '</span></div>'
    for inc in cm["incoherences"]:
        niv = inc.get("niveau", "?")
        if niv == "MAJEURE":
            ci = "#ef4444"
        elif niv == "MODEREE":
            ci = "#eab308"
        else:
            ci = "#4ade80"
        html += '<div class="ligne"><span class="label">' + inc.get("marche", "?") + '</span><span class="val" style="color:' + ci + ';">' + str(round(inc["ecart_relatif"] * 100, 1)) + '% (' + niv + ')</span></div>'
    html += '<div class="ligne"><span class="label">Consistency</span><span class="val" style="color:' + col + ';">' + str(cons["consistency"]) + ' (' + cons["label"] + ')</span></div>'
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



@app.post("/analyser", response_class=HTMLResponse)
async def analyser(request: Request):
    form = await request.form()

    competition = form.get("competition", "")
    eq_dom = form.get("equipe_domicile", "")
    eq_ext = form.get("equipe_exterieur", "")
    date_match = form.get("date_match", "")
    sport = form.get("sport", "football")
    ligue = form.get("ligue", "nba")

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

    ht1 = ff(form, "ht_1")
    htx = ff(form, "ht_x")
    ht2 = ff(form, "ht_2")
    h21 = ff(form, "h2_1")
    h2x = ff(form, "h2_x")
    h22 = ff(form, "h2_2")
    c_ht = [ht1, htx, ht2] if (ht1 and ht2) else None
    c_2h = [h21, h2x, h22] if (h21 and h22) else None

    meteo = form.get("meteo", "normale")
    enjeu = form.get("enjeu", "normal")
    bd = form.get("blessures_domicile") is not None
    be = form.get("blessures_exterieur") is not None
    fd = form.get("fatigue_domicile") is not None
    fe = form.get("fatigue_exterieur") is not None
    pd = fi(form, "pos_dom")
    pe = fi(form, "pos_ext")
    te = fi(form, "total_equipes")

    pace_dom = fopt(form, "pace_dom")
    offrtg_dom = fopt(form, "offrtg_dom")
    defrtg_dom = fopt(form, "defrtg_dom")
    pace_ext = fopt(form, "pace_ext")
    offrtg_ext = fopt(form, "offrtg_ext")
    defrtg_ext = fopt(form, "defrtg_ext")

    if sport == "basketball":
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
            bd, be, fd, fe, pd, pe, te,
            ml_ft, ml_1h, ml_2h, total_1h, total_2h,
            ligue,
            pace_dom, offrtg_dom, defrtg_dom,
            pace_ext, offrtg_ext, defrtg_ext,
            q1, q2, q3, q4,
            o1, o2, c1, c2
        )
    else:
        r = analyser_match_football(
            home_ctx, home_glob, away_ctx, away_glob,
            o1, ox, o2, c1, cx, c2,
            meteo, enjeu, bd, be, fd, fe, h2h, hcp_lignes, ou_lignes,
            pd, pe, te, c_ht, c_2h,
            ligue
        )

    analyse_dict = {
        "date_analyse": datetime.now().isoformat(timespec="seconds"),
        "sport": sport,
        "competition": competition,
        "equipe_domicile": eq_dom,
        "equipe_exterieur": eq_ext,
        "date_match": date_match,
        "resultats": r,
    }
    analyse_json = json.dumps(analyse_dict, ensure_ascii=False).replace("</", "<\\/")

    html = '<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>QFTE</title><style>' + STYLE + '</style></head><body>'
    html += '<div style="text-align:center;margin-bottom:12px;"><a href="/historique" class="btn btn-secondary">Historique</a> <a href="/" class="btn btn-secondary">Accueil</a></div>'
    html += '<h1>QFTE V23.0 - Analyse</h1>'
    html += '<p style="text-align:center;color:#999;font-size:12px;">' + eq_dom + ' vs ' + eq_ext + ' - ' + competition + ' (' + sport + ')</p>'


if r["pari_retenu"]:
    p = r["pari_retenu"]
    html += '<div class="box" style="border:2px solid #4ade80;">'
    html += '<h2 style="color:#4ade80;">PARI RETENU (' + p.get("marche", p.get("type", "?")) + ')</h2>'
    html += '<div class="ligne"><span class="label">Selection</span><span class="val">' + p["selection"] + '</span></div>'
    html += '<div class="ligne"><span class="label">Cote</span><span class="val">' + str(p["cote"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Probabilite</span><span class="val">' + str(round(p["p"] * 100, 2)) + '%</span></div>'
    html += '<div class="ligne"><span class="label">EV net</span><span class="val" style="color:#4ade80;">' + str(round(p["ev"] * 100, 2)) + '%</span></div>'
    if p.get("fiabilite_origine") is not None:
        html += '<div class="ligne"><span class="label">Fiab. origine</span><span class="val">' + str(p["fiabilite_origine"]) + '</span></div>'
    if p.get("ajustement_forensics") and p["ajustement_forensics"] != 0:
        s = "+" if p["ajustement_forensics"] > 0 else ""
        c = "#4ade80" if p["ajustement_forensics"] > 0 else "#ef4444"
        html += '<div class="ligne"><span class="label">Ajust. Forensics</span><span class="val" style="color:' + c + ';">' + s + str(p["ajustement_forensics"]) + '</span></div>'
    if p.get("ajustement_stacking") and p["ajustement_stacking"] != 0:
        s = "+" if p["ajustement_stacking"] > 0 else ""
        c = "#4ade80" if p["ajustement_stacking"] > 0 else "#ef4444"
        html += '<div class="ligne"><span class="label">Ajust. Stacking</span><span class="val" style="color:' + c + ';">' + s + str(p["ajustement_stacking"]) + '</span></div>'
    if p.get("ajustement_consistency") and p["ajustement_consistency"] != 0:
        s = "+" if p["ajustement_consistency"] > 0 else ""
        c = "#4ade80" if p["ajustement_consistency"] > 0 else "#ef4444"
        html += '<div class="ligne"><span class="label">Ajust. Cross-Market</span><span class="val" style="color:' + c + ';">' + s + str(p["ajustement_consistency"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Fiabilite finale</span><span class="val">' + str(p["fiabilite"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Niveau</span><span class="val">' + p["niveau"] + '</span></div>'
    html += '<div class="ligne"><span class="label">Decision</span><span class="val">' + p["decision"] + '</span></div>'
    if p.get("stake_origine"):
        html += '<div class="ligne"><span class="label">Stake origine</span><span class="val">' + str(p["stake_origine"]) + '%</span></div>'
    html += '<div class="ligne"><span class="label">Stake final</span><span class="val">' + str(p["stake"]) + '% bankroll</span></div>'
    html += '</div>'
else:
    html += '<div class="box" style="border:2px solid #ef4444;"><h2 style="color:#ef4444;">AUCUN PARI RETENU</h2><p style="color:#ccc;font-size:13px;">Aucune selection ne respecte les filtres V23.0.</p></div>'

if r.get("cross_market"):
    html += bloc_cross(r["cross_market"])
if r.get("stacking"):
    html += bloc_stacking(r["stacking"])
if r.get("forensics"):
    html += bloc_forensics(r["forensics"])

if sport == "basketball" and r.get("signature"):
    sig = r["signature"]
    html += '<div class="box" style="border:2px solid #a855f7;background:#1a0f2a;">'
    html += '<h2 style="color:#a855f7;">🔬 TRUE SIGMA</h2>'
    html += '<div class="ligne"><span class="label">Sigma ligue</span><span class="val">' + str(sig["sigma_ligue"]) + '</span></div>'
    if sig["sigma_dom"] is not None:
        html += '<div class="ligne"><span class="label">Sigma reel dom.</span><span class="val">' + str(sig["sigma_dom"]) + '</span></div>'
    if sig["sigma_ext"] is not None:
        html += '<div class="ligne"><span class="label">Sigma reel ext.</span><span class="val">' + str(sig["sigma_ext"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Sigma final</span><span class="val" style="color:#a855f7;">' + str(sig["sigma_final"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Consistance dom.</span><span class="val">' + str(sig["consistance_dom"]) + ' (' + sig["label_consistance_dom"] + ')</span></div>'
    html += '<div class="ligne"><span class="label">Consistance ext.</span><span class="val">' + str(sig["consistance_ext"]) + ' (' + sig["label_consistance_ext"] + ')</span></div>'
    html += '<div class="ligne"><span class="label">Alerte volatilite</span><span class="val">' + sig["niveau_alerte"] + '</span></div>'
    html += '<div class="ligne"><span class="label">Multiplicateur stake</span><span class="val">x' + str(sig["multiplicateur_stake"]) + '</span></div>'
    html += '</div>'

if sport == "football" and r.get("signature"):
    sigf = r["signature"]
    html += '<div class="box" style="border:2px solid #f59e0b;background:#1a150a;">'
    html += '<h2 style="color:#f59e0b;">🔬 SIGNATURE FOOT</h2>'
    html += '<div class="ligne"><span class="label">Prior ligue</span><span class="val">' + str(sigf["prior_ligue"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Lambda dom (brut)</span><span class="val">' + str(sigf["lambda_home_brut"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Lambda dom (bayesien)</span><span class="val" style="color:#f59e0b;">' + str(sigf["lambda_home_bayesien"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Lambda ext (brut)</span><span class="val">' + str(sigf["lambda_away_brut"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Lambda ext (bayesien)</span><span class="val" style="color:#f59e0b;">' + str(sigf["lambda_away_bayesien"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">BTTS Oui (DC)</span><span class="val">' + str(round(sigf["p_btts_oui_dc"] * 100, 2)) + '%</span></div>'
    html += '</div>'


if sport == "basketball":
    html += '<div class="box"><h2>Points attendus</h2>'
    html += '<div class="ligne"><span class="label">' + eq_dom + '</span><span class="val">' + str(r["mu_home"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">' + eq_ext + '</span><span class="val">' + str(r["mu_away"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">Total FT</span><span class="val">' + str(r["mu_total"]) + '</span></div>'
    html += '</div>'

    html += '<h2 style="text-align:left;">Detail - Moneyline</h2>'
    for c in r["ml_candidats"]:
        html += bloc_candidat(c)
    html += '<h2 style="text-align:left;">Detail - Spread</h2>'
    for c in r["spread_candidats"]:
        html += bloc_candidat(c)
    html += '<h2 style="text-align:left;">Detail - Total FT</h2>'
    for c in r["total_ft_candidats"]:
        html += bloc_candidat(c)

else:
    html += '<div class="box"><h2>Buts attendus</h2>'
    html += '<div class="ligne"><span class="label">' + eq_dom + '</span><span class="val">' + str(r["lambda_home"]) + '</span></div>'
    html += '<div class="ligne"><span class="label">' + eq_ext + '</span><span class="val">' + str(r["lambda_away"]) + '</span></div>'
    html += '</div>'

    html += '<div class="box"><h2>Probabilites 1X2</h2>'
    html += '<div class="ligne"><span class="label">1</span><span class="val">' + str(round(r["p1"] * 100, 2)) + '%</span></div>'
    html += '<div class="ligne"><span class="label">X</span><span class="val">' + str(round(r["px"] * 100, 2)) + '%</span></div>'
    html += '<div class="ligne"><span class="label">2</span><span class="val">' + str(round(r["p2"] * 100, 2)) + '%</span></div>'
    html += '</div>'

    html += '<h2 style="text-align:left;">Detail - 1X2</h2>'
    for c in r["candidats"]:
        html += bloc_candidat(c)
    html += '<h2 style="text-align:left;">Detail - Handicap</h2>'
    for h in r["handicap_resultats"]:
        html += bloc_candidat(h)
    html += '<h2 style="text-align:left;">Detail - Over / Under</h2>'
    for o in r["ou_resultats"]:
        html += bloc_candidat(o)


    html += '<div style="text-align:center;margin:24px 0;">'
    html += '<button class="btn" onclick="sauvegarder()">Sauvegarder</button> '
    html += '<a href="/" class="btn btn-secondary">Nouvelle analyse</a>'
    html += '</div>'

    html += '<script>const ANALYSE = ' + analyse_json + ';'
    html += 'function sauvegarder(){try{let hist=JSON.parse(localStorage.getItem("qfte_analyses")||"[]");'
    html += 'hist=hist.filter(a=>!(a.equipe_domicile===ANALYSE.equipe_domicile&&a.equipe_exterieur===ANALYSE.equipe_exterieur&&a.date_match===ANALYSE.date_match));'
    html += 'hist.unshift(ANALYSE);if(hist.length>200)hist=hist.slice(0,200);'
    html += 'localStorage.setItem("qfte_analyses",JSON.stringify(hist));alert("Analyse sauvegardee !");'
    html += '}catch(e){alert("Erreur : "+e.message);}}</script>'

    html += '</body></html>'
        return HTMLResponse(content=html)


@app.get("/historique", response_class=HTMLResponse)
async def historique(request: Request):
    h = '<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Historique QFTE</title><style>' + STYLE + '</style></head><body>'
    h += '<h1>Historique QFTE V23.0</h1>'
    h += '<div style="text-align:center;margin-bottom:16px;">'
    h += '<a href="/" class="btn btn-secondary">Accueil</a> '
    h += '<button class="btn" onclick="exporter()">Exporter JSON</button> '
    h += '<button class="btn btn-danger" onclick="vider()">Vider</button>'
    h += '</div>'
    h += '<div id="compteur" style="text-align:center;color:#999;font-size:13px;margin-bottom:16px;"></div>'
    h += '<div id="liste"></div>'
    h += '<script>'
    h += 'function charger(){let h=[];try{h=JSON.parse(localStorage.getItem("qfte_analyses")||"[]");}catch(e){}return h;}'
    h += 'function afficher(){const hist=charger();const liste=document.getElementById("liste");const c=document.getElementById("compteur");'
    h += 'if(hist.length===0){c.textContent="";liste.innerHTML="<div class=empty>Aucune analyse.</div>";return;}'
    h += 'c.textContent=hist.length+" analyse(s)";let html="";'
    h += 'hist.forEach((a,i)=>{const r=a.resultats||{};const p=r.pari_retenu;'
    h += 'let badge="<span class=\\"badge badge-avoid\\">AUCUN</span>";let resume="Aucun pari retenu";'
    h += 'if(p){if(p.niveau==="ELITE")badge="<span class=\\"badge badge-elite\\">ELITE</span>";'
    h += 'else if(p.niveau==="PREMIUM")badge="<span class=\\"badge badge-premium\\">PREMIUM</span>";'
    h += 'else if(p.niveau==="GOOD")badge="<span class=\\"badge badge-good\\">GOOD</span>";'
    h += 'else badge="<span class=\\"badge badge-avoid\\">"+p.niveau+"</span>";'
    h += 'resume=p.selection+" @ "+p.cote+" (EV "+(p.ev*100).toFixed(2)+"%)";}'
    h += 'html+="<div class=box>";'
    h += 'html+="<div class=ligne><span class=label>#"+(i+1)+" - "+(a.date_analyse||"")+"</span><span class=val>"+badge+"</span></div>";'
    h += 'html+="<div class=ligne><span class=label>Match</span><span class=val>"+(a.equipe_domicile||"")+" vs "+(a.equipe_exterieur||"")+"</span></div>";'
    h += 'html+="<div class=ligne><span class=label>Sport</span><span class=val>"+(a.sport||"")+"</span></div>";'
    h += 'html+="<div class=ligne><span class=label>Resultat</span><span class=val>"+resume+"</span></div>";'
    h += 'html+="</div>";});liste.innerHTML=html;}'
    h += 'function exporter(){const hist=charger();if(hist.length===0){alert("Rien a exporter.");return;}'
    h += 'const blob=new Blob([JSON.stringify(hist,null,2)],{type:"application/json"});'
    h += 'const url=URL.createObjectURL(blob);const a=document.createElement("a");'
    h += 'a.href=url;a.download="qfte_historique_"+new Date().toISOString().slice(0,10)+".json";'
    h += 'document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(url);}'
    h += 'function vider(){if(!confirm("Vider tout l historique ?"))return;localStorage.removeItem("qfte_analyses");afficher();}'
    h += 'afficher();</script></body></html>'
    return HTMLResponse(content=h)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "V23.0"}
