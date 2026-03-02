"""Order manager — tracks pending orders, fill status, and history."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from loguru import logger

from src.connectors.base import OrderResult, OrderStatus
from src.event_bus import Event, EventBus, EventType


class OrderManager:
    """Tracks all orders through their lifecycle."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._pending: dict[str, dict] = {}
        self._filled: list[dict] = []
        self._rejected: list[dict] = []

    async def start(self) -> None:
        """Subscribe to order events."""
        await self.event_bus.subscribe(EventType.ORDER_APPROVED, self._on_approved)
        await self.event_bus.subscribe(EventType.ORDER_FILLED, self._on_filled)
        await self.event_bus.subscribe(EventType.ORDER_REJECTED, self._on_rejected)

    async def _on_approved(self, event: Event) -> None:
        """Track a newly approved order."""
        order_id = event.data.get("order_id", event.event_id)
        self._pending[order_id] = {
            **event.data,
            "status": "approved",
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _on_filled(self, event: Event) -> None:
        """Move order from pending to filled."""
        order_id = event.data.get("order_id", "")
        fill_data = {
            **event.data,
            "status": "filled",
            "filled_at": datetime.now(timezone.utc).isoformat(),
        }

        self._pending.pop(order_id, None)
        self._filled.append(fill_data)

    async def _on_rejected(self, event: Event) -> None:
        """Record a rejected order."""
        self._rejected.append(
            {
                **event.data,
                "status": "rejected",
                "rejected_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_pending_orders(self) -> list[dict]:
        return list(self._pending.values())

    def get_pending_count(self, market: str | None = None) -> int:
        if market is None:
            return len(self._pending)
        return sum(
            1 for o in self._pending.values() if o.get("market") == market
        )

    def get_filled_orders(self, limit: int = 100) -> list[dict]:
        return self._filled[-limit:]

    def get_rejected_orders(self, limit: int = 50) -> list[dict]:
        return self._rejected[-limit:]

    def get_all_orders(self) -> dict:
        return {
            "pending": self.get_pending_orders(),
            "filled": self.get_filled_orders(),
            "rejected": self.get_rejected_orders(),
        }
