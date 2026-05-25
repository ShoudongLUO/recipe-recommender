from __future__ import annotations

from fastapi import FastAPI

from app.routes import auth, dishes, history, ingredients, llm_config, profile, recommend

app = FastAPI(title="Recipe Recommender")

app.include_router(auth.router)
app.include_router(dishes.router)
app.include_router(history.router)
app.include_router(ingredients.router)
app.include_router(llm_config.router)
app.include_router(profile.router)
app.include_router(recommend.router)
