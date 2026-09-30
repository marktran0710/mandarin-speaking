"""Reusable reference features, so a teacher recording is analysed once.

Keyed by the recording's content hash, the script text and the pipeline
version: replacing the audio, editing the sentence or upgrading the extractor
each produce a new key, so a stale entry can never be served. The in-memory
store is per process; ``ReferenceFeatureStore`` is the seam for a persistent
(database) store without touching the evaluator.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Hashable, Optional, Protocol

from domain.pronunciation.types import UtteranceFeatures

DEFAULT_CAPACITY = 256


class ReferenceFeatureStore(Protocol):
    def get(self, key: Hashable) -> Optional[UtteranceFeatures]: ...

    def put(self, key: Hashable, features: UtteranceFeatures) -> None: ...


class InMemoryReferenceStore:
    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._capacity = capacity
        self._items: "OrderedDict[Hashable, UtteranceFeatures]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Optional[UtteranceFeatures]:
        with self._lock:
            features = self._items.get(key)
            if features is not None:
                self._items.move_to_end(key)
            return features

    def put(self, key: Hashable, features: UtteranceFeatures) -> None:
        with self._lock:
            self._items[key] = features
            self._items.move_to_end(key)
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)


default_reference_store: ReferenceFeatureStore = InMemoryReferenceStore()
