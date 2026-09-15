from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from qfte_engine.mvp import analyser_match_football

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "titre": "QFTE V23.0 – Bot d'analyse"}
    )


@app.post("/analyser", response_class=HTMLResponse)
async def analyser(
    request: Request,
    sport: str = Form(...),
    competition: str = Form(...),
    equipe_domicile: str = Form(...),
    equipe_exterieur: str = Form(...),
    date_match: str = Form(...),
    home_adv_1: str = Form(""), home_bp_1: int = Form(0), home_bc_1: int = Form(0),
    home_adv_2: str = Form(""), home_bp_2: int = Form(0), home_bc_2: int = Form(0),
    home_adv_3: str = Form(""), home_bp_3: int = Form(0), home_bc_3: int = Form(0),
    home_adv_4: str = Form(""), home_bp_4: int = Form(0), home_bc_4: int = Form(0),
    home_adv_5: str = Form(""), home_bp_5: int = Form(0), home_bc_5: int = Form(0),
    away_adv_1: str = Form(""), away_bp_1: int = Form(0), away_bc_1: int = Form(0),
    away_adv_2: str = Form(""), away_bp_2: int = Form(0), away_bc_2: int = Form(0),
    away_adv_3: str = Form(""), away_bp_3: int = Form(0), away_bc_3: int = Form(0),
    away_adv_4: str = Form(""), away_bp_4: int = Form(0), away_bc_4: int = Form(0),
    away_adv_5: str = Form(""), away_bp_5: int = Form(0), away_bc_5: int = Form(0),
    open_1: float = Form(...), open_x: float = Form(0), open_2: float = Form(...),
    curr_1: float = Form(...), curr_x: float = Form(0), curr_2: float = Form(...),
    meteo: str = Form("normale"),
    enjeu: str = Form("normal"),
    blessures_domicile: str = Form(None),
    blessures_exterieur: str = Form(None),
    notes: str = Form(""),
):
    # Moyennes buts marqués / encaissés
    home_bp_moy = (home_bp_1 + home_bp_2 + home_bp_3 + home_bp_4 + home_bp_5) / 5.0
    home_bc_moy = (home_bc_1 + home_bc_2 + home_bc_3 + home_bc_4 + home_bc_5) / 5.0
    away_bp_moy = (away_bp_1 + away_bp_2 + away_bp_3 + away_bp_4 + away_bp_5) / 5.0
    away_bc_moy = (away_bc_1 + away_bc_2 + away_bc_3 + away_bc_4 + away_bc_5) / 5.0

    # Appel au moteur (football uniquement pour l'instant)
    resultat = analyser_match_football(
        home_bp_moy, home_bc_moy, away_bp_moy, away_bc_moy,
        open_1, open_x, open_2,
        curr_1, curr_x, curr_2
    )

    # --- Construction des recommandations (HTML) ---
    reco_html = ""
    for i, r in enumerate(resultat["recommandations"], 1):
        ev_pct = r["ev"] * 100
        ev_color = "#4ade80" if ev_pct >= 0 else "#ef4444"
        reco_html += f"""
        <div class="box">
            <div class="ligne"><span class="label">#{i} — Sélection</span><span class="val">{r['selection']}</span></div>
            <div class="ligne"><span class="label">Probabilité</span><span class="val">{r['p']*100:.2f}%</span></div>
            <div class="ligne"><span class="label">Cote</span><span class="val">{r['cote']}</span></div>
            <div class="ligne"><span class="label">EV net</span><span class="val" style="color:{ev_color}">{ev_pct:+.2f}%</span></div>
            <div class="ligne"><span class="label">Fiabilité</span><span class="val">{r['fiabilite']}</span></div>
            <div class="ligne"><span class="label">Niveau</span><span class="val">{r['niveau']}</span></div>
            <div class="ligne"><span class="label">Décision</span><span class="val">{r['decision']}</span></div>
        </div>
        """

    # --- Top 3 scores ---
    scores_html = ""
    for s in resultat["top_3_scores"]:
        scores_html += f"""
        <div class="ligne">
            <span class="label">#{s['rank']}</span>
            <span class="val">{s['score']} — {s['probability']*100:.2f}%</span>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>QFTE — Résultats</title>
        <style>
            body {{ font-family: -apple-system, Arial, sans-serif; background: #0f0f1a; color: #eee; padding: 16px; line-height: 1.5; }}
            h1 {{ color: #ffcc00; font-size: 20px; text-align: center; }}
            h2 {{ color: #ffcc00; font-size: 15px; margin-top: 20px; border-bottom: 1px solid #333; padding-bottom: 6px; }}
            .box {{ background: #14141f; border: 1px solid #262636; border-radius: 10px; padding: 12px; margin-bottom: 14px; }}
            .ligne {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; }}
            .label {{ color: #999; }}
            .val {{ color: #fff; font-weight: bold; }}
            a {{ color: #ffcc00; text-decoration: none; display: inline-block; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <h1>🦁 QFTE V23.0 — Analyse</h1>
        <p style="text-align:center;color:#999;font-size:12px;">{equipe_domicile} vs {equipe_exterieur} — {competition}</p>

        <div class="box">
            <h2>⚽ Buts attendus (λ)</h2>
            <div class="ligne"><span class="label">{equipe_domicile}</span><span class="val">{resultat['lambda_home']}</span></div>
            <div class="ligne"><span class="label">{equipe_exterieur}</span><span class="val">{resultat['lambda_away']}</span></div>
        </div>

        <div class="box">
            <h2>🎯 Probabilités 1X2</h2>
            <div class="ligne"><span class="label">1 (Domicile)</span><span class="val">{resultat['p1']*100:.2f}%</span></div>
            <div class="ligne"><span class="label">X (Nul)</span><span class="val">{resultat['px']*100:.2f}%</span></div>
            <div class="ligne"><span class="label">2 (Extérieur)</span><span class="val">{resultat['p2']*100:.2f}%</span></div>
        </div>

        <div class="box">
            <h2>🎲 Top 3 scores probables</h2>
            {scores_html}
        </div>

        <h2>💰 Recommandations (classées par fiabilité)</h2>
        {reco_html}

        <p style="text-align:center;"><a href="/">← Nouvelle analyse</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "V23.0"}
