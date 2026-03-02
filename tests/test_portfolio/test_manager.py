"""Tests for portfolio manager."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.connectors.base import Market
from src.event_bus import Event, EventType


@pytest.mark.asyncio
async def test_buy_creates_position(portfolio, event_bus):
    """Buy fill should create a new position."""
    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_FILLED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "quantity": "1",
                "price": "100",
                "fees": "1",
                "market": "crypto",
                "strategy": "test",
            },
        )
    )

    positions = portfolio.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "BTC/USDT"
    assert positions[0].quantity == Decimal("1")


@pytest.mark.asyncio
async def test_sell_closes_position(portfolio, event_bus):
    """Sell fill should close position."""
    # Buy first
    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_FILLED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "quantity": "1",
                "price": "100",
                "fees": "0",
                "market": "crypto",
                "strategy": "test",
            },
        )
    )

    # Then sell
    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_FILLED,
            data={
                "symbol": "BTC/USDT",
                "side": "SELL",
                "quantity": "1",
                "price": "110",
                "fees": "0",
                "market": "crypto",
                "strategy": "test",
            },
        )
    )

    positions = portfolio.get_positions()
    assert len(positions) == 0


@pytest.mark.asyncio
async def test_cash_tracking(portfolio, event_bus):
    """Cash should decrease on buy and increase on sell."""
    initial = portfolio.get_cash_balance()

    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_FILLED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "quantity": "1",
                "price": "100",
                "fees": "1",
                "market": "crypto",
                "strategy": "test",
            },
        )
    )

    assert portfolio.get_cash_balance() == initial - Decimal("101")  # 100 + 1 fee


@pytest.mark.asyncio
async def test_price_update_updates_pnl(portfolio, event_bus):
    """Price updates should recalculate unrealised P&L."""
    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_FILLED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "quantity": "1",
                "price": "100",
                "fees": "0",
                "market": "crypto",
                "strategy": "test",
            },
        )
    )

    # Price goes up
    await event_bus.publish(
        Event(
            event_type=EventType.PRICE_UPDATE,
            data={"symbol": "BTC/USDT", "price": "110", "market": "crypto"},
        )
    )

    pos = portfolio.get_position("BTC/USDT")
    assert pos is not None
    assert pos.unrealised_pnl == Decimal("10")  # (110 - 100) * 1


@pytest.mark.asyncio
async def test_market_exposure(portfolio, event_bus):
    """Market exposure should sum all positions in a market."""
    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_FILLED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "quantity": "1",
                "price": "100",
                "fees": "0",
                "market": "crypto",
                "strategy": "test",
            },
        )
    )

    exposure = portfolio.get_market_exposure(Market.CRYPTO)
    assert exposure == Decimal("100")


@pytest.mark.asyncio
async def test_trade_history(portfolio, event_bus):
    """Trades should be recorded in history."""
    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_FILLED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "quantity": "1",
                "price": "100",
                "fees": "0",
                "market": "crypto",
                "strategy": "momentum",
            },
        )
    )

    trades = portfolio.get_trades()
    assert len(trades) == 1
    assert trades[0]["symbol"] == "BTC/USDT"
    assert trades[0]["strategy"] == "momentum"
