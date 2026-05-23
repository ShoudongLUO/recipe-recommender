import math
from dataclasses import dataclass

from app.services.scoring import score_dish


@dataclass
class FakeDish:
    cuisine: str
    spicy: int
    cook_count: int


@dataclass
class FakeProfile:
    cuisine_prefs: list
    spicy: int


def test_cuisine_match_adds_one():
    d = FakeDish(cuisine="川", spicy=3, cook_count=0)
    p = FakeProfile(cuisine_prefs=["川"], spicy=3)
    assert score_dish(d, p) == 1.0 + 0.5


def test_cuisine_miss_no_one_point():
    d = FakeDish(cuisine="粤", spicy=3, cook_count=0)
    p = FakeProfile(cuisine_prefs=["川"], spicy=3)
    assert score_dish(d, p) == 0.5


def test_spicy_within_one_matches():
    d = FakeDish(cuisine="粤", spicy=2, cook_count=0)
    p = FakeProfile(cuisine_prefs=[], spicy=3)
    assert score_dish(d, p) == 0.5


def test_spicy_far_no_match():
    d = FakeDish(cuisine="粤", spicy=5, cook_count=0)
    p = FakeProfile(cuisine_prefs=[], spicy=0)
    assert score_dish(d, p) == 0.0


def test_cook_count_monotonic():
    p = FakeProfile(cuisine_prefs=[], spicy=0)
    s_low = score_dish(FakeDish(cuisine="x", spicy=5, cook_count=0), p)
    s_high = score_dish(FakeDish(cuisine="x", spicy=5, cook_count=10), p)
    assert s_high > s_low


def test_full_combo():
    d = FakeDish(cuisine="川", spicy=3, cook_count=4)
    p = FakeProfile(cuisine_prefs=["川"], spicy=3)
    assert score_dish(d, p) == 1.0 + 0.5 + 0.3 * math.log(5)
