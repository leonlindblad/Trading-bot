"""Shared test fixtures."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
import pytest_asyncio

from src.config import (
    AppConfig,
    DCAConfig,
    GridConfig,
    MomentumConfig,
    PaperTradingConfig,
    RiskConfig,
    Settings,
)
from src.connectors.base import Market
from src.connectors.paper import PaperConnector
from src.event_bus import EventBus
from src.portfolio.manager import PortfolioManager
from src.risk.circuit_breakers import CircuitBreakerManager


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def event_bus():
    return EventBus()


@pytest_asyncio.fixture
async def paper_connector(event_bus):
    connector = PaperConnector(
        market=Market.CRYPTO,
        event_bus=event_bus,
        initial_balance=Decimal("10000"),
        slippage_pct=Decimal("0.0005"),
        fee_pct=Decimal("0.001"),
    )
    await connector.connect()
    connector.set_price("BTC/USDT", Decimal("60000"))
    connector.set_price("ETH/USDT", Decimal("3000"))
    yield connector
    await connector.disconnect()


@pytest_asyncio.fixture
async def portfolio(event_bus):
    pm = PortfolioManager(event_bus=event_bus, initial_cash=Decimal("10000"))
    await pm.start()
    return pm


@pytest_asyncio.fixture
async def circuit_breakers(event_bus):
    return CircuitBreakerManager(event_bus)


@pytest.fixture
def risk_config():
    return RiskConfig(
        {
            "total_budget": 10000,
            "per_trade_max_pct": 2,
            "per_asset_max_pct": 15,
            "per_market_max_pct": 50,
            "daily_loss_limit_pct": 3,
            "weekly_loss_limit_pct": 7,
            "max_open_positions": 15,
            "max_concurrent_orders_per_exchange": 5,
            "cash_reserve_pct": 20,
        }
    )


@pytest.fixture
def momentum_config():
    return MomentumConfig(
        {
            "enabled": True,
            "ema_fast": 12,
            "ema_slow": 26,
            "rsi_period": 14,
            "volume_threshold": 1.5,
            "trailing_stop_atr_mult": 2.0,
            "max_positions_per_market": 3,
            "position_size_pct": 2.0,
        }
    )


@pytest.fixture
def dca_config():
    return DCAConfig(
        {
            "enabled": True,
            "schedule": "daily",
            "base_amount": 50,
            "dip_threshold_pct": 5,
            "dip_multiplier": 1.5,
            "crash_threshold_pct": 15,
            "crash_multiplier": 2.0,
            "allocation": {"BTC/USDT": 0.5, "ETH/USDT": 0.3},
        }
    )


@pytest.fixture
def grid_config():
    return GridConfig(
        {
            "enabled": True,
            "num_levels": 10,
            "spacing_pct": 1.5,
            "auto_range": False,
            "recalculate_weekly": False,
            "budget_per_asset_pct": 5,
        }
    )


@pytest.fixture
def sample_candles():
    """Generate sample OHLCV candle data for testing strategies."""
    np.random.seed(42)
    n = 50
    dates = pd.date_range("2026-01-01", periods=n, freq="1h")
    close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 10.0)  # Ensure positive

    return pd.DataFrame(
        {
            "open": close * (1 + np.random.randn(n) * 0.001),
            "high": close * (1 + np.abs(np.random.randn(n) * 0.01)),
            "low": close * (1 - np.abs(np.random.randn(n) * 0.01)),
            "close": close,
            "volume": np.random.uniform(100, 1000, n),
        },
        index=dates,
    )


@pytest.fixture
def bullish_crossover_candles():
    """Candle data that produces a bullish EMA crossover."""
    n = 30
    # Start declining, then strongly reverse upward
    prices = list(range(100, 85, -1)) + list(range(85, 100, 1))
    prices = [float(p) for p in prices]

    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [500.0] * n,
        }
    )
