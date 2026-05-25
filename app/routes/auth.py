from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import InviteCode, Profile, User
from app.db.session import get_db
from app.services.auth import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[a-z0-9_]+$")
    password: str = Field(min_length=8, max_length=72)
    invite_code: str = Field(min_length=12, max_length=12)


class TokenOut(BaseModel):
    token: str
    username: str


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    user_id = uuid4()

    # Insert the user FIRST and flush it alone, so the row physically exists
    # before anything references users.id. (Postgres enforces FKs; relying on
    # SQLAlchemy to order a combined user+profile flush is not reliable when the
    # FK column is also the child's primary key.)
    user = User(
        id=user_id,
        username=body.username,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户名已存在")

    # user row now exists -> safe to create rows that reference it
    db.add(Profile(user_id=user_id, cuisine_prefs=[], spicy=2, dislikes=[]))

    # Atomically consume invite code
    stmt = (
        update(InviteCode)
        .where(InviteCode.code == body.invite_code, InviteCode.used_at.is_(None))
        .values(used_at=datetime.utcnow(), used_by_user_id=user_id)
    )
    result = db.execute(stmt)
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="邀请码无效或已使用")

    db.commit()
    token = create_token(user_id=user.id, username=user.username)
    return TokenOut(token=token, username=user.username)


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(user_id=user.id, username=user.username)
    return TokenOut(token=token, username=user.username)
