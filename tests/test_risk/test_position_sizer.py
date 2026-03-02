"""Tests for position sizing logic."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio

from src.connectors.base import Market, Side
from src.event_bus import EventBus
from src.portfolio.manager import PortfolioManager
from src.risk.position_sizer import PositionSizer


@pytest_asyncio.fixture
async def sizer(event_bus, portfolio, risk_config):
    return PositionSizer(risk_config, portfolio)


@pytest.mark.asyncio
async def test_basic_sizing(sizer):
    """Should calculate size based on strategy percentage."""
    size = sizer.calculate_size(
        symbol="BTC/USDT",
        side=Side.BUY,
        market=Market.CRYPTO,
        price=Decimal("100"),
        strategy_pct=Decimal("2"),
    )

    # 2% of 10000 = 200, 200/100 = 2
    assert size == Decimal("2.00000000")


@pytest.mark.asyncio
async def test_cash_reserve_limits_size(sizer):
    """Should respect cash reserve when sizing."""
    # Cash reserve is 20% of 10000 = 2000
    # Available for trading = 10000 - 2000 = 8000
    size = sizer.calculate_size(
        symbol="BTC/USDT",
        side=Side.BUY,
        market=Market.CRYPTO,
        price=Decimal("100"),
        strategy_pct=Decimal("100"),  # Try to use 100% of portfolio
    )

    # Should be limited by cash reserve
    assert size <= Decimal("80")  # 8000 / 100


@pytest.mark.asyncio
async def test_sell_returns_position_quantity(sizer, portfolio, event_bus):
    """Sell sizing should return the current position quantity."""
    from src.event_bus import Event, EventType

    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_FILLED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "quantity": "5",
                "price": "100",
                "fees": "0",
                "market": "crypto",
                "strategy": "test",
            },
        )
    )

    size = sizer.calculate_size(
        symbol="BTC/USDT",
        side=Side.SELL,
        market=Market.CRYPTO,
        price=Decimal("100"),
    )
    assert size == Decimal("5")


@pytest.mark.asyncio
async def test_zero_price_returns_zero(sizer):
    """Should return 0 for zero or negative price."""
    size = sizer.calculate_size(
        symbol="BTC/USDT",
        side=Side.BUY,
        market=Market.CRYPTO,
        price=Decimal("0"),
    )
    assert size == Decimal("0")


@pytest.mark.asyncio
async def test_size_never_negative(sizer):
    """Size should never be negative."""
    size = sizer.calculate_size(
        symbol="BTC/USDT",
        side=Side.BUY,
        market=Market.CRYPTO,
        price=Decimal("1000000"),  # Very expensive
    )
    assert size >= Decimal("0")
