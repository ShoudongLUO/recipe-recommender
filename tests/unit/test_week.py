from datetime import date

from app.services.week import get_monday


def test_monday_returns_self():
    assert get_monday(date(2026, 5, 18)) == date(2026, 5, 18)


def test_sunday_returns_previous_monday():
    assert get_monday(date(2026, 5, 24)) == date(2026, 5, 18)


def test_wednesday_returns_monday():
    assert get_monday(date(2026, 5, 20)) == date(2026, 5, 18)


def test_cross_year_boundary():
    # 2026-01-01 is a Thursday -> previous Monday is 2025-12-29
    assert get_monday(date(2026, 1, 1)) == date(2025, 12, 29)
