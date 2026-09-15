import re
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from qfte_engine.mvp import analyser_match_football

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")


# =========================================================
# PARSER — Convertit "3-1 (1-0), 2-2" en liste de matchs
# =========================================================
def parser_matchs(texte):
    """
    Parse une chaîne comme :
    "3-1 (1-0), 2-2, 4-0 (2-0)"
    et retourne une liste de dict :
    [{'bp':3, 'bc':1, 'ht_bp':1, 'ht_bc':0}, ...]
    """
    resultats = []
    if not texte:
        return resultats

    # Séparer par virgules
    morceaux = [m.strip() for m in texte.split(",") if m.strip()]

    for m in morceaux:
        # Format avec HT : 3-1 (1-0)
        match_ht = re.match(r"^(\d+)\s*-\s*(\d+)\s*\(\s*(\d+)\s*-\s*(\d+)\s*\)$", m)
        # Format sans HT : 3-1
        match_simple = re.match(r"^(\d+)\s*-\s*(\d+)$", m)

        if match_ht:
            resultats.append({
                "bp": int(match_ht.group(1)),
                "bc": int(match_ht.group(2)),
                "ht_bp": int(match_ht.group(3)),
                "ht_bc": int(match_ht.group(4)),
            })
        elif match_simple:
            resultats.append({
                "bp": int(match_simple.group(1)),
                "bc": int(match_simple.group(2)),
                "ht_bp": None,
                "ht_bc": None,
            })
        # Sinon : on ignore le morceau invalide

    return resultats


def moyenne(valeurs):
    """Moyenne en ignorant les valeurs None ou vides."""
    v = [x for x in valeurs if x is not None and x > 0]
    if not v:
        return 0.0
    return sum(v) / len(v)


def ffloat(form, key, default=0.0):
    v = form.get(key, "")
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "titre": "QFTE V23.0 – Bot d'analyse"}
    )


@app.post("/analyser", response_class=HTMLResponse)
async def analyser(request: Request):
    form = await request.form()

    sport = form.get("sport", "football")
    competition = form.get("competition", "")
    equipe_domicile = form.get("equipe_domicile", "")
    equipe_exterieur = form.get("equipe_exterieur", "")
    date_match = form.get("date_match", "")

    # Parsing des 4 sections compactes
    home_contextuel = parser_matchs(form.get("home_contextuel", ""))
    home_global = parser_matchs(form.get("home_global", ""))
    away_contextuel = parser_matchs(form.get("away_contextuel", ""))
    away_global = parser_matchs(form.get("away_global", ""))

    # Pour l'instant, on utilise UNIQUEMENT le contexte (comme avant)
    home_bp_moy = moyenne([m["bp"] for m in home_contextuel])
    home_bc_moy = moyenne([m["bc"] for m in home_contextuel])
    away_bp_moy = moyenne([m["bp"] for m in away_contextuel])
    away_bc_moy = moyenne([m["bc"] for m in away_contextuel])

    # Cotes
    open_1 = ffloat(form, "open_1")
    open_x = ffloat(form, "open_x")
    open_2 = ffloat(form, "open_2")
    curr_1 = ffloat(form, "curr_1")
    curr_x = ffloat(form, "curr_x")
    curr_2 = ffloat(form, "curr_2")

    meteo = form.get("meteo", "normale")
    enjeu = form.get("enjeu", "normal")
    blessures_domicile = form.get("blessures_domicile") is not None
    blessures_exterieur = form.get("blessures_exterieur") is not None

    # Appel moteur
    r = analyser_match_football(
        home_bp_moy, home_bc_moy, away_bp_moy, away_bc_moy,
        open_1, open_x, open_2,
        curr_1, curr_x, curr_2
    )

    # Bloc décision
    if r["pari_retenu"]:
        p = r["pari_retenu"]
        decision_html = f"""
        <div class="box" style="border:2px solid #4ade80;">
            <h2 style="color:#4ade80;">🟢 PARI RETENU</h2>
            <div class="ligne"><span class="label">Sélection</span><span class="val">{p['selection']}</span></div>
            <div class="ligne"><span class="label">Cote</span><span class="val">{p['cote']}</span></div>
            <div class="ligne"><span class="label">Probabilité</span><span class="val">{p['p']*100:.2f}%</span></div>
            <div class="ligne"><span class="label">EV net</span><span class="val" style="color:#4ade80;">{p['ev']*100:+.2f}%</span></div>
            <div class="ligne"><span class="label">Fiabilité</span><span class="val">{p['fiabilite']}</span></div>
            <div class="ligne"><span class="label">Niveau</span><span class="val">{p['niveau']}</span></div>
            <div class="ligne"><span class="label">Décision</span><span class="val">{p['decision']}</span></div>
            <div class="ligne"><span class="label">💰 Stake</span><span class="val">{p['stake']}% bankroll</span></div>
        </div>
        """
    else:
        decision_html = """
        <div class="box" style="border:2px solid #ef4444;">
            <h2 style="color:#ef4444;">🔴 AUCUN PARI RETENU</h2>
            <p style="color:#ccc;font-size:13px;">Aucune sélection ne respecte les filtres V23.0.</p>
        </div>
        """

    candidats_html = ""
    for c in r["candidats"]:
        ev_color = "#4ade80" if c["ev"] >= 0 else "#ef4444"
        if c["passe_filtres"]:
            statut = '<span style="color:#4ade80;font-weight:bold;">✅ PASSE</span>'
            raisons_html = ""
        else:
            statut = '<span style="color:#ef4444;font-weight:bold;">❌ REJETÉ</span>'
            raisons_html = "".join([f'<div class="ligne"><span class="label" style="color:#ef4444;font-size:12px;">→ {x}</span></div>' for x in c["raisons_rejet"]])
        candidats_html += f"""
        <div class="box">
            <div class="ligne"><span class="label">Sélection</span><span class="val">{c['selection']}</span></div>
            <div class="ligne"><span class="label">Probabilité</span><span class="val">{c['p']*100:.2f}%</span></div>
            <div class="ligne"><span class="label">Cote</span><span class="val">{c['cote']}</span></div>
            <div class="ligne"><span class="label">EV net</span><span class="val" style="color:{ev_color};">{c['ev']*100:+.2f}%</span></div>
            <div class="ligne"><span class="label">Fiabilité</span><span class="val">{c['fiabilite']}</span></div>
            <div class="ligne"><span class="label">Filtres</span><span class="val">{statut}</span></div>
            {raisons_html}
        </div>
        """

    scores_html = ""
    for s in r["top_3_scores"]:
        scores_html += f'<div class="ligne"><span class="label">#{s["rank"]}</span><span class="val">{s["score"]} — {s["probability"]*100:.2f}%</span></div>'

    # Info parsing (debug utile)
    parsing_info = f"""
    <p style="text-align:center;color:#666;font-size:11px;">
    Matchs parsés : Dom. contextuel={len(home_contextuel)} | Dom. global={len(home_global)} | Ext. contextuel={len(away_contextuel)} | Ext. global={len(away_global)}
    </p>
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
            h2 {{ color: #ffcc00; font-size: 15px; margin-top: 10px; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 6px; }}
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
        <p style="text-align:center;color:#666;font-size:11px;">Météo: {meteo} | Enjeu: {enjeu} | Blessures dom: {'Oui' if blessures_domicile else 'Non'} | Blessures ext: {'Oui' if blessures_exterieur else 'Non'}</p>
        {parsing_info}

        {decision_html}

        <div class="box">
            <h2>⚽ Buts attendus (λ)</h2>
            <div class="ligne"><span class="label">{equipe_domicile}</span><span class="val">{r['lambda_home']}</span></div>
            <div class="ligne"><span class="label">{equipe_exterieur}</span><span class="val">{r['lambda_away']}</span></div>
        </div>

        <div class="box">
            <h2>🎯 Probabilités 1X2</h2>
            <div class="ligne"><span class="label">1 (Domicile)</span><span class="val">{r['p1']*100:.2f}%</span></div>
            <div class="ligne"><span class="label">X (Nul)</span><span class="val">{r['px']*100:.2f}%</span></div>
            <div class="ligne"><span class="label">2 (Extérieur)</span><span class="val">{r['p2']*100:.2f}%</span></div>
        </div>

        <div class="box">
            <h2>🎲 Top 3 scores probables</h2>
            {scores_html}
        </div>

        <h2 style="text-align:left;">📋 Détail des candidats (filtres V23.0)</h2>
        {candidats_html}

        <p style="text-align:center;"><a href="/">← Nouvelle analyse</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "V23.0"}
