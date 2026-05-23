from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Profile, User
from app.db.session import get_db
from app.services.auth import current_user

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileIn(BaseModel):
    cuisine_prefs: list[str] = Field(default_factory=list)
    spicy: int = Field(ge=0, le=5)
    dislikes: list[str] = Field(default_factory=list)


class ProfileOut(ProfileIn):
    pass


@router.get("", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Profile, user.id)
    if p is None:
        return ProfileOut(cuisine_prefs=[], spicy=2, dislikes=[])
    return ProfileOut(cuisine_prefs=p.cuisine_prefs, spicy=p.spicy, dislikes=p.dislikes)


@router.put("", response_model=ProfileOut)
def put_profile(
    body: ProfileIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    p = db.get(Profile, user.id)
    if p is None:
        p = Profile(user_id=user.id, cuisine_prefs=body.cuisine_prefs,
                    spicy=body.spicy, dislikes=body.dislikes)
        db.add(p)
    else:
        p.cuisine_prefs = body.cuisine_prefs
        p.spicy = body.spicy
        p.dislikes = body.dislikes
        p.updated_at = datetime.utcnow()
    db.commit()
    return body
