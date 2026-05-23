from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Profile
from app.db.session import get_db

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileIn(BaseModel):
    cuisine_prefs: list[str] = Field(default_factory=list)
    spicy: int = Field(ge=0, le=5)
    dislikes: list[str] = Field(default_factory=list)


class ProfileOut(ProfileIn):
    pass


@router.get("", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    p = db.get(Profile, 1)
    return ProfileOut(cuisine_prefs=p.cuisine_prefs, spicy=p.spicy, dislikes=p.dislikes)


@router.put("", response_model=ProfileOut)
def put_profile(body: ProfileIn, db: Session = Depends(get_db)):
    p = db.get(Profile, 1)
    p.cuisine_prefs = body.cuisine_prefs
    p.spicy = body.spicy
    p.dislikes = body.dislikes
    p.updated_at = datetime.utcnow()
    db.commit()
    return body
