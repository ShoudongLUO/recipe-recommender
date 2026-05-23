import time

from app.services.cache import TTLCache


def test_set_get_within_ttl():
    c = TTLCache(ttl_seconds=10)
    c.set("k", {"v": 1})
    assert c.get("k") == {"v": 1}


def test_expired_returns_none():
    c = TTLCache(ttl_seconds=0)
    c.set("k", {"v": 1})
    time.sleep(0.01)
    assert c.get("k") is None


def test_missing_key():
    c = TTLCache(ttl_seconds=10)
    assert c.get("nope") is None


def test_overwrite_extends_ttl():
    c = TTLCache(ttl_seconds=10)
    c.set("k", 1)
    c.set("k", 2)
    assert c.get("k") == 2
