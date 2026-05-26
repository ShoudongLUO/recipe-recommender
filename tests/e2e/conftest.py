"""Fixtures for browser smoke tests.

These tests are opt-in. One-time setup:
    pip install pytest-playwright   (or: pip install -e .[e2e])
    playwright install chromium
Then run:
    python -m pytest tests/e2e

The `live_server` fixture launches the real FastAPI app via uvicorn against a
throwaway SQLite database (its own DATABASE_URL, so it never touches dev/prod
data), seeds one user + a JWT, and yields the base URL + token.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_until_up(base_url: str, proc: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
            raise RuntimeError(f"server exited early (code {proc.returncode}):\n{out}")
        try:
            urllib.request.urlopen(base_url + "/", timeout=2)
            return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError("server did not come up within timeout")


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("e2e") / "e2e.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    # Create schema + seed a user + mint a token in the same DB the server uses.
    from sqlalchemy.orm import Session

    from app.db.models import Base, Profile, User
    from app.db.session import make_engine
    from app.services.auth import create_token, hash_password

    engine = make_engine(db_url)
    Base.metadata.create_all(engine)
    uid = uuid.uuid4()
    with Session(engine) as s:
        s.add(User(id=uid, username="e2e", password_hash=hash_password("e2epass12")))
        s.add(Profile(user_id=uid, cuisine_prefs=[], spicy=2, dislikes=[]))
        s.commit()
    engine.dispose()
    token = create_token(user_id=uid, username="e2e")

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO_ROOT),
        env={**os.environ, "DATABASE_URL": db_url},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_until_up(base_url, proc)
        yield {"base_url": base_url, "token": token, "username": "e2e"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
