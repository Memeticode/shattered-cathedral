"""Thread-safe SSE event system for the real-time demo."""
from __future__ import annotations

import json
import queue
from dataclasses import dataclass, field
from enum import Enum


class EventType(Enum):
    ITERATION_START = "iteration_start"
    RENDER_PROGRESS = "render_progress"
    RENDER_COMPLETE = "render_complete"
    CONFIG_READY = "config_ready"
    METRICS_READY = "metrics_ready"
    EVALUATION_READY = "evaluation_ready"
    VISUALIZATION_READY = "visualization_ready"
    SESSION_COMPLETE = "session_complete"
    ERROR = "error_event"


@dataclass
class DemoEvent:
    event_type: EventType
    iteration: int
    data: dict = field(default_factory=dict)

    def to_sse(self) -> str:
        payload = json.dumps({"iteration": self.iteration, **self.data})
        return f"event: {self.event_type.value}\ndata: {payload}\n\n"


class EventBus:
    """Publish/subscribe bus for streaming events to SSE clients."""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[DemoEvent]] = []

    def subscribe(self) -> queue.Queue[DemoEvent]:
        q: queue.Queue[DemoEvent] = queue.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[DemoEvent]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def publish(self, event: DemoEvent) -> None:
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # drop if consumer is too slow
