"""Bounded in-process fanout for the Studio event stream."""

from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Lock
from typing import Any, Callable


StudioEvent = tuple[str, dict[str, Any]]
EventFilter = Callable[[str, dict[str, Any]], bool]


class EventBus:
    def __init__(self, *, queue_size: int = 64) -> None:
        if queue_size < 1:
            raise ValueError("event queues must have positive capacity")
        self._queue_size = queue_size
        self._subscribers: dict[Queue[StudioEvent], EventFilter | None] = {}
        self._lock = Lock()
        self._seq = 0

    def subscribe(self, accepts: EventFilter | None = None) -> Queue[StudioEvent]:
        subscriber: Queue[StudioEvent] = Queue(self._queue_size)
        with self._lock:
            self._subscribers[subscriber] = accepts
        return subscriber

    def unsubscribe(self, subscriber: Queue[StudioEvent]) -> None:
        with self._lock:
            self._subscribers.pop(subscriber, None)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            event = (event_type, {**payload, "seq": self._seq})
            for subscriber, accepts in self._subscribers.items():
                if accepts is not None and not accepts(*event):
                    continue
                try:
                    subscriber.put_nowait(event)
                except Full:
                    while True:
                        try:
                            subscriber.get_nowait()
                        except Empty:
                            break
                        subscriber.task_done()
                    subscriber.put_nowait(("studio.resync", {"seq": self._seq}))
