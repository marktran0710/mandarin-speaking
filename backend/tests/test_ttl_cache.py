"""Unit tests for the analytics TTL memo cache (no DB, no app)."""

from analytics.ttl_cache import TTLCache


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_hit_within_ttl_computes_once():
    clock = FakeClock()
    cache = TTLCache(ttl_seconds=10, clock=clock)
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return "value"

    assert cache.get_or_compute("k", compute) == "value"
    clock.t = 9.99
    assert cache.get_or_compute("k", compute) == "value"
    assert calls["n"] == 1  # second call served from cache


def test_recomputes_after_ttl_expires():
    clock = FakeClock()
    cache = TTLCache(ttl_seconds=10, clock=clock)
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    assert cache.get_or_compute("k", compute) == 1
    clock.t = 10.0  # exactly at TTL is already stale
    assert cache.get_or_compute("k", compute) == 2
    assert calls["n"] == 2


def test_distinct_keys_are_independent():
    cache = TTLCache(ttl_seconds=10, clock=FakeClock())
    assert cache.get_or_compute(("ks", "a"), lambda: "A") == "A"
    assert cache.get_or_compute(("ks", "b"), lambda: "B") == "B"
    assert cache.get_or_compute(("ks", "a"), lambda: "X") == "A"  # still cached


def test_non_positive_ttl_disables_caching():
    cache = TTLCache(ttl_seconds=0, clock=FakeClock())
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    assert cache.get_or_compute("k", compute) == 1
    assert cache.get_or_compute("k", compute) == 2  # never cached
    assert calls["n"] == 2


def test_eviction_keeps_cache_bounded():
    clock = FakeClock()
    cache = TTLCache(ttl_seconds=1000, max_entries=3, clock=clock)
    for i in range(6):
        clock.t = float(i)
        cache.get_or_compute(i, lambda i=i: i)
    # never grows past the cap; the most recent key is still present
    assert len(cache._store) <= 3
    assert 5 in cache._store


def test_clear_forces_recompute():
    cache = TTLCache(ttl_seconds=1000, clock=FakeClock())
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    assert cache.get_or_compute("k", compute) == 1
    cache.clear()
    assert cache.get_or_compute("k", compute) == 2
