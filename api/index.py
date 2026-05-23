"""Vercel @vercel/python entry point.

Vercel imports this file and looks for `app` (an ASGI callable).
We re-export the FastAPI app from app.main.
"""
from app.main import app  # noqa: F401
