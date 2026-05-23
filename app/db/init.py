from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Base, Profile
from app.db.session import SessionLocal, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        if db.get(Profile, 1) is None:
            db.add(Profile(id=1, cuisine_prefs=[], spicy=2, dislikes=[]))
            db.commit()
    finally:
        db.close()
