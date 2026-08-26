"""
The event transport: one thread-safe queue, drained by whoever is watching.

SPEC §7.2 sets two opposite overflow policies, and the asymmetry is the point:

  ASR input   blocks on full   -- a gap in the transcript is a missed trigger
  Event -> UI drops oldest     -- the UI is a view; losing a frame of it is fine

This is the second one. Drops are COUNTED and reported to the screen, because a
UI that silently skips events while claiming to be real-time is lying, and the
whole project's credibility rests on not doing that.
"""
from __future__ import annotations

import collections
import threading
from typing import Any, Dict, List, Optional


class EventQueue:
    """Bounded, thread-safe, drop-oldest. One producer, several consumers."""

    def __init__(self, maxsize: int = 1000) -> None:
        self.maxsize = maxsize
        self._items: "collections.deque" = collections.deque()
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._dropped = 0
        self._published = 0
        self._closed = False

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def published(self) -> int:
        return self._published

    def put(self, event: Dict[str, Any]) -> None:
        with self._not_empty:
            if self._closed:
                return
            while len(self._items) >= self.maxsize:
                self._items.popleft()
                self._dropped += 1
            self._items.append(event)
            self._published += 1
            self._not_empty.notify()

    def get(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        with self._not_empty:
            if not self._items and not self._closed:
                self._not_empty.wait(timeout)
            if self._items:
                return self._items.popleft()
            return None

    def drain(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = list(self._items)
            self._items.clear()
            return out

    def close(self) -> None:
        with self._not_empty:
            self._closed = True
            self._not_empty.notify_all()

    @property
    def closed(self) -> bool:
        return self._closed

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
