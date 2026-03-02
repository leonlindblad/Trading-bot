"""Dollar-Cost Averaging (DCA) strategy.

Invests fixed amounts at regular intervals with optional dip-buying logic.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Any

import pandas as pd
from loguru import logger

from src.config import DCAConfig
from src.connectors.base import Market, Side, Signal
from src.strategies.base import BaseStrategy


class DCAStrategy(BaseStrategy):
    """Dollar-cost averaging with dip detection and crash buying.

    - Schedule: hourly, daily, or weekly purchases
    - Dip detection: +50% buy if price drops >5% from 7-day high
    - Crash detection: +100% buy if price drops >15% from 30-day high
    """

    def __init__(self, config: DCAConfig, market: Market):
        self._config = config
        self._market = market
        self._last_purchase: dict[str, datetime] = {}
        self._daily_spent: Decimal = Decimal("0")
        self._monthly_spent: Decimal = Decimal("0")
        self._last_daily_reset: datetime | None = None
        self._last_monthly_reset: datetime | None = None

    @property
    def name(self) -> str:
        return "dca"

    def _get_interval(self) -> timedelta:
        """Get the scheduling interval."""
        intervals = {
            "hourly": timedelta(hours=1),
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
        }
        return intervals.get(self._config.schedule, timedelta(days=1))

    def _is_due(self, symbol: str) -> bool:
        """Check if a purchase is due for this symbol."""
        now = datetime.now(timezone.utc)
        last = self._last_purchase.get(symbol)
        if last is None:
            return True
        return (now - last) >= self._get_interval()

    async def evaluate(
        self,
        symbol: str,
        candles: pd.DataFrame,
        current_position: Any | None,
    ) -> Signal | None:
        """Evaluate whether a DCA purchase is due.

        Args:
            candles: DataFrame with at least 30 rows for crash detection.
            current_position: Existing position (DCA always adds, never sells).
        """
        if not self._is_due(symbol):
            return None

        # Get allocation weight for this symbol
        weight = self._config.allocation.get(symbol, 0)
        if weight <= 0:
            return None

        # Reset daily/monthly counters
        self._reset_counters()

        base_amount = Decimal(str(self._config.base_amount)) * Decimal(str(weight))
        if base_amount <= 0:
            return None

        # Dip and crash detection
        multiplier = Decimal("1")
        if len(candles) >= 7:
            close = candles["close"].astype(float)
            current_price = close.iloc[-1]

            # 7-day high for dip detection
            seven_day_high = close.iloc[-7:].max()
            if seven_day_high > 0:
                drop_from_7d = (seven_day_high - current_price) / seven_day_high * 100
                if drop_from_7d >= self._config.dip_threshold_pct:
                    multiplier = Decimal(str(self._config.dip_multiplier))
                    logger.info(
                        f"DCA dip detected for {symbol}: "
                        f"{drop_from_7d:.1f}% below 7-day high, "
                        f"multiplier={multiplier}"
                    )

            # 30-day high for crash detection
            if len(candles) >= 30:
                thirty_day_high = close.iloc[-30:].max()
                if thirty_day_high > 0:
                    drop_from_30d = (
                        (thirty_day_high - current_price) / thirty_day_high * 100
                    )
                    if drop_from_30d >= self._config.crash_threshold_pct:
                        multiplier = Decimal(str(self._config.crash_multiplier))
                        logger.info(
                            f"DCA crash detected for {symbol}: "
                            f"{drop_from_30d:.1f}% below 30-day high, "
                            f"multiplier={multiplier}"
                        )

        buy_amount = base_amount * multiplier

        # Budget guard
        monthly_budget = Decimal(str(self._config.base_amount)) * Decimal("30")
        remaining = monthly_budget - self._monthly_spent
        if remaining <= 0:
            logger.info(f"DCA monthly budget exhausted")
            return None
        buy_amount = min(buy_amount, remaining)

        # Calculate quantity
        current_price = Decimal(str(candles["close"].iloc[-1]))
        if current_price <= 0:
            return None

        quantity = (buy_amount / current_price).quantize(
            Decimal("0.00000001"), rounding=ROUND_DOWN
        )
        if quantity <= 0:
            return None

        # Record purchase
        now = datetime.now(timezone.utc)
        self._last_purchase[symbol] = now
        self._daily_spent += buy_amount
        self._monthly_spent += buy_amount

        logger.info(
            f"DCA BUY: {symbol} amount={buy_amount:.2f} qty={quantity} "
            f"@ {current_price}"
        )

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            market=self._market,
            strategy=self.name,
            quantity=quantity,
            price=current_price,
            reason=f"dca_scheduled_x{multiplier}",
        )

    def _reset_counters(self) -> None:
        """Reset daily and monthly spending counters when appropriate."""
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if self._last_daily_reset is None or today > self._last_daily_reset:
            self._daily_spent = Decimal("0")
            self._last_daily_reset = today

        first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if self._last_monthly_reset is None or first_of_month > self._last_monthly_reset:
            self._monthly_spent = Decimal("0")
            self._last_monthly_reset = first_of_month

    async def on_fill(self, trade: dict) -> None:
        """Track DCA fills."""
        pass

    def get_state(self) -> dict:
        return {
            "last_purchase": {
                k: v.isoformat() for k, v in self._last_purchase.items()
            },
            "daily_spent": str(self._daily_spent),
            "monthly_spent": str(self._monthly_spent),
        }

    def load_state(self, data: dict) -> None:
        self._last_purchase = {
            k: datetime.fromisoformat(v)
            for k, v in data.get("last_purchase", {}).items()
        }
        self._daily_spent = Decimal(data.get("daily_spent", "0"))
        self._monthly_spent = Decimal(data.get("monthly_spent", "0"))
