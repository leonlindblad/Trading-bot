"""Tests for the event bus pub/sub system."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from src.event_bus import Event, EventBus, EventType


@pytest.mark.asyncio
async def test_subscribe_and_publish(event_bus):
    """Test basic subscribe/publish round trip."""
    received = []

    async def handler(event: Event):
        received.append(event)

    await event_bus.subscribe(EventType.PRICE_UPDATE, handler)
    event = Event(event_type=EventType.PRICE_UPDATE, data={"symbol": "BTC/USDT", "price": "60000"})
    await event_bus.publish(event)

    assert len(received) == 1
    assert received[0].data["symbol"] == "BTC/USDT"


@pytest.mark.asyncio
async def test_multiple_subscribers(event_bus):
    """Multiple handlers should all receive the same event."""
    results_a = []
    results_b = []

    async def handler_a(event: Event):
        results_a.append(event)

    async def handler_b(event: Event):
        results_b.append(event)

    await event_bus.subscribe(EventType.ORDER_FILLED, handler_a)
    await event_bus.subscribe(EventType.ORDER_FILLED, handler_b)

    event = Event(event_type=EventType.ORDER_FILLED, data={"order_id": "123"})
    await event_bus.publish(event)

    assert len(results_a) == 1
    assert len(results_b) == 1


@pytest.mark.asyncio
async def test_unsubscribe(event_bus):
    """Unsubscribed handler should not receive events."""
    received = []

    async def handler(event: Event):
        received.append(event)

    await event_bus.subscribe(EventType.PRICE_UPDATE, handler)
    await event_bus.unsubscribe(EventType.PRICE_UPDATE, handler)

    event = Event(event_type=EventType.PRICE_UPDATE, data={"test": True})
    await event_bus.publish(event)

    assert len(received) == 0


@pytest.mark.asyncio
async def test_error_isolation(event_bus):
    """A failing handler should not prevent other handlers from receiving events."""
    received = []

    async def failing_handler(event: Event):
        raise ValueError("Intentional error")

    async def good_handler(event: Event):
        received.append(event)

    await event_bus.subscribe(EventType.PRICE_UPDATE, failing_handler)
    await event_bus.subscribe(EventType.PRICE_UPDATE, good_handler)

    event = Event(event_type=EventType.PRICE_UPDATE, data={"test": True})
    await event_bus.publish(event)

    assert len(received) == 1


@pytest.mark.asyncio
async def test_event_history(event_bus):
    """Event history should record published events."""
    for i in range(5):
        await event_bus.publish(
            Event(event_type=EventType.PRICE_UPDATE, data={"i": i})
        )

    history = event_bus.get_history()
    assert len(history) == 5

    # Filter by type
    await event_bus.publish(
        Event(event_type=EventType.ORDER_FILLED, data={"order": "test"})
    )
    price_history = event_bus.get_history(EventType.PRICE_UPDATE)
    assert len(price_history) == 5


@pytest.mark.asyncio
async def test_no_duplicate_subscribe(event_bus):
    """Subscribing the same handler twice should not result in duplicate calls."""
    received = []

    async def handler(event: Event):
        received.append(event)

    await event_bus.subscribe(EventType.PRICE_UPDATE, handler)
    await event_bus.subscribe(EventType.PRICE_UPDATE, handler)

    event = Event(event_type=EventType.PRICE_UPDATE, data={})
    await event_bus.publish(event)

    assert len(received) == 1


@pytest.mark.asyncio
async def test_different_event_types_isolated(event_bus):
    """Handlers for different event types should not interfere."""
    price_events = []
    order_events = []

    async def price_handler(event: Event):
        price_events.append(event)

    async def order_handler(event: Event):
        order_events.append(event)

    await event_bus.subscribe(EventType.PRICE_UPDATE, price_handler)
    await event_bus.subscribe(EventType.ORDER_FILLED, order_handler)

    await event_bus.publish(
        Event(event_type=EventType.PRICE_UPDATE, data={"price": "100"})
    )

    assert len(price_events) == 1
    assert len(order_events) == 0
