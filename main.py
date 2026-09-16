import json
import re
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from qfte_engine.mvp import analyser_match_football

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")


def parser_matchs(texte):
    r = []
    if not texte: return r
    for m in [x.strip() for x in texte.split(",") if x.strip()]:
        mh = re.match(r"^(\d+)\s*-\s*(\d+)\s*\(\s*(\d+)\s*-\s*(\d+)\s*\)$", m)
        ms = re.match(r"^(\d+)\s*-\s*(\d+)$", m)
        if mh:
            r.append({"bp": int(mh.group(1)), "bc": int(mh.group(2)), "ht_bp": int(mh.group(3)), "ht_bc": int(mh.group(4))})
        elif ms:
            r.append({"bp": int(ms.group(1)), "bc": int(ms.group(2)), "ht_bp": None, "ht_bc": None})
    return r


def parser_handicap(texte):
    r = []
    if not texte: return r
    for m in [x.strip() for x in texte.split(",") if x.strip()]:
        p = [x.strip() for x in m.split("/") if x.strip()]
        if len(p) != 4: continue
        try:
            r.append({"hcp_dom": float(p[0]), "cote_dom": float(p[1]), "hcp_ext": float(p[2]), "cote_ext": float(p[3])})
        except: pass
    return r


def parser_ou(texte):
    r = []
    if not texte: return r
    for m in [x.strip() for x in texte.split(",") if x.strip()]:
        p = [x.strip() for x in m.split("/") if x.strip()]
        if len(p) != 3: continue
        try:
            r.append({"ligne": float(p[0]), "cote_over": float(p[1]), "cote_under": float(p[2])})
        except: pass
    return r


def ffloat(form, key, default=0.0):
    v = form.get(key, "")
    if v is None or v == "": return default
    try: return float(v)
    except: return default


def fint(form, key):
    v = form.get(key, "")
    if v is None or v == "": return None
    try: return int(v)
    except: return None


STYLE = """
    body { font-family: -apple-system, Arial, sans-serif; background: #0f0f1a; color: #eee; padding: 16px; line-height: 1.5; }
    h1 { color: #ffcc00; font-size: 20px; text-align: center; }
    h2 { color: #ffcc00; font-size: 15px; margin-top: 10px; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 6px; }
    .box { background: #14141f; border: 1px solid #262636; border-radius: 10px; padding: 12px; margin-bottom: 14px; }
    .ligne { display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; }
    .label { color: #999; } .val { color: #fff; font-weight: bold; }
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
    ou_lignes = parser_ou(form.get("ou_buts", ""))

    open_1 = ffloat(form, "open_1"); open_x = ffloat(form, "open_x"); open_2 = ffloat(form, "open_2")
    curr_1 = ffloat(form, "curr_1"); curr_x = ffloat(form, "curr_x"); curr_2 = ffloat(form, "curr_2")

    ht_1 = ffloat(form, "ht_1"); ht_x = ffloat(form, "ht_x"); ht_2 = ffloat(form, "ht_2")
    h2_1 = ffloat(form, "h2_1"); h2_x = ffloat(form, "h2_x"); h2_2 = ffloat(form, "h2_2")
    cotes_ht = [ht_1, ht_x, ht_2] if (ht_1 and ht_2) else None
    cotes_2h = [h2_1, h2_x, h2_2] if (h2_1 and h2_2) else None

    meteo = form.get("meteo", "normale"); enjeu = form.get("enjeu", "normal")
    bd = form.get("blessures_domicile") is not None
    be = form.get("blessures_exterieur") is not None
    fd = form.get("fatigue_domicile") is not None
    fe = form.get("fatigue_exterieur") is not None
    pos_dom = fint(form, "pos_dom"); pos_ext = fint(form, "pos_ext"); total_equipes = fint(form, "total_equipes")

    r = analyser_match_football(
        home_ctx, home_glob, away_ctx, away_glob,
        open_1, open_x, open_2, curr_1, curr_x, curr_2,
        meteo, enjeu, bd, be, fd, fe, h2h_matchs, handicap_lignes, ou_lignes,
        pos_dom, pos_ext, total_equipes, cotes_ht, cotes_2h
    )

    analyse_complete = {
        "date_analyse": datetime.now().isoformat(timespec="seconds"),
        "sport": sport, "competition": competition,
        "equipe_domicile": equipe_domicile, "equipe_exterieur": equipe_exterieur,
        "date_match": date_match, "resultats": r,
    }
    analyse_json = json.dumps(analyse_complete, ensure_ascii=False).replace("</", "<\\/")
# Décision
if r["pari_retenu"]:
    p = r["pari_retenu"]
    tl = p.get("type", "1X2")
    decision_html = f"""
    <div class="box" style="border:2px solid #4ade80;">
        <h2 style="color:#4ade80;">🟢 PARI RETENU ({tl})</h2>
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

securite_html = ""
if r.get("ou_securite"):
    s = r["ou_securite"]
    ec = "#4ade80" if s["ev"] >= 0 else "#ef4444"
    st = '✅ PASSE' if s['passe_filtres'] else '⚠️ Partiel'
    securite_html = f"""
    <div class="box" style="border:2px solid #60a5fa;">
        <h2 style="color:#60a5fa;">🛡️ SÉCURITÉ (Over/Under)</h2>
        <div class="ligne"><span class="label">Marché</span><span class="val">{s['type']} {s['ligne']} buts</span></div>
        <div class="ligne"><span class="label">Cote</span><span class="val">{s['cote']}</span></div>
        <div class="ligne"><span class="label">P(effective)</span><span class="val">{s['p']*100:.2f}%</span></div>
        <div class="ligne"><span class="label">EV net</span><span class="val" style="color:{ec};">{s['ev']*100:+.2f}%</span></div>
        <div class="ligne"><span class="label">Fiabilité</span><span class="val">{s['fiabilite']}</span></div>
        <div class="ligne"><span class="label">Filtres</span><span class="val">{st}</span></div>
    </div>
    """

def bloc_candidat(c):
    ec = "#4ade80" if c["ev"] >= 0 else "#ef4444"
    if c["passe_filtres"]:
        st = '<span style="color:#4ade80;font-weight:bold;">✅ PASSE</span>'; rh = ""
    else:
        st = '<span style="color:#ef4444;font-weight:bold;">❌ REJETÉ</span>'
        rh = "".join([f'<div class="ligne"><span class="label" style="color:#ef4444;font-size:12px;">→ {x}</span></div>' for x in c["raisons_rejet"]])
    return f"""
    <div class="box">
        <div class="ligne"><span class="label">Sélection</span><span class="val">{c['selection']}</span></div>
        <div class="ligne"><span class="label">Probabilité</span><span class="val">{c['p']*100:.2f}%</span></div>
        <div class="ligne"><span class="label">Cote</span><span class="val">{c['cote']}</span></div>
        <div class="ligne"><span class="label">EV net</span><span class="val" style="color:{ec};">{c['ev']*100:+.2f}%</span></div>
        <div class="ligne"><span class="label">Fiabilité</span><span class="val">{c['fiabilite']}</span></div>
        <div class="ligne"><span class="label">Filtres</span><span class="val">{st}</span></div>
        {rh}
    </div>
    """

candidats_html = "".join([bloc_candidat(c) for c in r["candidats"]])

handicap_html = ""
if r["handicap_resultats"]:
    for h in r["handicap_resultats"]:
        ec = "#4ade80" if h["ev"] >= 0 else "#ef4444"
        if h["passe_filtres"]:
            st = '<span style="color:#4ade80;font-weight:bold;">✅ PASSE</span>'; rh = ""
        else:
            st = '<span style="color:#ef4444;font-weight:bold;">❌ REJETÉ</span>'
            rh = "".join([f'<div class="ligne"><span class="label" style="color:#ef4444;font-size:12px;">→ {x}</span></div>' for x in h["raisons_rejet"]])
        handicap_html += f"""
        <div class="box">
            <div class="ligne"><span class="label">Handicap</span><span class="val">{h['hcp']:+g} ({h['cible']})</span></div>
            <div class="ligne"><span class="label">P(gain) / P(remb.)</span><span class="val">{h['p_gain']*100:.1f}% / {h['p_remb']*100:.1f}%</span></div>
            <div class="ligne"><span class="label">P(effective)</span><span class="val">{h['p']*100:.2f}%</span></div>
            <div class="ligne"><span class="label">Cote</span><span class="val">{h['cote']}</span></div>
            <div class="ligne"><span class="label">EV net</span><span class="val" style="color:{ec};">{h['ev']*100:+.2f}%</span></div>
            <div class="ligne"><span class="label">Fiabilité</span><span class="val">{h['fiabilite']}</span></div>
            <div class="ligne"><span class="label">Filtres</span><span class="val">{st}</span></div>
            {rh}
        </div>
        """
else:
    handicap_html = '<div class="box"><p style="color:#666;font-size:13px;">Aucun handicap saisi.</p></div>'

ou_html = ""
if r["ou_resultats"]:
    for o in r["ou_resultats"]:
        ec = "#4ade80" if o["ev"] >= 0 else "#ef4444"
        if o["passe_filtres"]:
            st = '<span style="color:#4ade80;font-weight:bold;">✅ PASSE</span>'; rh = ""
        else:
            st = '<span style="color:#ef4444;font-weight:bold;">❌ REJETÉ</span>'
            rh = "".join([f'<div class="ligne"><span class="label" style="color:#ef4444;font-size:12px;">→ {x}</span></div>' for x in o["raisons_rejet"]])
        ou_html += f"""
        <div class="box">
            <div class="ligne"><span class="label">Marché</span><span class="val">{o['type']} {o['ligne']}</span></div>
            <div class="ligne"><span class="label">P(gain) / P(remb.)</span><span class="val">{o['p_brute']*100:.1f}% / {o['p_remb']*100:.1f}%</span></div>
            <div class="ligne"><span class="label">P(effective)</span><span class="val">{o['p']*100:.2f}%</span></div>
            <div class="ligne"><span class="label">Cote</span><span class="val">{o['cote']}</span></div>
            <div class="ligne"><span class="label">EV net</span><span class="val" style="color:{ec};">{o['ev']*100:+.2f}%</span></div>
            <div class="ligne"><span class="label">Fiabilité</span><span class="val">{o['fiabilite']}</span></div>
            <div class="ligne"><span class="label">Filtres</span><span class="val">{st}</span></div>
            {rh}
        </div>
        """
else:
    ou_html = '<div class="box"><p style="color:#666;font-size:13px;">Aucun O/U saisi.</p></div>'

m2mt = r["marches_2mt"]
mt2_html = ""
if m2mt.get("ht"):
    mt2_html += "<h2 style='text-align:left;color:#4ea8ff;'>🕐 Mi-temps (HT)</h2>"
    mt2_html += f'<div class="box"><div class="ligne"><span class="label">P 1 / X / 2 HT</span><span class="val">{m2mt["p1_ht"]*100:.1f}% / {m2mt["px_ht"]*100:.1f}% / {m2mt["p2_ht"]*100:.1f}%</span></div></div>'
    for c in m2mt["ht"]:
        mt2_html += bloc_candidat(c)
if m2mt.get("2h"):
    mt2_html += "<h2 style='text-align:left;color:#4ea8ff;'>🕐 2ème mi-temps (2H)</h2>"
    mt2_html += f'<div class="box"><div class="ligne"><span class="label">P 1 / X / 2 2H</span><span class="val">{m2mt["p1_2h"]*100:.1f}% / {m2mt["px_2h"]*100:.1f}% / {m2mt["p2_2h"]*100:.1f}%</span></div></div>'
    for c in m2mt["2h"]:
        mt2_html += bloc_candidat(c)
if not mt2_html:
    mt2_html = '<div class="box"><p style="color:#666;font-size:13px;">Aucune cote 2 mi-temps saisie.</p></div>'

divergences_html = ""
if r.get("divergences"):
    blocs = ""
    for d in r["divergences"]:
        if d["niveau"] == "MAJEUR": bord = "#ef4444"; color = "#ef4444"
        else: bord = "#eab308"; color = "#eab308"
        blocs += f"""
        <div class="box" style="border-left:4px solid {bord};padding-left:10px;">
            <div class="ligne"><span class="label">Marché</span><span class="val">{d['marche']}</span></div>
            <div class="ligne"><span class="label">P_modèle / P_marché</span><span class="val">{d['p_modele']*100:.1f}% / {d['p_marche']*100:.1f}%</span></div>
            <div class="ligne"><span class="label">Écart</span><span class="val" style="color:{color};">{d['ecart']*100:+.1f}%</span></div>
            <div class="ligne"><span class="label">Niveau</span><span class="val" style="color:{color};">{d['niveau']}</span></div>
            <div class="ligne"><span class="label" style="font-size:12px;">{d['interpretation']}</span></div>
        </div>
        """
    divergences_html = f'<h2 style="text-align:left;">🔍 Divergences détectées</h2>{blocs}'
else:
    divergences_html = '<h2 style="text-align:left;">🔍 Divergences détectées</h2><div class="box"><p style="color:#4ade80;font-size:13px;">✅ Aucune divergence majeure.</p></div>'

scores_html = "".join([f'<div class="ligne"><span class="label">#{s["rank"]}</span><span class="val">{s["score"]} — {s["probability"]*100:.2f}%</span></div>' for s in r["top_3_scores"]])

d = r["details"]
details_html = f"""
<div class="box">
    <h2>🔬 Ajustements appliqués</h2>
    <div class="ligne"><span class="label">BP dom (ctx/glob)</span><span class="val">{d['home_bp_ctx']} / {d['home_bp_glob']}</span></div>
    <div class="ligne"><span class="label">BP ext (ctx/glob)</span><span class="val">{d['away_bp_ctx']} / {d['away_bp_glob']}</span></div>
    <div class="ligne"><span class="label">Ratio HT dom./ext.</span><span class="val">{d['ratio_ht_home']} / {d['ratio_ht_away']}</span></div>
    <div class="ligne"><span class="label">Facteur HT dom./ext.</span><span class="val">{d['f_ht_home']} / {d['f_ht_away']}</span></div>
    <div class="ligne"><span class="label">Facteur forme dom./ext.</span><span class="val">{d['f_forme_home']} / {d['f_forme_away']}</span></div>
    <div class="ligne"><span class="label">Facteur class. dom./ext.</span><span class="val">{d['f_class_home']} / {d['f_class_away']}</span></div>
    <div class="ligne"><span class="label">Facteur H2H dom./ext.</span><span class="val">{d['f_h2h_home']} / {d['f_h2h_away']}</span></div>
    <div class="ligne"><span class="label">Facteur météo / enjeu</span><span class="val">{d['f_meteo']} / {d['f_enjeu']}</span></div>
    <div class="ligne"><span class="label">Blessures dom./ext.</span><span class="val">{d['f_bless_dom']} / {d['f_bless_ext']}</span></div>
    <div class="ligne"><span class="label">Fatigue dom./ext.</span><span class="val">{d['f_fatigue_dom']} / {d['f_fatigue_ext']}</span></div>
</div>
"""

html = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QFTE — Résultats</title>
    <style>{STYLE}</style>
</head>
<body>
    <div style="text-align:center;margin-bottom:12px;">
        <a href="/historique" class="btn btn-secondary" style="margin:0;">📊 Historique</a>
    </div>
    <h1>🦁 QFTE V23.0 — Analyse</h1>
    <p style="text-align:center;color:#999;font-size:12px;">{equipe_domicile} vs {equipe_exterieur} — {competition}</p>

    {decision_html}
    {securite_html}

    <div class="box">
        <h2>⚽ Buts attendus (λ)</h2>
        <div class="ligne"><span class="label">{equipe_domicile} (total)</span><span class="val">{r['lambda_home']}</span></div>
        <div class="ligne"><span class="label">{equipe_exterieur} (total)</span><span class="val">{r['lambda_away']}</span></div>
        <div class="ligne"><span class="label">{equipe_domicile} (HT)</span><span class="val">{r['lambda_ht_home']}</span></div>
        <div class="ligne"><span class="label">{equipe_exterieur} (HT)</span><span class="val">{r['lambda_ht_away']}</span></div>
        <div class="ligne"><span class="label">{equipe_domicile} (2H)</span><span class="val">{r['lambda_2h_home']}</span></div>
        <div class="ligne"><span class="label">{equipe_exterieur} (2H)</span><span class="val">{r['lambda_2h_away']}</span></div>
    </div>

    <div class="box">
        <h2>🎯 Probabilités 1X2 (temps plein)</h2>
        <div class="ligne"><span class="label">1</span><span class="val">{r['p1']*100:.2f}%</span></div>
        <div class="ligne"><span class="label">X</span><span class="val">{r['px']*100:.2f}%</span></div>
        <div class="ligne"><span class="label">2</span><span class="val">{r['p2']*100:.2f}%</span></div>
    </div>

    <div class="box">
        <h2>🎲 Top 3 scores probables</h2>
        {scores_html}
    </div>

    {divergences_html}

    <h2 style="text-align:left;">📋 Détail — 1X2</h2>
    {candidats_html}

    <h2 style="text-align:left;">🎯 Détail — Handicap</h2>
    {handicap_html}

    <h2 style="text-align:left;">⚽ Détail — Over / Under</h2>
    {ou_html}

    <h2 style="text-align:left;">🕐 Détail — 2 Mi-temps</h2>
    {mt2_html}

    {details_html}

    <div style="text-align:center;margin:24px 0;">
        <button class="btn" onclick="sauvegarder()">💾 Sauvegarder</button>
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
        .label { color: #999; } .val { color: #fff; font-weight: bold; }
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
