"""Performance metrics calculation — Sharpe, drawdown, win rate, etc."""

from __future__ import annotations

from decimal import Decimal
import math


def calculate_sharpe_ratio(
    returns: list[float], risk_free_rate: float = 0.0
) -> float | None:
    """Calculate annualised Sharpe ratio from a series of daily returns.

    Returns None if insufficient data (< 2 data points).
    """
    if len(returns) < 2:
        return None

    excess = [r - risk_free_rate / 252 for r in returns]
    mean_return = sum(excess) / len(excess)
    variance = sum((r - mean_return) ** 2 for r in excess) / (len(excess) - 1)
    std_dev = math.sqrt(variance) if variance > 0 else 0

    if std_dev == 0:
        return None

    return (mean_return / std_dev) * math.sqrt(252)


def calculate_max_drawdown(equity_curve: list[float]) -> float:
    """Calculate maximum drawdown from an equity curve.

    Returns the drawdown as a positive fraction (e.g., 0.15 = 15% drawdown).
    """
    if len(equity_curve) < 2:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    return max_dd


def calculate_win_rate(trades: list[dict]) -> float:
    """Calculate percentage of profitable trades."""
    if not trades:
        return 0.0

    profitable = 0
    for trade in trades:
        pnl = float(trade.get("pnl", 0))
        if pnl > 0:
            profitable += 1

    return profitable / len(trades)


def calculate_profit_factor(trades: list[dict]) -> float | None:
    """Calculate gross profit / gross loss.

    Returns None if there are no losing trades.
    """
    gross_profit = 0.0
    gross_loss = 0.0

    for trade in trades:
        pnl = float(trade.get("pnl", 0))
        if pnl > 0:
            gross_profit += pnl
        elif pnl < 0:
            gross_loss += abs(pnl)

    if gross_loss == 0:
        return None

    return gross_profit / gross_loss


def calculate_calmar_ratio(
    annual_return: float, max_drawdown: float
) -> float | None:
    """Calculate Calmar ratio = annualised return / max drawdown."""
    if max_drawdown == 0:
        return None
    return annual_return / max_drawdown
