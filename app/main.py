from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes import auth, dishes, history, ingredients, llm_config, plan, profile, recommend

app = FastAPI(title="Recipe Recommender")

app.include_router(auth.router)
app.include_router(dishes.router)
app.include_router(history.router)
app.include_router(ingredients.router)
app.include_router(llm_config.router)
app.include_router(profile.router)
app.include_router(recommend.router)
app.include_router(plan.router)

# Serve the SPA locally / in tests. In production Vercel routes "/" and
# "/static/*" to the static build before requests reach this app, so these are
# only exercised off-Vercel. check_dir=False keeps import safe where the
# directory isn't bundled (e.g. the Vercel function filesystem).
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=_STATIC_DIR, check_dir=False), name="static")
