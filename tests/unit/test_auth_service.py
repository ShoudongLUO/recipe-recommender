import pytest

from app.services.auth import hash_password, verify_password


def test_hash_password_returns_non_empty_string():
    h = hash_password("hello1234")
    assert isinstance(h, str)
    assert len(h) > 20
    assert h != "hello1234"


def test_verify_correct_password():
    h = hash_password("hello1234")
    assert verify_password("hello1234", h) is True


def test_verify_wrong_password():
    h = hash_password("hello1234")
    assert verify_password("wrong1234", h) is False


def test_two_hashes_of_same_password_differ():
    a = hash_password("hello1234")
    b = hash_password("hello1234")
    assert a != b  # salt differs
    assert verify_password("hello1234", a)
    assert verify_password("hello1234", b)
