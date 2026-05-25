from scripts.backfill_meals import meals_for_category


def test_drink_is_breakfast():
    assert meals_for_category("饮品") == ["breakfast"]


def test_soup_is_lunch_dinner():
    assert meals_for_category("汤类") == ["lunch", "dinner"]


def test_main_is_lunch_dinner():
    assert meals_for_category("主菜") == ["lunch", "dinner"]


def test_western_is_lunch_dinner():
    assert meals_for_category("西餐") == ["lunch", "dinner"]


def test_vegetarian_is_all_meals():
    assert meals_for_category("素食") == ["breakfast", "lunch", "dinner"]


def test_none_category_is_all_meals():
    assert meals_for_category(None) == ["breakfast", "lunch", "dinner"]


def test_unknown_category_is_all_meals():
    assert meals_for_category("夜宵") == ["breakfast", "lunch", "dinner"]
