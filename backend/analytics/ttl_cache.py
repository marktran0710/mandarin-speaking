"""A tiny thread-safe TTL memo cache for expensive, read-only computations.

The admin analytics endpoints recompute PFA/BKT models (and, for the audit,
scan every quiz attempt) on each request even though the underlying data
changes slowly. Memoising the computed result for a short window avoids the
repeat work when a dashboard refreshes or several views load at once, without
changing what is returned - a hit replays the exact value the compute produced.

Deliberately simple: process-local (each worker keeps its own), TTL-bounded
staleness rather than write-invalidation, and the heavy compute runs OUTSIDE
the lock so concurrent callers never serialise behind one another.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Hashable


class TTLCache:
    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max(1, max_entries)
        self._clock = clock
        self._lock = threading.Lock()
        self._store: dict[Hashable, tuple[float, Any]] = {}

    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        """Return the cached value for ``key`` if fresh, else compute and store it.

        A non-positive TTL disables caching entirely, so it can be turned off
        with an env var without touching call sites.
        """
        if self._ttl <= 0:
            return compute()

        now = self._clock()
        with self._lock:
            hit = self._store.get(key)
            if hit is not None and now - hit[0] < self._ttl:
                return hit[1]

        # Compute outside the lock: a cold key must not block other keys, and a
        # slow compute must not hold the lock. Two callers racing the same cold
        # key both compute once; the last write wins, which is harmless here.
        value = compute()

        with self._lock:
            self._store[key] = (self._clock(), value)
            if len(self._store) > self._max:
                self._evict_locked(now)
        return value

    def _evict_locked(self, now: float) -> None:
        # Drop everything already expired first; only then trim the oldest live
        # entries until back under the cap.
        for key in [k for k, (ts, _) in self._store.items() if now - ts >= self._ttl]:
            self._store.pop(key, None)
        while len(self._store) > self._max:
            oldest = min(self._store, key=lambda k: self._store[k][0])
            self._store.pop(oldest, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
