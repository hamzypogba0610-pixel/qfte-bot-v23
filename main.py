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

# -----------------------------
# Fonctions utilitaires
# -----------------------------
# >>> Toutes tes fonctions parse_matchs, parse_hcp, parse_ou, parse_ml, parse_total_mt, parse_quart, ff, fi, bloc_candidat <<<
# (placées ici, au début du fichier, sans indentation parasite)

# -----------------------------
# Bloc visuel
# -----------------------------
# >>> Ton bloc_visuel complet ici <<<

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
        # >>> Ton bloc football complet (partie 3) <<<
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
        # >>> Construction HTML football (inchangée) <<<
        return HTMLResponse(content=html)

    else:
        # >>> Ton bloc basketball complet (partie 4) <<<
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
        # >>> Construction HTML basket (inchangée) <<<
        return HTMLResponse(content=html)

# -----------------------------
# Historique
# -----------------------------
@app.get("/historique", response_class=HTMLResponse)
async def historique(request: Request):
    # >>> Ton bloc historique complet (partie 4) <<<
    return HTMLResponse(content=h)
