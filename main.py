from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")


# =============================================================
# ROUTE 1 : Page d'accueil (formulaire)
# =============================================================
@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "titre": "QFTE V23.0 – Bot d'analyse"}
    )


# =============================================================
# ROUTE 2 : Analyse du match (reçoit le formulaire)
# =============================================================
@app.post("/analyser", response_class=HTMLResponse)
async def analyser(
    request: Request,
    sport: str = Form(...),
    competition: str = Form(...),
    equipe_domicile: str = Form(...),
    equipe_exterieur: str = Form(...),
    date_match: str = Form(...),
    # 5 derniers à domicile
    home_adv_1: str = Form(""),
    home_bp_1: int = Form(0),
    home_bc_1: int = Form(0),
    home_adv_2: str = Form(""),
    home_bp_2: int = Form(0),
    home_bc_2: int = Form(0),
    home_adv_3: str = Form(""),
    home_bp_3: int = Form(0),
    home_bc_3: int = Form(0),
    home_adv_4: str = Form(""),
    home_bp_4: int = Form(0),
    home_bc_4: int = Form(0),
    home_adv_5: str = Form(""),
    home_bp_5: int = Form(0),
    home_bc_5: int = Form(0),
    # 5 derniers à l'extérieur
    away_adv_1: str = Form(""),
    away_bp_1: int = Form(0),
    away_bc_1: int = Form(0),
    away_adv_2: str = Form(""),
    away_bp_2: int = Form(0),
    away_bc_2: int = Form(0),
    away_adv_3: str = Form(""),
    away_bp_3: int = Form(0),
    away_bc_3: int = Form(0),
    away_adv_4: str = Form(""),
    away_bp_4: int = Form(0),
    away_bc_4: int = Form(0),
    away_adv_5: str = Form(""),
    away_bp_5: int = Form(0),
    away_bc_5: int = Form(0),
    # Cotes
    open_1: float = Form(...),
    open_x: float = Form(0),
    open_2: float = Form(...),
    curr_1: float = Form(...),
    curr_x: float = Form(0),
    curr_2: float = Form(...),
    # Contexte
    meteo: str = Form("normale"),
    enjeu: str = Form("normal"),
    blessures_domicile: str = Form(None),
    blessures_exterieur: str = Form(None),
    notes: str = Form(""),
):
    """
    Reçoit les données du formulaire.
    Pour l'instant : affiche juste un récap (pas de calcul).
    """

    # --- Calculs préliminaires simples (moyennes) ---
    home_bp_total = home_bp_1 + home_bp_2 + home_bp_3 + home_bp_4 + home_bp_5
    home_bc_total = home_bc_1 + home_bc_2 + home_bc_3 + home_bc_4 + home_bc_5
    away_bp_total = away_bp_1 + away_bp_2 + away_bp_3 + away_bp_4 + away_bp_5
    away_bc_total = away_bc_1 + away_bc_2 + away_bc_3 + away_bc_4 + away_bc_5

    # On ne divise que si au moins un score est renseigné
    home_bp_moy = home_bp_total / 5
    home_bc_moy = home_bc_total / 5
    away_bp_moy = away_bp_total / 5
    away_bc_moy = away_bc_total / 5

    # --- Affichage ---
    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Résultats QFTE</title>
        <style>
            body {{
                font-family: -apple-system, Arial, sans-serif;
                background: #0f0f1a;
                color: #eee;
                padding: 16px;
                line-height: 1.5;
            }}
            h1 {{ color: #ffcc00; font-size: 20px; text-align: center; }}
            h2 {{ color: #ffcc00; font-size: 15px; margin-top: 20px; border-bottom: 1px solid #333; padding-bottom: 6px; }}
            .box {{
                background: #14141f;
                border: 1px solid #262636;
                border-radius: 10px;
                padding: 12px;
                margin-bottom: 14px;
            }}
            .ligne {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; }}
            .label {{ color: #999; }}
            .val {{ color: #fff; font-weight: bold; }}
            a {{ color: #ffcc00; text-decoration: none; display: inline-block; margin-top: 20px; }}
            .ok {{ color: #4ade80; }}
        </style>
    </head>
    <body>
        <h1>✅ Données reçues</h1>
        <p style="text-align:center;color:#999;font-size:12px;">Étape 2 validée — le formulaire fonctionne</p>

        <div class="box">
            <h2>📋 Match</h2>
            <div class="ligne"><span class="label">Sport</span><span class="val">{sport}</span></div>
            <div class="ligne"><span class="label">Compétition</span><span class="val">{competition}</span></div>
            <div class="ligne"><span class="label">Domicile</span><span class="val">{equipe_domicile}</span></div>
            <div class="ligne"><span class="label">Extérieur</span><span class="val">{equipe_exterieur}</span></div>
            <div class="ligne"><span class="label">Date</span><span class="val">{date_match}</span></div>
        </div>

        <div class="box">
            <h2>🏠 {equipe_domicile} — à domicile</h2>
            <div class="ligne"><span class="label">Buts marqués / match</span><span class="val">{home_bp_moy:.2f}</span></div>
            <div class="ligne"><span class="label">Buts encaissés / match</span><span class="val">{home_bc_moy:.2f}</span></div>
        </div>

        <div class="box">
            <h2>✈️ {equipe_exterieur} — à l'extérieur</h2>
            <div class="ligne"><span class="label">Buts marqués / match</span><span class="val">{away_bp_moy:.2f}</span></div>
            <div class="ligne"><span class="label">Buts encaissés / match</span><span class="val">{away_bc_moy:.2f}</span></div>
        </div>

        <div class="box">
            <h2>📈 Cotes</h2>
            <div class="ligne"><span class="label">Ouverture 1</span><span class="val">{open_1}</span></div>
            <div class="ligne"><span class="label">Ouverture X</span><span class="val">{open_x if open_x else '—'}</span></div>
            <div class="ligne"><span class="label">Ouverture 2</span><span class="val">{open_2}</span></div>
            <div class="ligne"><span class="label">Actuelle 1</span><span class="val">{curr_1}</span></div>
            <div class="ligne"><span class="label">Actuelle X</span><span class="val">{curr_x if curr_x else '—'}</span></div>
            <div class="ligne"><span class="label">Actuelle 2</span><span class="val">{curr_2}</span></div>
        </div>

        <div class="box">
            <h2>🎚️ Contexte</h2>
            <div class="ligne"><span class="label">Météo</span><span class="val">{meteo}</span></div>
            <div class="ligne"><span class="label">Enjeu</span><span class="val">{enjeu}</span></div>
            <div class="ligne"><span class="label">Blessures domicile</span><span class="val">{'Oui' if blessures_domicile else 'Non'}</span></div>
            <div class="ligne"><span class="label">Blessures extérieur</span><span class="val">{'Oui' if blessures_exterieur else 'Non'}</span></div>
        </div>

        <p style="text-align:center;color:#4ade80;font-weight:bold;">🎯 Le formulaire envoie bien les données !</p>
        <p style="text-align:center;"><a href="/">← Retour au formulaire</a></p>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


# =============================================================
# ROUTE 3 : Health check (utile pour Render)
# =============================================================
@app.get("/health")
async def health():
    return {"status": "ok", "version": "V23.0"}
