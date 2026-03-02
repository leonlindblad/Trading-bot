"""Tests for the DCA strategy."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.connectors.base import Market, Side
from src.strategies.dca import DCAStrategy


def _make_candles(prices, n=30):
    """Helper to create candle DataFrame from close prices."""
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [500.0] * len(prices),
        }
    )


@pytest.mark.asyncio
async def test_first_purchase_always_due(dca_config):
    """First evaluation should always trigger a purchase."""
    strategy = DCAStrategy(config=dca_config, market=Market.CRYPTO)
    prices = [100.0] * 30
    candles = _make_candles(prices)

    signal = await strategy.evaluate("BTC/USDT", candles, None)

    assert signal is not None
    assert signal.side == Side.BUY
    assert signal.strategy == "dca"


@pytest.mark.asyncio
async def test_schedule_respected(dca_config):
    """Should not purchase again before schedule interval."""
    strategy = DCAStrategy(config=dca_config, market=Market.CRYPTO)
    prices = [100.0] * 30
    candles = _make_candles(prices)

    # First purchase
    signal1 = await strategy.evaluate("BTC/USDT", candles, None)
    assert signal1 is not None

    # Immediate second attempt should be None (daily schedule)
    signal2 = await strategy.evaluate("BTC/USDT", candles, None)
    assert signal2 is None


@pytest.mark.asyncio
async def test_dip_multiplier(dca_config):
    """Should increase buy amount when dip detected."""
    strategy = DCAStrategy(config=dca_config, market=Market.CRYPTO)

    # 7-day high was 100, now at 93 (7% drop > 5% threshold)
    prices = [100.0] * 24 + [95.0, 94.0, 93.5, 93.0, 93.0, 93.0]
    candles = _make_candles(prices)

    signal = await strategy.evaluate("BTC/USDT", candles, None)
    assert signal is not None
    # With dip multiplier of 1.5x, quantity should be higher than normal
    normal_amount = Decimal(str(dca_config.base_amount)) * Decimal(str(dca_config.allocation.get("BTC/USDT", 0)))
    normal_qty = normal_amount / Decimal("93")
    # Signal quantity should be ~1.5x normal
    assert signal.quantity > normal_qty * Decimal("1.1")


@pytest.mark.asyncio
async def test_crash_multiplier(dca_config):
    """Should double buy amount on crash (>15% drop from 30-day high)."""
    strategy = DCAStrategy(config=dca_config, market=Market.CRYPTO)

    # 30-day high was 120, now at 100 (~17% drop > 15% threshold)
    prices = [120.0] * 20 + [110.0, 108.0, 105.0, 103.0, 102.0, 101.0, 100.5, 100.0, 100.0, 100.0]
    candles = _make_candles(prices)

    signal = await strategy.evaluate("BTC/USDT", candles, None)
    assert signal is not None
    # Should use crash multiplier (2.0x)


@pytest.mark.asyncio
async def test_zero_allocation_no_signal(dca_config):
    """Symbol with 0 allocation should not trigger purchase."""
    strategy = DCAStrategy(config=dca_config, market=Market.CRYPTO)
    prices = [100.0] * 30
    candles = _make_candles(prices)

    signal = await strategy.evaluate("SOL/USDT", candles, None)
    assert signal is None  # SOL not in allocation


@pytest.mark.asyncio
async def test_state_persistence(dca_config):
    """State should serialize and restore correctly."""
    strategy = DCAStrategy(config=dca_config, market=Market.CRYPTO)
    prices = [100.0] * 30
    candles = _make_candles(prices)

    await strategy.evaluate("BTC/USDT", candles, None)

    state = strategy.get_state()
    assert "last_purchase" in state
    assert "BTC/USDT" in state["last_purchase"]

    new_strategy = DCAStrategy(config=dca_config, market=Market.CRYPTO)
    new_strategy.load_state(state)
    assert "BTC/USDT" in new_strategy._last_purchase
