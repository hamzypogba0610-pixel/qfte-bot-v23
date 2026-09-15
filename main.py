from fastapi import FastAPI

app = FastAPI(
    title="QFTE V23 Web Bot",
    description="API web pour la plateforme quantitative QFTE V23",
    version="0.1.0",
)


@app.get("/")
def read_root():
    return {"message": "QFTE V23 Web Bot is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
