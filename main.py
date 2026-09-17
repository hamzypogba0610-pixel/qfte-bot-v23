from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="QFTE Bot V23.0")


@app.get("/", response_class=HTMLResponse)
async def accueil():
    return "<h1>QFTE V23.0</h1><p>Le bot est en ligne !</p>"


@app.get("/health")
async def health():
    return {"status": "ok", "version": "V23.0"}
