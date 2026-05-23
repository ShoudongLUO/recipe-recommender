from __future__ import annotations

import math
from typing import Protocol


class DishLike(Protocol):
    cuisine: str | None
    spicy: int
    cook_count: int


class ProfileLike(Protocol):
    cuisine_prefs: list
    spicy: int


def score_dish(d: DishLike, p: ProfileLike) -> float:
    cuisine_pt = 1.0 if (d.cuisine and d.cuisine in p.cuisine_prefs) else 0.0
    spicy_pt = 0.5 if abs(d.spicy - p.spicy) <= 1 else 0.0
    count_pt = 0.3 * math.log(1 + max(0, d.cook_count))
    return cuisine_pt + spicy_pt + count_pt
