from app.routes.plan import compose_candidates


def test_compose_candidates_known_first_ai_deduped_capped():
    known = [{"name": f"k{i}"} for i in range(8)]
    ai = [{"name": "k0"}, {"name": "a1"}, {"name": "a2"}, {"name": "a3"}]
    out = compose_candidates(known, ai, limit=10)
    assert [c["name"] for c in out] == [
        "k0", "k1", "k2", "k3", "k4", "k5", "k6", "k7", "a1", "a2",
    ]


def test_compose_candidates_empty_ai():
    known = [{"name": "a"}, {"name": "b"}]
    assert compose_candidates(known, [], limit=10) == known
