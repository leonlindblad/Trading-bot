"""Tests for the StrategyManager — the component that bridges prices to strategies."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.config import AppConfig, DCAConfig, GridConfig, MomentumConfig, RiskConfig, Settings
from src.connectors.base import Market, Side
from src.event_bus import Event, EventBus, EventType
from src.portfolio.manager import PortfolioManager
from src.risk.position_sizer import PositionSizer
from src.strategies.manager import CandleAggregator, StrategyManager


# --- CandleAggregator tests ---


def test_candle_aggregation_basic():
    """Ticks should accumulate into candles after N ticks."""
    agg = CandleAggregator()

    # First 9 ticks shouldn't close a candle
    for i in range(9):
        result = agg.add_tick("BTC/USDT", 100.0 + i)
        assert result is False

    # 10th tick should close the candle
    result = agg.add_tick("BTC/USDT", 109.0)
    assert result is True
    assert agg.candle_count("BTC/USDT") == 1


def test_candle_ohlcv_values():
    """Candle should have correct OHLCV values."""
    agg = CandleAggregator()

    prices = [100, 105, 95, 110, 90, 100, 103, 97, 106, 102]
    for price in prices:
        agg.add_tick("BTC/USDT", float(price))

    df = agg.get_dataframe("BTC/USDT")
    assert len(df) == 1
    assert df.iloc[0]["open"] == 100
    assert df.iloc[0]["high"] == 110
    assert df.iloc[0]["low"] == 90
    assert df.iloc[0]["close"] == 102


def test_candle_multiple_symbols():
    """Candle aggregation should be independent per symbol."""
    agg = CandleAggregator()

    for i in range(10):
        agg.add_tick("BTC/USDT", 100.0)

    for i in range(5):
        agg.add_tick("ETH/USDT", 50.0)

    assert agg.candle_count("BTC/USDT") == 1
    assert agg.candle_count("ETH/USDT") == 0


def test_candle_empty_dataframe():
    """Should return empty DataFrame for unknown symbol."""
    agg = CandleAggregator()
    df = agg.get_dataframe("UNKNOWN")
    assert df.empty


def test_candle_max_limit():
    """Should trim candles beyond max_candles."""
    agg = CandleAggregator(max_candles=5)

    for _ in range(100):  # 100 ticks = 10 candles
        agg.add_tick("BTC/USDT", 100.0)

    assert agg.candle_count("BTC/USDT") == 5


# --- StrategyManager tests ---


def _make_config(
    momentum_enabled=True, dca_enabled=True, grid_enabled=True
) -> AppConfig:
    """Create a test AppConfig with specific strategy settings."""
    yaml_data = {
        "strategies": {
            "momentum": {"enabled": momentum_enabled, "ema_fast": 12, "ema_slow": 26},
            "dca": {
                "enabled": dca_enabled,
                "schedule": "daily",
                "base_amount": 50,
                "allocation": {"BTC/USDT": 0.5, "ETH/USDT": 0.5},
            },
            "grid": {"enabled": grid_enabled, "num_levels": 5, "budget_per_asset_pct": 5},
        },
        "risk": {"total_budget": 10000, "cash_reserve_pct": 20},
        "assets": {
            "crypto": [
                {"symbol": "BTC/USDT", "strategies": ["momentum", "dca", "grid"]},
                {"symbol": "ETH/USDT", "strategies": ["dca"]},
            ]
        },
        "paper_trading": {"initial_balance": 10000},
    }
    return AppConfig(settings=Settings(), yaml_data=yaml_data)


def _make_manager(config=None, event_bus=None, portfolio=None):
    """Create a StrategyManager with test defaults."""
    event_bus = event_bus or EventBus()
    portfolio = portfolio or PortfolioManager(event_bus=event_bus, initial_cash=Decimal("10000"))
    config = config or _make_config()
    position_sizer = PositionSizer(config.risk, portfolio)
    return StrategyManager(
        event_bus=event_bus,
        config=config,
        portfolio=portfolio,
        position_sizer=position_sizer,
    )


@pytest.mark.asyncio
async def test_strategy_initialization():
    """StrategyManager should create strategy instances based on config."""
    manager = _make_manager()
    await manager.start()

    status = manager.get_status()
    assert status["strategies"]["momentum"]["enabled"] is True
    assert status["strategies"]["dca"]["enabled"] is True
    assert status["strategies"]["grid"]["enabled"] is True

    # BTC/USDT should be tracked by momentum
    assert "BTC/USDT" in status["strategies"]["momentum"]["symbols"]

    await manager.stop()


@pytest.mark.asyncio
async def test_disabled_strategies_not_created():
    """Disabled strategies should not be instantiated."""
    config = _make_config(momentum_enabled=False, grid_enabled=False)
    manager = _make_manager(config=config)
    await manager.start()

    status = manager.get_status()
    assert status["strategies"]["momentum"]["enabled"] is False
    assert status["strategies"]["dca"]["enabled"] is True
    assert status["strategies"]["grid"]["enabled"] is False

    await manager.stop()


@pytest.mark.asyncio
async def test_price_updates_accumulate_candles():
    """Price update events should accumulate into candles."""
    event_bus = EventBus()
    manager = _make_manager(event_bus=event_bus)
    await manager.start()

    # Send price updates
    for i in range(20):
        await event_bus.publish(
            Event(
                event_type=EventType.PRICE_UPDATE,
                data={
                    "symbol": "BTC/USDT",
                    "price": str(60000 + i * 10),
                    "market": "crypto",
                },
                source="test",
            )
        )

    status = manager.get_status()
    assert status["candle_counts"]["BTC/USDT"] == 2  # 20 ticks / 10 per candle
    assert status["eval_count"] > 0  # Strategies evaluated at least once

    await manager.stop()


@pytest.mark.asyncio
async def test_dca_generates_signal():
    """DCA strategy should generate a signal on first evaluation (never purchased before)."""
    event_bus = EventBus()
    portfolio = PortfolioManager(event_bus=event_bus, initial_cash=Decimal("10000"))
    await portfolio.start()

    manager = _make_manager(event_bus=event_bus, portfolio=portfolio)
    await manager.start()

    # Track signals
    signals_received = []

    async def capture_signal(event: Event):
        signals_received.append(event)

    await event_bus.subscribe(EventType.SIGNAL_GENERATED, capture_signal)

    # Send enough price ticks to close a candle (10 ticks)
    for i in range(10):
        await event_bus.publish(
            Event(
                event_type=EventType.PRICE_UPDATE,
                data={
                    "symbol": "BTC/USDT",
                    "price": str(60000 + i),
                    "market": "crypto",
                },
                source="test",
            )
        )

    # DCA should fire because it's never purchased BTC/USDT before
    dca_signals = [
        s for s in signals_received if s.data.get("strategy") == "dca"
    ]
    assert len(dca_signals) > 0, "DCA should generate a signal on first evaluation"
    assert dca_signals[0].data["side"] == "BUY"
    assert dca_signals[0].data["symbol"] == "BTC/USDT"

    await manager.stop()


@pytest.mark.asyncio
async def test_full_pipeline_signal_to_fill():
    """Test the complete pipeline: price → strategy → signal → risk → execution → fill."""
    from src.connectors.paper import PaperConnector
    from src.execution.engine import ExecutionEngine
    from src.risk.circuit_breakers import CircuitBreakerManager
    from src.risk.manager import RiskManager

    event_bus = EventBus()
    portfolio = PortfolioManager(event_bus=event_bus, initial_cash=Decimal("10000"))
    await portfolio.start()

    # Set up paper connector
    connector = PaperConnector(
        market=Market.CRYPTO,
        event_bus=event_bus,
        initial_balance=Decimal("10000"),
    )
    await connector.connect()
    connector.set_price("BTC/USDT", Decimal("60000"))
    connector.set_price("ETH/USDT", Decimal("3000"))

    # Set up risk and execution
    config = _make_config(momentum_enabled=False, grid_enabled=False)
    circuit_breakers = CircuitBreakerManager(event_bus)
    risk_manager = RiskManager(
        event_bus=event_bus,
        portfolio=portfolio,
        risk_config=config.risk,
        circuit_breakers=circuit_breakers,
    )
    await risk_manager.start()

    execution = ExecutionEngine(
        event_bus=event_bus,
        connectors={"crypto": connector},
    )
    await execution.start()

    # Set up strategy manager
    position_sizer = PositionSizer(config.risk, portfolio)
    manager = StrategyManager(
        event_bus=event_bus,
        config=config,
        portfolio=portfolio,
        position_sizer=position_sizer,
    )
    await manager.start()

    # Send price ticks to trigger DCA
    for i in range(10):
        await event_bus.publish(
            Event(
                event_type=EventType.PRICE_UPDATE,
                data={
                    "symbol": "BTC/USDT",
                    "price": str(60000 + i),
                    "market": "crypto",
                },
                source="test",
            )
        )

    # Give the async pipeline a moment to complete
    await asyncio.sleep(0.1)

    # Verify trades were executed
    trades = portfolio.get_trades()
    assert len(trades) > 0, "Should have executed at least one trade"
    assert trades[0]["symbol"] == "BTC/USDT"
    assert trades[0]["side"] == "BUY"

    await manager.stop()


@pytest.mark.asyncio
async def test_status_reporting():
    """get_status() should return comprehensive state."""
    manager = _make_manager()
    await manager.start()

    status = manager.get_status()
    assert "strategies" in status
    assert "eval_count" in status
    assert "signal_count" in status
    assert "last_signals" in status
    assert "candle_counts" in status

    await manager.stop()


@pytest.mark.asyncio
async def test_ignores_events_when_stopped():
    """Should not process price events after stop()."""
    event_bus = EventBus()
    manager = _make_manager(event_bus=event_bus)
    await manager.start()
    await manager.stop()

    # Send price events — should be ignored
    for i in range(10):
        await event_bus.publish(
            Event(
                event_type=EventType.PRICE_UPDATE,
                data={
                    "symbol": "BTC/USDT",
                    "price": str(60000),
                    "market": "crypto",
                },
                source="test",
            )
        )

    assert manager._eval_count == 0
