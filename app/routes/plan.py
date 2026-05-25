from __future__ import annotations

TOTAL = 10


def compose_candidates(
    known_dicts: list[dict], ai_dicts: list[dict], limit: int = TOTAL
) -> list[dict]:
    """known 在前（调用方已排序），ai 去掉与 known 重名的，合并截断到 limit。"""
    known_names = {d["name"] for d in known_dicts}
    ai_unique = [d for d in ai_dicts if d["name"] not in known_names]
    return (known_dicts + ai_unique)[:limit]
