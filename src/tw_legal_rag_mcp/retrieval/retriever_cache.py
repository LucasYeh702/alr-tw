from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DemoRetrieverCache:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._hits = 0
        self._misses = 0

    def get_or_set(
        self,
        corpus: str,
        query: str,
        loader: Callable[[], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        key = (corpus, query)
        if key in self._cache:
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        self._cache[key] = loader()
        return self._cache[key]

    def stats(self) -> dict[str, int | bool]:
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "persistent": False,
        }
