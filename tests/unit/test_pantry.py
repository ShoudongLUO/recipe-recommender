from datetime import date, timedelta

from app.db.models import WeeklyIngredients
from app.services.pantry import ensure_current_week
from app.services.week import get_monday


def _prev_monday():
    return get_monday(date.today()) - timedelta(days=7)


def test_ensure_returns_existing_current_week(db_session, test_user):
    ws = get_monday(date.today())
    db_session.add(WeeklyIngredients(user_id=test_user.id, week_start=ws,
        items=["番茄"], quantities={"番茄": "2个"}, used_up=[]))
    db_session.commit()
    got = ensure_current_week(db_session, test_user)
    assert got.week_start == ws
    assert got.items == ["番茄"]


def test_ensure_carries_unused_from_prev_week(db_session, test_user):
    db_session.add(WeeklyIngredients(user_id=test_user.id, week_start=_prev_monday(),
        items=["番茄", "鸡蛋", "牛奶"],
        quantities={"番茄": "2个", "鸡蛋": "3个", "牛奶": "1盒"}, used_up=["鸡蛋"]))
    db_session.commit()
    got = ensure_current_week(db_session, test_user)
    assert got.week_start == get_monday(date.today())
    assert got.items == ["番茄", "牛奶"]
    assert got.quantities == {"番茄": "2个", "牛奶": "1盒"}
    assert got.used_up == []


def test_ensure_no_history_returns_none(db_session, test_user):
    assert ensure_current_week(db_session, test_user) is None


def test_ensure_all_used_up_returns_none(db_session, test_user):
    db_session.add(WeeklyIngredients(user_id=test_user.id, week_start=_prev_monday(),
        items=["番茄"], quantities={"番茄": "2个"}, used_up=["番茄"]))
    db_session.commit()
    assert ensure_current_week(db_session, test_user) is None
