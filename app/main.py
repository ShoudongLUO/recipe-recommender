from __future__ import annotations

from fastapi import FastAPI

from app.db.init import init_db
from app.routes import ingredients, profile
from app.services.gemini import build_gemini_client

app = FastAPI(title="Recipe Recommender")
app.state.gemini = build_gemini_client()
app.include_router(profile.router)
app.include_router(ingredients.router)


@app.on_event("startup")
def _startup():
    init_db()
