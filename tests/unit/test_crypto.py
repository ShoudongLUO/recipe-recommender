import pytest

from app.services.crypto import encrypt, decrypt


def test_roundtrip():
    c = encrypt("sk-secret-123")
    assert c != "sk-secret-123"
    assert decrypt(c) == "sk-secret-123"


def test_ciphertext_differs_each_time():
    a = encrypt("same")
    b = encrypt("same")
    assert a != b
    assert decrypt(a) == "same" and decrypt(b) == "same"


def test_decrypt_garbage_raises():
    with pytest.raises(Exception):
        decrypt("not-valid-ciphertext")
