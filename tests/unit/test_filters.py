from app.services.filters import can_cook_with, has_forbidden


def test_can_cook_full_match():
    assert can_cook_with(["番茄", "鸡蛋"], ["番茄", "鸡蛋", "葱"]) is True


def test_can_cook_missing_one():
    assert can_cook_with(["番茄", "鸡蛋", "牛肉"], ["番茄", "鸡蛋"]) is False


def test_can_cook_empty_dish():
    assert can_cook_with([], ["番茄"]) is True


def test_can_cook_empty_pantry():
    assert can_cook_with(["番茄"], []) is False


def test_has_forbidden_in_ingredients():
    assert has_forbidden(
        cuisine="川", main_ingredients=["香菜", "牛肉"], dislikes=["香菜"]
    ) is True


def test_has_forbidden_in_cuisine():
    assert has_forbidden(
        cuisine="川", main_ingredients=["豆腐"], dislikes=["川"]
    ) is True


def test_no_forbidden():
    assert has_forbidden(
        cuisine="粤", main_ingredients=["虾"], dislikes=["香菜", "内脏"]
    ) is False
