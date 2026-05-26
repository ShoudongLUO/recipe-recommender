from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def invalidate_prefix(self, prefix: str) -> None:
        for k in [k for k in self._store if k.startswith(prefix)]:
            self._store.pop(k, None)


recommend_cache = TTLCache(ttl_seconds=30)
