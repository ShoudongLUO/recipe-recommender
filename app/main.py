from __future__ import annotations

from fastapi import FastAPI

from app.routes import auth, dishes, history, ingredients, profile, recommend
from app.services.gemini import build_gemini_client

app = FastAPI(title="Recipe Recommender")
app.state.gemini = build_gemini_client()

app.include_router(auth.router)
app.include_router(dishes.router)
app.include_router(history.router)
app.include_router(ingredients.router)
app.include_router(profile.router)
app.include_router(recommend.router)
