from __future__ import annotations


def can_cook_with(dish_ingredients: list[str], pantry: list[str]) -> bool:
    return set(dish_ingredients).issubset(set(pantry))


def has_forbidden(
    cuisine: str | None, main_ingredients: list[str], dislikes: list[str]
) -> bool:
    blocked = set(dislikes)
    if cuisine and cuisine in blocked:
        return True
    if set(main_ingredients) & blocked:
        return True
    return False
