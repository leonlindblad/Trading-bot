"""Tests for the paper trading connector."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.connectors.base import Market, Order, OrderStatus, OrderType, Side
from src.connectors.paper import PaperConnector
from src.event_bus import EventBus


@pytest.mark.asyncio
async def test_market_buy_order(paper_connector):
    """Market buy should fill immediately and update position."""
    order = Order(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        market=Market.CRYPTO,
    )

    result = await paper_connector.place_order(order)

    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == Decimal("0.1")
    assert result.filled_price > Decimal("0")
    assert result.fees > Decimal("0")

    # Check position was created
    positions = await paper_connector.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "BTC/USDT"
    assert positions[0].quantity == Decimal("0.1")


@pytest.mark.asyncio
async def test_market_sell_order(paper_connector):
    """Market sell should reduce position and increase cash."""
    # Buy first
    buy = Order(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        market=Market.CRYPTO,
    )
    await paper_connector.place_order(buy)

    initial_cash = paper_connector.cash

    # Then sell
    sell = Order(
        symbol="BTC/USDT",
        side=Side.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        market=Market.CRYPTO,
    )
    result = await paper_connector.place_order(sell)

    assert result.status == OrderStatus.FILLED
    assert paper_connector.cash > initial_cash


@pytest.mark.asyncio
async def test_slippage_applied(paper_connector):
    """Buy price should be slightly higher due to slippage."""
    order = Order(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        market=Market.CRYPTO,
    )
    result = await paper_connector.place_order(order)

    # Fill price should be >= current price (slippage for buys)
    assert result.filled_price >= Decimal("60000")


@pytest.mark.asyncio
async def test_insufficient_balance_rejected(event_bus):
    """Order exceeding cash balance should be rejected."""
    connector = PaperConnector(
        market=Market.CRYPTO,
        event_bus=event_bus,
        initial_balance=Decimal("100"),
    )
    await connector.connect()
    connector.set_price("BTC/USDT", Decimal("60000"))

    order = Order(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        market=Market.CRYPTO,
    )
    result = await connector.place_order(order)

    assert result.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_limit_order_pending(paper_connector):
    """Limit order below current price should be pending."""
    order = Order(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("50000"),  # Below current 60000
        market=Market.CRYPTO,
    )
    result = await paper_connector.place_order(order)

    assert result.status == OrderStatus.PENDING
    assert paper_connector.pending_order_count == 1


@pytest.mark.asyncio
async def test_limit_order_immediate_fill(paper_connector):
    """Limit buy at or above current price should fill immediately."""
    order = Order(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("65000"),  # Above current 60000
        market=Market.CRYPTO,
    )
    result = await paper_connector.place_order(order)

    assert result.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_cancel_order(paper_connector):
    """Cancelling a pending order should work."""
    order = Order(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("50000"),
        market=Market.CRYPTO,
    )
    result = await paper_connector.place_order(order)

    assert paper_connector.pending_order_count == 1
    cancelled = await paper_connector.cancel_order(order.order_id)
    assert cancelled is True
    assert paper_connector.pending_order_count == 0


@pytest.mark.asyncio
async def test_balance_accounting(paper_connector):
    """Balance should reflect trades correctly."""
    initial_balance = await paper_connector.get_balance()
    initial_equity = initial_balance.total_equity

    order = Order(
        symbol="BTC/USDT",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        market=Market.CRYPTO,
    )
    await paper_connector.place_order(order)

    balance = await paper_connector.get_balance()
    # Total equity should be approximately the same (minus fees/slippage)
    diff = abs(balance.total_equity - initial_equity)
    assert diff < Decimal("100")  # Within reasonable fee/slippage range

    # Cash should be reduced
    assert balance.available_cash < initial_equity


@pytest.mark.asyncio
async def test_multiple_positions(paper_connector):
    """Should track multiple positions correctly."""
    for symbol in ["BTC/USDT", "ETH/USDT"]:
        order = Order(
            symbol=symbol,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            market=Market.CRYPTO,
        )
        await paper_connector.place_order(order)

    positions = await paper_connector.get_positions()
    assert len(positions) == 2
    symbols = {p.symbol for p in positions}
    assert symbols == {"BTC/USDT", "ETH/USDT"}
