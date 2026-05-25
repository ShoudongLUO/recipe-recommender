from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _normalize_url(url: str) -> str:
    # Neon/Vercel inject "postgresql://..."; SQLAlchemy would pick the (uninstalled)
    # psycopg2 driver. Force the psycopg (v3) driver, which is what we depend on.
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


def make_engine(url: str | None = None):
    url = _normalize_url(url or os.getenv("DATABASE_URL", "sqlite:///./data.db"))
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, future=True, pool_pre_ping=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
