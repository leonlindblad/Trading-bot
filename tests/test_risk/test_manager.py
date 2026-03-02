"""Tests for the risk management engine — targeting 100% coverage."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio

from src.connectors.base import Market, Order, OrderType, Side
from src.event_bus import EventBus
from src.portfolio.manager import PortfolioManager
from src.risk.circuit_breakers import CircuitBreakerManager
from src.risk.manager import RiskManager


def _make_order(
    symbol="BTC/USDT",
    side=Side.BUY,
    quantity=Decimal("0.01"),
    market=Market.CRYPTO,
    price=None,
):
    return Order(
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        market=market,
        price=price,
    )


@pytest_asyncio.fixture
async def risk_manager(event_bus, portfolio, circuit_breakers, risk_config):
    rm = RiskManager(event_bus, portfolio, risk_config, circuit_breakers)
    await rm.start()
    return rm


@pytest.mark.asyncio
async def test_valid_trade_approved(risk_manager, portfolio):
    """A small trade within all limits should be approved."""
    # Set a current price so risk manager can estimate
    from src.event_bus import Event, EventType

    await portfolio.event_bus.publish(
        Event(
            event_type=EventType.PRICE_UPDATE,
            data={"symbol": "BTC/USDT", "price": "100", "market": "crypto"},
        )
    )

    order = _make_order(quantity=Decimal("1"), price=Decimal("100"))
    decision = risk_manager.validate_trade(order)
    assert decision.approved


@pytest.mark.asyncio
async def test_sell_always_approved(risk_manager):
    """Sell orders should pass most checks regardless."""
    order = _make_order(side=Side.SELL, quantity=Decimal("100"))
    decision = risk_manager.validate_trade(order)
    assert decision.approved


@pytest.mark.asyncio
async def test_circuit_breaker_rejects(risk_manager, circuit_breakers):
    """All trades rejected when circuit breaker is tripped."""
    await circuit_breakers.trip("test")
    order = _make_order(quantity=Decimal("0.001"), price=Decimal("100"))
    decision = risk_manager.validate_trade(order)
    assert not decision.approved
    assert "Circuit breaker" in decision.reason


@pytest.mark.asyncio
async def test_insufficient_cash_rejected(risk_manager, portfolio):
    """Trade exceeding cash balance should be rejected."""
    order = _make_order(quantity=Decimal("1000"), price=Decimal("100"))
    # 1000 * 100 = 100,000 > 10,000 cash
    decision = risk_manager.validate_trade(order)
    assert not decision.approved
    assert "Insufficient cash" in decision.reason


@pytest.mark.asyncio
async def test_per_asset_limit(risk_manager, portfolio, event_bus):
    """Should reject when per-asset exposure exceeds 15%."""
    from src.event_bus import Event, EventType

    # Simulate a large existing position
    await event_bus.publish(
        Event(
            event_type=EventType.ORDER_FILLED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "quantity": "15",
                "price": "100",
                "fees": "0",
                "market": "crypto",
                "strategy": "test",
            },
        )
    )

    # Try to add more — should exceed 15% of portfolio
    order = _make_order(quantity=Decimal("5"), price=Decimal("100"))
    decision = risk_manager.validate_trade(order)
    assert not decision.approved
    assert "Per-asset limit" in decision.reason


@pytest.mark.asyncio
async def test_max_open_positions(risk_manager, portfolio, event_bus):
    """Should reject new positions when at max."""
    from src.event_bus import Event, EventType
    from src.config import RiskConfig

    risk_manager.config = RiskConfig({"max_open_positions": 2, "cash_reserve_pct": 0, "per_asset_max_pct": 100, "per_market_max_pct": 100, "per_trade_max_pct": 100})

    # Create 2 positions
    for i, sym in enumerate(["AAA", "BBB"]):
        await event_bus.publish(
            Event(
                event_type=EventType.ORDER_FILLED,
                data={
                    "symbol": sym,
                    "side": "BUY",
                    "quantity": "1",
                    "price": "10",
                    "fees": "0",
                    "market": "crypto",
                    "strategy": "test",
                },
            )
        )

    # Third should be rejected
    order = _make_order(symbol="CCC", quantity=Decimal("1"), price=Decimal("10"))
    decision = risk_manager.validate_trade(order)
    assert not decision.approved
    assert "Max open positions" in decision.reason


@pytest.mark.asyncio
async def test_cash_reserve_enforced(risk_manager, portfolio):
    """Should reject trades that would breach cash reserve."""
    # Temporarily raise per-asset and per-market limits so cash reserve is the binding constraint
    from src.config import RiskConfig
    risk_manager.config = RiskConfig({
        "per_trade_max_pct": 100,
        "per_asset_max_pct": 100,
        "per_market_max_pct": 100,
        "daily_loss_limit_pct": 100,
        "weekly_loss_limit_pct": 100,
        "max_open_positions": 100,
        "max_concurrent_orders_per_exchange": 100,
        "cash_reserve_pct": 20,
    })
    # Cash reserve is 20% of equity (10000), so min cash = 2000
    # Trying to spend 9000 of 10000 cash should fail (only 8000 available)
    order = _make_order(quantity=Decimal("90"), price=Decimal("100"))
    decision = risk_manager.validate_trade(order)
    assert not decision.approved
    assert "Cash reserve" in decision.reason


@pytest.mark.asyncio
async def test_max_concurrent_orders(risk_manager):
    """Should reject when pending orders per exchange exceed limit."""
    risk_manager._pending_orders_per_exchange["crypto"] = 5

    order = _make_order(quantity=Decimal("0.01"), price=Decimal("100"))
    decision = risk_manager.validate_trade(order)
    assert not decision.approved
    assert "Max concurrent orders" in decision.reason
