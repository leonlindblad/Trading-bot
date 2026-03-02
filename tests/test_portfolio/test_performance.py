"""Tests for performance metric calculations."""

from __future__ import annotations

import pytest

from src.portfolio.performance import (
    calculate_calmar_ratio,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_win_rate,
)


def test_sharpe_ratio_basic():
    """Sharpe ratio with known returns."""
    returns = [0.01, 0.02, -0.005, 0.015, 0.01]
    result = calculate_sharpe_ratio(returns)
    assert result is not None
    assert result > 0


def test_sharpe_ratio_insufficient_data():
    """Should return None with < 2 data points."""
    assert calculate_sharpe_ratio([0.01]) is None
    assert calculate_sharpe_ratio([]) is None


def test_sharpe_ratio_zero_std():
    """Should return None when all returns are identical."""
    result = calculate_sharpe_ratio([0.01, 0.01, 0.01])
    assert result is None


def test_max_drawdown_basic():
    """Max drawdown with a clear peak-to-trough."""
    equity = [100, 110, 120, 100, 90, 95, 130]
    # Peak=120, trough=90, dd = 30/120 = 0.25
    dd = calculate_max_drawdown(equity)
    assert abs(dd - 0.25) < 0.001


def test_max_drawdown_no_drawdown():
    """No drawdown in a monotonically increasing curve."""
    equity = [100, 110, 120, 130]
    dd = calculate_max_drawdown(equity)
    assert dd == 0.0


def test_max_drawdown_insufficient_data():
    assert calculate_max_drawdown([100]) == 0.0
    assert calculate_max_drawdown([]) == 0.0


def test_win_rate_all_winners():
    trades = [{"pnl": 10}, {"pnl": 20}, {"pnl": 5}]
    assert calculate_win_rate(trades) == 1.0


def test_win_rate_mixed():
    trades = [{"pnl": 10}, {"pnl": -5}, {"pnl": 20}, {"pnl": -3}]
    assert calculate_win_rate(trades) == 0.5


def test_win_rate_empty():
    assert calculate_win_rate([]) == 0.0


def test_profit_factor_basic():
    trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 200}]
    result = calculate_profit_factor(trades)
    assert result is not None
    assert result == 300 / 50


def test_profit_factor_no_losses():
    trades = [{"pnl": 100}]
    assert calculate_profit_factor(trades) is None


def test_calmar_ratio():
    result = calculate_calmar_ratio(0.20, 0.10)
    assert result == 2.0


def test_calmar_ratio_zero_drawdown():
    assert calculate_calmar_ratio(0.20, 0.0) is None
