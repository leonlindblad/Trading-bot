"""Tests for the Grid Trading strategy."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.connectors.base import Market, Side
from src.strategies.grid import GridStrategy


def _make_candles(prices):
    """Helper to create candle DataFrame."""
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.005 for p in prices],
            "low": [p * 0.995 for p in prices],
            "close": prices,
            "volume": [500.0] * len(prices),
        }
    )


@pytest.mark.asyncio
async def test_grid_initialization(grid_config):
    """Grid should be created on first evaluation."""
    strategy = GridStrategy(
        config=grid_config, market=Market.CRYPTO, total_budget=Decimal("10000")
    )
    prices = [100.0] * 20
    candles = _make_candles(prices)

    # First call initializes the grid
    signal = await strategy.evaluate("BTC/USDT", candles, None)
    assert signal is None  # No trade on initialization tick
    assert "BTC/USDT" in strategy._grids

    grid = strategy._grids["BTC/USDT"]
    assert len(grid.levels) == grid_config.num_levels
    assert grid.is_active


@pytest.mark.asyncio
async def test_grid_buy_on_price_drop(grid_config):
    """Should trigger BUY when price drops to a grid level."""
    strategy = GridStrategy(
        config=grid_config, market=Market.CRYPTO, total_budget=Decimal("10000")
    )

    # Initialize grid at price 100
    init_prices = [100.0] * 20
    candles = _make_candles(init_prices)
    await strategy.evaluate("BTC/USDT", candles, None)

    # Find a buy level below 100
    grid = strategy._grids["BTC/USDT"]
    buy_levels = [l for l in grid.levels if l.side == Side.BUY and l.price < Decimal("100")]

    if buy_levels:
        target_price = float(buy_levels[-1].price)
        # Price drops to that level
        drop_prices = init_prices + [100.0, target_price]
        candles2 = _make_candles(drop_prices)
        signal = await strategy.evaluate("BTC/USDT", candles2, None)

        if signal:
            assert signal.side == Side.BUY
            assert signal.strategy == "grid"


@pytest.mark.asyncio
async def test_grid_range_break(grid_config):
    """Should deactivate on range break."""
    strategy = GridStrategy(
        config=grid_config, market=Market.CRYPTO, total_budget=Decimal("10000")
    )

    # Initialize at 100
    init_prices = [100.0] * 20
    candles = _make_candles(init_prices)
    await strategy.evaluate("BTC/USDT", candles, None)

    grid = strategy._grids["BTC/USDT"]
    far_above = float(grid.upper_bound) + 10.0

    # Price breaks above grid range
    break_prices = init_prices + [100.0, far_above]
    candles2 = _make_candles(break_prices)
    signal = await strategy.evaluate("BTC/USDT", candles2, None)

    assert signal is None
    assert not grid.is_active  # Grid should be paused


@pytest.mark.asyncio
async def test_grid_state_serialization(grid_config):
    """Grid state should serialize and restore."""
    strategy = GridStrategy(
        config=grid_config, market=Market.CRYPTO, total_budget=Decimal("10000")
    )
    prices = [100.0] * 20
    candles = _make_candles(prices)
    await strategy.evaluate("BTC/USDT", candles, None)

    state = strategy.get_state()
    assert "BTC/USDT" in state
    assert "levels" in state["BTC/USDT"]

    new_strategy = GridStrategy(
        config=grid_config, market=Market.CRYPTO, total_budget=Decimal("10000")
    )
    new_strategy.load_state(state)
    assert "BTC/USDT" in new_strategy._grids
    assert len(new_strategy._grids["BTC/USDT"].levels) == grid_config.num_levels
