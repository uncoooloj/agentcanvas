"""Bounded in-process fanout for the Studio event stream."""

from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Lock
from typing import Any


StudioEvent = tuple[str, dict[str, Any]]


class EventBus:
    def __init__(self, *, queue_size: int = 64) -> None:
        if queue_size < 1:
            raise ValueError("event queues must have positive capacity")
        self._queue_size = queue_size
        self._subscribers: set[Queue[StudioEvent]] = set()
        self._lock = Lock()

    def subscribe(self) -> Queue[StudioEvent]:
        subscriber: Queue[StudioEvent] = Queue(self._queue_size)
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Queue[StudioEvent]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = (event_type, payload)
        with self._lock:
            for subscriber in self._subscribers:
                try:
                    subscriber.put_nowait(event)
                except Full:
                    try:
                        subscriber.get_nowait()
                        subscriber.task_done()
                    except Empty:
                        pass  # The consumer freed space before we could drop an event.
                    subscriber.put_nowait(event)
