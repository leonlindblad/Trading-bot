"""Central event bus for inter-component communication using pub/sub pattern."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable
from uuid import uuid4

from loguru import logger


class EventType(str, Enum):
    """All event types in the system."""

    PRICE_UPDATE = "price_update"
    SIGNAL_GENERATED = "signal_generated"
    ORDER_APPROVED = "order_approved"
    ORDER_REJECTED = "order_rejected"
    ORDER_FILLED = "order_filled"
    RISK_BREACH = "risk_breach"
    HEALTH_CHECK = "health_check"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker_triggered"
    STRATEGY_STATE_CHANGED = "strategy_state_changed"


@dataclass
class Event:
    """Typed event envelope."""

    event_type: EventType
    data: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source: str = ""


# Type alias for event handlers
EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """Async pub/sub event bus. All components communicate through this."""

    def __init__(self, history_size: int = 1000):
        self._subscribers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._history: deque[Event] = deque(maxlen=history_size)
        self._lock = asyncio.Lock()

    async def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Register an async handler for an event type."""
        async with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    async def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove a handler for an event type."""
        async with self._lock:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass

    async def publish(self, event: Event) -> None:
        """Dispatch event to all subscribers. Errors in one handler don't affect others."""
        self._history.append(event)

        async with self._lock:
            handlers = list(self._subscribers.get(event.event_type, []))

        if not handlers:
            return

        results = await asyncio.gather(
            *[self._safe_call(handler, event) for handler in handlers],
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"Event handler error for {event.event_type}: {result}"
                )

    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        """Call a handler, catching and logging any exceptions."""
        try:
            await handler(event)
        except Exception as e:
            logger.error(
                f"Handler {handler.__name__} failed for {event.event_type}: {e}"
            )
            raise

    def get_history(
        self,
        event_type: EventType | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get recent events, optionally filtered by type."""
        events = list(self._history)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()
