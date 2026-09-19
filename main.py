import json
import re
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from qfte_engine.mvp import analyser_match_football
from qfte_engine.basket import analyser_match_basket

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")

# -----------------------------
# Fonctions utilitaires
# -----------------------------
# (parse_matchs, parse_hcp, parse_ou, parse_ml, parse_total_mt, parse_quart, ff, fi, bloc_candidat)
# >>> Ton code utilitaire inchangé ici <<<

# -----------------------------
# Bloc visuel
# -----------------------------
# >>> Ton code bloc_visuel inchangé ici <<<

# -----------------------------
# Routes principales
# -----------------------------
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
        return HTMLResponse(content=f"<pre style='background:#000;color:#4ade80;padding:20px;font-size:12px;white-space:pre-wrap;'>ERREUR :\n\n{err}</pre>")

# -----------------------------
# Fonction interne d'analyse
# -----------------------------
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
        # >>> Bloc football inchangé (ton code partie 3) <<<
        ...
        return HTMLResponse(content=html)

    else:
        # >>> Bloc basketball inchangé (ton code partie 4) <<<
        ...
        return HTMLResponse(content=html)

# -----------------------------
# Historique
# -----------------------------
@app.get("/historique", response_class=HTMLResponse)
async def historique(request: Request):
    # >>> Ton code historique inchangé (partie 4) <<<
    return HTMLResponse(content=h)
