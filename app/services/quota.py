from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.db.models import ApiQuota


def bump_quota(db: Session, user_id) -> int:
    today = date.today()
    row = db.get(ApiQuota, (user_id, today))
    if row is None:
        row = ApiQuota(user_id=user_id, quota_date=today, count=1)
        db.add(row)
    else:
        row.count += 1
    db.commit()
    return row.count


def today_quota(db: Session, user_id) -> int:
    row = db.get(ApiQuota, (user_id, date.today()))
    return row.count if row else 0
