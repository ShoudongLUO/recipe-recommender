from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db.init import init_db
from app.routes import dishes, ingredients, profile, recommend
from app.services.gemini import build_gemini_client

app = FastAPI(title="Recipe Recommender")
app.state.gemini = build_gemini_client()

app.include_router(profile.router)
app.include_router(ingredients.router)
app.include_router(dishes.router)
app.include_router(recommend.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.on_event("startup")
def _startup():
    init_db()
