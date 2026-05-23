from __future__ import annotations

from datetime import date, timedelta


def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())
