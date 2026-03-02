"""Execution engine — routes approved orders to the correct connector."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from loguru import logger

from src.connectors.base import (
    BaseConnector,
    Market,
    Order,
    OrderResult,
    OrderStatus,
    OrderType,
    Side,
)
from src.event_bus import Event, EventBus, EventType


class ExecutionEngine:
    """Routes approved orders to the correct market connector.

    Subscribes to ORDER_APPROVED events, dispatches to connectors,
    and publishes ORDER_FILLED events on success.
    """

    def __init__(
        self,
        event_bus: EventBus,
        connectors: dict[str, BaseConnector],
        max_retries: int = 3,
    ):
        self.event_bus = event_bus
        self.connectors = connectors
        self._max_retries = max_retries

    async def start(self) -> None:
        """Subscribe to approved order events."""
        await self.event_bus.subscribe(
            EventType.ORDER_APPROVED, self._on_order_approved
        )

    async def _on_order_approved(self, event: Event) -> None:
        """Route an approved order to the correct connector."""
        data = event.data
        market_str = data.get("market", "crypto")

        order = Order(
            symbol=data["symbol"],
            side=Side(data["side"]),
            order_type=OrderType(data.get("order_type", "MARKET")),
            quantity=Decimal(str(data["quantity"])),
            market=Market(market_str),
            strategy=data.get("strategy", ""),
            price=Decimal(str(data["price"])) if data.get("price") else None,
            stop_loss=Decimal(str(data["stop_loss"])) if data.get("stop_loss") else None,
        )

        if "order_id" in data:
            order.order_id = data["order_id"]

        connector = self._get_connector(market_str)
        if connector is None:
            logger.error(f"No connector found for market: {market_str}")
            return

        result = await self._execute_with_retry(connector, order)

        if result and result.status == OrderStatus.FILLED:
            logger.info(
                f"Order filled: {order.side.value} {result.filled_quantity} "
                f"{order.symbol} @ {result.filled_price}"
            )
        elif result and result.status == OrderStatus.REJECTED:
            logger.warning(f"Order rejected by connector: {order.symbol}")
        elif result and result.status == OrderStatus.PENDING:
            logger.info(f"Limit order placed: {order.symbol} @ {order.price}")

    def _get_connector(self, market: str) -> BaseConnector | None:
        """Get the connector for a given market."""
        # Try exact market match first
        if market in self.connectors:
            return self.connectors[market]
        # Try paper connector as fallback
        paper_key = f"paper_{market}"
        if paper_key in self.connectors:
            return self.connectors[paper_key]
        # Try any available connector
        for key, conn in self.connectors.items():
            if conn.market.value == market:
                return conn
        return None

    async def _execute_with_retry(
        self, connector: BaseConnector, order: Order
    ) -> OrderResult | None:
        """Execute an order with exponential backoff retry."""
        last_error = None

        for attempt in range(self._max_retries):
            try:
                result = await connector.place_order(order)
                return result
            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(
                    f"Execution attempt {attempt + 1}/{self._max_retries} failed "
                    f"for {order.symbol}: {e}. Retrying in {wait_time}s..."
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(wait_time)

        logger.error(
            f"Order execution failed after {self._max_retries} attempts "
            f"for {order.symbol}: {last_error}"
        )
        return None
