"""Tests for the execution engine."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio

from src.connectors.base import Market, OrderType, Side
from src.connectors.paper import PaperConnector
from src.event_bus import Event, EventBus, EventType
from src.execution.engine import ExecutionEngine


@pytest_asyncio.fixture
async def engine(event_bus, paper_connector):
    connectors = {paper_connector.market.value: paper_connector}
    engine = ExecutionEngine(event_bus=event_bus, connectors=connectors)
    await engine.start()
    return engine


@pytest.mark.asyncio
async def test_order_routing(engine, event_bus, paper_connector):
    """Approved order should be routed to the correct connector."""
    filled = []

    async def on_fill(event: Event):
        filled.append(event)

    await event_bus.subscribe(EventType.ORDER_FILLED, on_fill)

    # Publish an approved order
    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_APPROVED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": "0.01",
                "market": "crypto",
                "strategy": "test",
                "price": None,
                "stop_loss": None,
            },
        )
    )

    # The paper connector should have a position now
    positions = await paper_connector.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "BTC/USDT"


@pytest.mark.asyncio
async def test_no_connector_for_market(event_bus):
    """Should handle missing connector gracefully."""
    engine = ExecutionEngine(event_bus=event_bus, connectors={})
    await engine.start()

    # This should not crash
    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_APPROVED,
            data={
                "symbol": "AAPL",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": "1",
                "market": "us_stocks",
                "strategy": "test",
                "price": None,
                "stop_loss": None,
            },
        )
    )
    # No crash = success
