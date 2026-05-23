from scripts.invite import generate_code, FORBIDDEN_CHARS


def test_code_length():
    assert len(generate_code()) == 12


def test_code_charset():
    code = generate_code()
    for c in code:
        assert c not in FORBIDDEN_CHARS, f"forbidden char {c!r} in code"


def test_batch_uniqueness():
    codes = {generate_code() for _ in range(1000)}
    assert len(codes) == 1000


def test_forbidden_set_is_what_we_expect():
    assert FORBIDDEN_CHARS == set("0O1Il")
