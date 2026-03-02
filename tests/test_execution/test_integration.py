"""Integration test — full signal-to-fill pipeline."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio

from src.config import RiskConfig
from src.connectors.base import Market, Side
from src.connectors.paper import PaperConnector
from src.event_bus import Event, EventBus, EventType
from src.execution.engine import ExecutionEngine
from src.execution.order_manager import OrderManager
from src.portfolio.manager import PortfolioManager
from src.risk.circuit_breakers import CircuitBreakerManager
from src.risk.manager import RiskManager


@pytest.mark.asyncio
async def test_full_pipeline():
    """Test the complete flow: signal → risk → execution → fill → portfolio."""
    # Setup
    event_bus = EventBus()

    connector = PaperConnector(
        market=Market.CRYPTO,
        event_bus=event_bus,
        initial_balance=Decimal("10000"),
        slippage_pct=Decimal("0.0005"),
        fee_pct=Decimal("0.001"),
    )
    await connector.connect()
    connector.set_price("BTC/USDT", Decimal("100"))

    portfolio = PortfolioManager(event_bus=event_bus, initial_cash=Decimal("10000"))
    await portfolio.start()

    circuit_breakers = CircuitBreakerManager(event_bus)
    risk_config = RiskConfig(
        {
            "per_trade_max_pct": 10,
            "per_asset_max_pct": 50,
            "per_market_max_pct": 80,
            "daily_loss_limit_pct": 5,
            "weekly_loss_limit_pct": 10,
            "max_open_positions": 15,
            "max_concurrent_orders_per_exchange": 5,
            "cash_reserve_pct": 10,
        }
    )

    risk_manager = RiskManager(event_bus, portfolio, risk_config, circuit_breakers)
    await risk_manager.start()

    order_manager = OrderManager(event_bus)
    await order_manager.start()

    execution_engine = ExecutionEngine(
        event_bus=event_bus,
        connectors={Market.CRYPTO.value: connector},
    )
    await execution_engine.start()

    # Track events
    fills = []

    async def track_fill(event: Event):
        fills.append(event)

    await event_bus.subscribe(EventType.ORDER_FILLED, track_fill)

    # Emit a signal (this triggers the full pipeline)
    await event_bus.publish(
        Event(
            event_type=EventType.SIGNAL_GENERATED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": "5",
                "market": "crypto",
                "strategy": "momentum",
                "price": "100",
            },
        )
    )

    # Verify the pipeline completed
    # 1. Order should have been filled (fills from connector + our listener)
    assert len(fills) >= 1

    # 2. Portfolio should show the position
    positions = portfolio.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "BTC/USDT"

    # 3. Cash should be reduced
    assert portfolio.get_cash_balance() < Decimal("10000")

    # 4. Order manager should have recorded the fill
    filled_orders = order_manager.get_filled_orders()
    assert len(filled_orders) >= 1

    await connector.disconnect()


@pytest.mark.asyncio
async def test_pipeline_risk_rejection():
    """Test that risk rejection prevents execution."""
    event_bus = EventBus()

    connector = PaperConnector(
        market=Market.CRYPTO,
        event_bus=event_bus,
        initial_balance=Decimal("100"),  # Very small balance
    )
    await connector.connect()
    connector.set_price("BTC/USDT", Decimal("60000"))

    portfolio = PortfolioManager(event_bus=event_bus, initial_cash=Decimal("100"))
    await portfolio.start()

    circuit_breakers = CircuitBreakerManager(event_bus)
    risk_config = RiskConfig()

    risk_manager = RiskManager(event_bus, portfolio, risk_config, circuit_breakers)
    await risk_manager.start()

    execution_engine = ExecutionEngine(
        event_bus=event_bus,
        connectors={Market.CRYPTO.value: connector},
    )
    await execution_engine.start()

    rejections = []

    async def track_rejection(event: Event):
        rejections.append(event)

    await event_bus.subscribe(EventType.ORDER_REJECTED, track_rejection)

    # Emit a signal that should be rejected (too expensive for balance)
    await event_bus.publish(
        Event(
            event_type=EventType.SIGNAL_GENERATED,
            data={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "quantity": "1",
                "market": "crypto",
                "strategy": "test",
                "price": "60000",
            },
        )
    )

    # Should have been rejected
    assert len(rejections) >= 1

    # No positions should exist
    positions = portfolio.get_positions()
    assert len(positions) == 0

    await connector.disconnect()
