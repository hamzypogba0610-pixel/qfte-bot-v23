import json
import re
from datetime import datetime
from fastapi import FastAPI, Request, Form
from qfte_engine.mvp import analyser_match_football


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
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")


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

    html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>QFTE</title></head><body style="background:#0f0f1a;color:#eee;padding:20px;font-family:Arial;">'
    html += '<h1 style="color:#ffcc00;">Analyse Football</h1>'
    html += '<p>' + eq_dom + ' vs ' + eq_ext + ' (' + ligue + ')</p>'

    p = r.get("pari_retenu")
    if p:
        html += '<h2 style="color:#4ade80;">PARI RETENU</h2>'
        html += '<p>Selection : ' + p["selection"] + '</p>'
        html += '<p>Cote : ' + str(p["cote"]) + '</p>'
        html += '<p>Probabilite : ' + str(round(p["p"] * 100, 2)) + '%</p>'
        html += '<p>EV : ' + str(round(p["ev"] * 100, 2)) + '%</p>'
        html += '<p>Fiabilite : ' + str(p["fiabilite"]) + '</p>'
    else:
        html += '<h2 style="color:#ef4444;">AUCUN PARI RETENU</h2>'

    html += '<h2>Probabilites 1X2</h2>'
    html += '<p>P(1) : ' + str(round(r["p1"] * 100, 2)) + '%</p>'
    html += '<p>P(X) : ' + str(round(r["px"] * 100, 2)) + '%</p>'
    html += '<p>P(2) : ' + str(round(r["p2"] * 100, 2)) + '%</p>'

    html += '<p><a href="/football" style="color:#ffcc00;">Retour</a></p>'
    html += '</body></html>'
    return HTMLResponse(content=html)

else:
    html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Basket</title></head><body style="background:#0f0f1a;color:#eee;padding:20px;font-family:Arial;">'
    html += '<h1 style="color:#ffcc00;">Basketball (moteur a venir)</h1>'
    html += '<p>Sport : ' + sport + '</p>'
    html += '<p>Competition : ' + competition + '</p>'
    html += '<p><a href="/" style="color:#ffcc00;">Retour</a></p>'
    html += '</body></html>'
    return HTMLResponse(content=html)
    return HTMLResponse(content=html)
