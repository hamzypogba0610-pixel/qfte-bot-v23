import json
import re
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from qfte_engine.mvp import analyser_match_football

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")


# =========================================================
# HELPERS
# =========================================================
def parser_matchs(texte):
    resultats = []
    if not texte:
        return resultats
    morceaux = [m.strip() for m in texte.split(",") if m.strip()]
    for m in morceaux:
        match_ht = re.match(r"^(\d+)\s*-\s*(\d+)\s*\(\s*(\d+)\s*-\s*(\d+)\s*\)$", m)
        match_simple = re.match(r"^(\d+)\s*-\s*(\d+)$", m)
        if match_ht:
            resultats.append({
                "bp": int(match_ht.group(1)), "bc": int(match_ht.group(2)),
                "ht_bp": int(match_ht.group(3)), "ht_bc": int(match_ht.group(4)),
            })
        elif match_simple:
            resultats.append({
                "bp": int(match_simple.group(1)), "bc": int(match_simple.group(2)),
                "ht_bp": None, "ht_bc": None,
            })
    return resultats


def parser_handicap(texte):
    """
    Parse : "-0.5/1.90/+0.5/1.95, -1.5/2.10/+1.5/1.75"
    Retourne une liste de dicts.
    """
    resultats = []
    if not texte:
        return resultats
    morceaux = [m.strip() for m in texte.split(",") if m.strip()]
    for m in morceaux:
        # Format : hcp_dom/cote_dom/hcp_ext/cote_ext
        parts = [p.strip() for p in m.split("/") if p.strip()]
        if len(parts) != 4:
            continue
        try:
            hcp_dom = float(parts[0])
            cote_dom = float(parts[1])
            hcp_ext = float(parts[2])
            cote_ext = float(parts[3])
            resultats.append({
                "hcp_dom": hcp_dom,
                "cote_dom": cote_dom,
                "hcp_ext": hcp_ext,
                "cote_ext": cote_ext,
            })
        except (ValueError, TypeError):
            continue
    return resultats


def ffloat(form, key, default=0.0):
    v = form.get(key, "")
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def fint(form, key):
    v = form.get(key, "")
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


STYLE_COMMUN = """
    body { font-family: -apple-system, Arial, sans-serif; background: #0f0f1a; color: #eee; padding: 16px; line-height: 1.5; }
    h1 { color: #ffcc00; font-size: 20px; text-align: center; }
    h2 { color: #ffcc00; font-size: 15px; margin-top: 10px; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 6px; }
    .box { background: #14141f; border: 1px solid #262636; border-radius: 10px; padding: 12px; margin-bottom: 14px; }
    .ligne { display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; }
    .label { color: #999; }
    .val { color: #fff; font-weight: bold; }
    a { color: #ffcc00; text-decoration: none; display: inline-block; margin-top: 20px; }
    .btn { display: inline-block; padding: 12px 16px; background: #ffcc00; color: #000; border: none; border-radius: 8px; font-size: 14px; font-weight: bold; cursor: pointer; margin: 6px 4px 6px 0; text-decoration: none; }
    .btn-secondary { background: #262636; color: #ffcc00; }
    .btn-danger { background: #ef4444; color: #fff; }
"""


@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "titre": "QFTE V23.0"})


@app.post("/analyser", response_class=HTMLResponse)
async def analyser(request: Request):
    form = await request.form()

    competition = form.get("competition", "")
    equipe_domicile = form.get("equipe_domicile", "")
    equipe_exterieur = form.get("equipe_exterieur", "")
    date_match = form.get("date_match", "")
    sport = form.get("sport", "football")

    home_ctx = parser_matchs(form.get("home_contextuel", ""))
    home_glob = parser_matchs(form.get("home_global", ""))
    away_ctx = parser_matchs(form.get("away_contextuel", ""))
    away_glob = parser_matchs(form.get("away_global", ""))
    h2h_matchs = parser_matchs(form.get("h2h", ""))
    handicap_lignes = parser_handicap(form.get("handicap", ""))

    open_1 = ffloat(form, "open_1"); open_x = ffloat(form, "open_x"); open_2 = ffloat(form, "open_2")
    curr_1 = ffloat(form, "curr_1"); curr_x = ffloat(form, "curr_x"); curr_2 = ffloat(form, "curr_2")

    meteo = form.get("meteo", "normale")
    enjeu = form.get("enjeu", "normal")
    blessures_dom = form.get("blessures_domicile") is not None
    blessures_ext = form.get("blessures_exterieur") is not None
    fatigue_dom = form.get("fatigue_domicile") is not None
    fatigue_ext = form.get("fatigue_exterieur") is not None

    pos_dom = fint(form, "pos_dom")
    pos_ext = fint(form, "pos_ext")
    total_equipes = fint(form, "total_equipes")

    r = analyser_match_football(
        home_ctx, home_glob, away_ctx, away_glob,
        open_1, open_x, open_2, curr_1, curr_x, curr_2,
        meteo, enjeu, blessures_dom, blessures_ext,
        fatigue_dom, fatigue_ext, h2h_matchs, handicap_lignes,
        pos_dom, pos_ext, total_equipes
    )

    analyse_complete = {
        "date_analyse": datetime.now().isoformat(timespec="seconds"),
        "sport": sport,
        "competition": competition,
        "equipe_domicile": equipe_domicile,
        "equipe_exterieur": equipe_exterieur,
        "date_match": date_match,
        "resultats": r,
    }
    analyse_json = json.dumps(analyse_complete, ensure_ascii=False).replace("</", "<\\/")

    # Bloc décision
    if r["pari_retenu"]:
        p = r["pari_retenu"]
        type_label = p.get("type", "1X2")
        decision_html = f"""
        <div class="box" style="border:2px solid #4ade80;">
            <h2 style="color:#4ade80;">🟢 PARI RETENU ({type_label})</h2>
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

    # Section handicap
    handicap_html = ""
    if r["handicap_resultats"]:
        for h in r["handicap_resultats"]:
            ev_color = "#4ade80" if h["ev"] >= 0 else "#ef4444"
            if h["passe_filtres"]:
                statut = '<span style="color:#4ade80;font-weight:bold;">✅ PASSE</span>'
                raisons_html = ""
            else:
                statut = '<span style="color:#ef4444;font-weight:bold;">❌ REJETÉ</span>'
                raisons_html = "".join([f'<div class="ligne"><span class="label" style="color:#ef4444;font-size:12px;">→ {x}</span></div>' for x in h["raisons_rejet"]])
            handicap_html += f"""
            <div class="box">
                <div class="ligne"><span class="label">Handicap</span><span class="val">{h['hcp']:+g} ({h['cible']})</span></div>
                <div class="ligne"><span class="label">P(gain) / P(remb.)</span><span class="val">{h['p_gain']*100:.1f}% / {h['p_remb']*100:.1f}%</span></div>
                <div class="ligne"><span class="label">P(effective)</span><span class="val">{h['p']*100:.2f}%</span></div>
                <div class="ligne"><span class="label">Cote</span><span class="val">{h['cote']}</span></div>
                <div class="ligne"><span class="label">EV net</span><span class="val" style="color:{ev_color};">{h['ev']*100:+.2f}%</span></div>
                <div class="ligne"><span class="label">Fiabilité</span><span class="val">{h['fiabilite']}</span></div>
                <div class="ligne"><span class="label">Filtres</span><span class="val">{statut}</span></div>
                {raisons_html}
            </div>
            """
    else:
        handicap_html = '<div class="box"><p style="color:#666;font-size:13px;">Aucun handicap saisi.</p></div>'

    scores_html = ""
    for s in r["top_3_scores"]:
        scores_html += f'<div class="ligne"><span class="label">#{s["rank"]}</span><span class="val">{s["score"]} — {s["probability"]*100:.2f}%</span></div>'

    d = r["details"]
    details_html = f"""
    <div class="box">
        <h2>🔬 Ajustements appliqués</h2>
        <div class="ligne"><span class="label">BP domicile (ctx / glob)</span><span class="val">{d['home_bp_ctx']} / {d['home_bp_glob']}</span></div>
        <div class="ligne"><span class="label">BP extérieur (ctx / glob)</span><span class="val">{d['away_bp_ctx']} / {d['away_bp_glob']}</span></div>
        <div class="ligne"><span class="label">Facteur HT dom.</span><span class="val">{d['f_ht_home']}</span></div>
        <div class="ligne"><span class="label">Facteur HT ext.</span><span class="val">{d['f_ht_away']}</span></div>
        <div class="ligne"><span class="label">Facteur forme dom.</span><span class="val">{d['f_forme_home']}</span></div>
        <div class="ligne"><span class="label">Facteur forme ext.</span><span class="val">{d['f_forme_away']}</span></div>
        <div class="ligne"><span class="label">Facteur class. dom.</span><span class="val">{d['f_class_home']}</span></div>
        <div class="ligne"><span class="label">Facteur class. ext.</span><span class="val">{d['f_class_away']}</span></div>
        <div class="ligne"><span class="label">Facteur H2H dom.</span><span class="val">{d['f_h2h_home']}</span></div>
        <div class="ligne"><span class="label">Facteur H2H ext.</span><span class="val">{d['f_h2h_away']}</span></div>
        <div class="ligne"><span class="label">Facteur météo</span><span class="val">{d['f_meteo']}</span></div>
        <div class="ligne"><span class="label">Facteur enjeu</span><span class="val">{d['f_enjeu']}</span></div>
        <div class="ligne"><span class="label">Facteur bless. dom./ext.</span><span class="val">{d['f_bless_dom']} / {d['f_bless_ext']}</span></div>
        <div class="ligne"><span class="label">Facteur fatigue dom./ext.</span><span class="val">{d['f_fatigue_dom']} / {d['f_fatigue_ext']}</span></div>
    </div>
    """

    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>QFTE — Résultats</title>
        <style>{STYLE_COMMUN}</style>
    </head>
    <body>
        <div style="text-align:center;margin-bottom:12px;">
            <a href="/historique" class="btn btn-secondary" style="margin:0;">📊 Historique</a>
        </div>

        <h1>🦁 QFTE V23.0 — Analyse</h1>
        <p style="text-align:center;color:#999;font-size:12px;">{equipe_domicile} vs {equipe_exterieur} — {competition}</p>

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

        <h2 style="text-align:left;">📋 Détail — Marché 1X2</h2>
        {candidats_html}

        <h2 style="text-align:left;">🎯 Détail — Marché Handicap</h2>
        {handicap_html}

        {details_html}

        <div style="text-align:center;margin:24px 0;">
            <button class="btn" onclick="sauvegarder()">💾 Sauvegarder cette analyse</button>
            <a href="/" class="btn btn-secondary">← Nouvelle analyse</a>
        </div>

        <script>
        const ANALYSE = {analyse_json};
        function sauvegarder() {{
            try {{
                let hist = JSON.parse(localStorage.getItem('qfte_analyses') || '[]');
                hist = hist.filter(a => !(a.equipe_domicile === ANALYSE.equipe_domicile && a.equipe_exterieur === ANALYSE.equipe_exterieur && a.date_match === ANALYSE.date_match));
                hist.unshift(ANALYSE);
                if (hist.length > 200) hist = hist.slice(0, 200);
                localStorage.setItem('qfte_analyses', JSON.stringify(hist));
                alert('✅ Analyse sauvegardée !');
            }} catch(e) {{ alert('❌ Erreur : ' + e.message); }}
        }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


HISTORIQUE_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QFTE — Historique</title>
    <style>
        body { font-family: -apple-system, Arial, sans-serif; background: #0f0f1a; color: #eee; padding: 16px; line-height: 1.5; }
        h1 { color: #ffcc00; font-size: 20px; text-align: center; }
        .box { background: #14141f; border: 1px solid #262636; border-radius: 10px; padding: 12px; margin-bottom: 14px; }
        .ligne { display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; }
        .label { color: #999; }
        .val { color: #fff; font-weight: bold; }
        .btn { display: inline-block; padding: 12px 16px; background: #ffcc00; color: #000; border: none; border-radius: 8px; font-size: 14px; font-weight: bold; cursor: pointer; margin: 6px 4px 6px 0; text-decoration: none; }
        .btn-secondary { background: #262636; color: #ffcc00; }
        .btn-danger { background: #ef4444; color: #fff; }
        .empty { text-align: center; color: #666; padding: 40px 20px; }
        .badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .badge-elite { background: #4ade80; color: #000; }
        .badge-premium { background: #22c55e; color: #000; }
        .badge-good { background: #eab308; color: #000; }
        .badge-avoid { background: #ef4444; color: #fff; }
    </style>
</head>
<body>
    <h1>📊 Historique QFTE V23.0</h1>
    <div style="text-align:center;margin-bottom:16px;">
        <a href="/" class="btn btn-secondary">← Nouvelle analyse</a>
        <button class="btn" onclick="exporter()">📤 Exporter JSON</button>
        <button class="btn btn-danger" onclick="vider()">🗑️ Vider</button>
    </div>
    <div id="compteur" style="text-align:center;color:#999;font-size:13px;margin-bottom:16px;"></div>
    <div id="liste"></div>
    <script>
    function charger() { let h = []; try { h = JSON.parse(localStorage.getItem('qfte_analyses') || '[]'); } catch(e) {} return h; }
    function afficher() {
        const hist = charger();
        const liste = document.getElementById('liste');
        const compteur = document.getElementById('compteur');
        if (hist.length === 0) { compteur.textContent = ''; liste.innerHTML = '<div class="empty">Aucune analyse sauvegardée.</div>'; return; }
        compteur.textContent = hist.length + ' analyse(s)';
        let html = '';
        hist.forEach((a, i) => {
            const r = a.resultats || {};
            const pari = r.pari_retenu;
            let badge = '<span class="badge badge-avoid">AUCUN</span>';
            let resume = 'Aucun pari retenu';
            if (pari) {
                if (pari.niveau === 'ELITE') badge = '<span class="badge badge-elite">ELITE</span>';
                else if (pari.niveau === 'PREMIUM') badge = '<span class="badge badge-premium">PREMIUM</span>';
                else if (pari.niveau === 'GOOD') badge = '<span class="badge badge-good">GOOD</span>';
                else badge = '<span class="badge badge-avoid">' + pari.niveau + '</span>';
                resume = pari.selection + ' @ ' + pari.cote + ' (EV ' + (pari.ev*100).toFixed(2) + '%)';
            }
            html += '<div class="box">';
            html += '<div class="ligne"><span class="label">#' + (i+1) + ' — ' + (a.date_analyse || '') + '</span><span class="val">' + badge + '</span></div>';
            html += '<div class="ligne"><span class="label">Match</span><span class="val">' + (a.equipe_domicile || '') + ' vs ' + (a.equipe_exterieur || '') + '</span></div>';
            html += '<div class="ligne"><span class="label">Résultat</span><span class="val">' + resume + '</span></div>';
            html += '</div>';
        });
        liste.innerHTML = html;
    }
    function exporter() {
        const hist = charger();
        if (hist.length === 0) { alert('Rien à exporter.'); return; }
        const blob = new Blob([JSON.stringify(hist, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'qfte_historique_' + new Date().toISOString().slice(0,10) + '.json';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
    function vider() {
        if (!confirm('⚠️ Vider TOUT l\\'historique ?')) return;
        localStorage.removeItem('qfte_analyses');
        afficher();
    }
    afficher();
    </script>
</body>
</html>
"""


@app.get("/historique", response_class=HTMLResponse)
async def historique(request: Request):
    return HTMLResponse(content=HISTORIQUE_HTML)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "V23.0"}
