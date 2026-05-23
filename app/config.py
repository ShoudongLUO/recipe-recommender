from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    database_url: str
    daily_gemini_quota: int


def load_settings() -> Settings:
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data.db"),
        daily_gemini_quota=int(os.getenv("DAILY_GEMINI_QUOTA", "100")),
    )


settings = load_settings()
