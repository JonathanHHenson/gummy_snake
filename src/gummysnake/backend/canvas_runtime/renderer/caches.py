"""Small renderer-owned cache helpers."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Hashable


class LruCache[K: Hashable, V]:
    """Bounded least-recently-used cache for renderer-side derived payloads."""

    def __init__(self, limit: int) -> None:
        if limit <= 0:
            raise ValueError("LruCache limit must be positive.")
        self._limit = int(limit)
        self._items: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        """Get.
        
        Args:
            key: The key value. Expected type: `K`.
        
        Returns:
            The return value. Type: `V | None`.
        """
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
        return value

    def set(self, key: K, value: V) -> bool:
        """Set.
        
        Args:
            key: The key value. Expected type: `K`.
            value: The value value. Expected type: `V`.
        
        Returns:
            The return value. Type: `bool`.
        """
        self._items[key] = value
        self._items.move_to_end(key)
        if len(self._items) <= self._limit:
            return False
        self._items.popitem(last=False)
        return True

    def clear(self) -> None:
        """Clear.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._items.clear()
