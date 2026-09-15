from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="QFTE Bot V23.0")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "titre": "QFTE V23.0 – Bot d'analyse"}
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": "V23.0"}
