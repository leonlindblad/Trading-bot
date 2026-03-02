"""Momentum / Trend Following strategy.

Uses EMA crossover with RSI confirmation and volume filter.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
from loguru import logger

from src.config import MomentumConfig
from src.connectors.base import Market, Side, Signal
from src.strategies.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    """Trend following strategy using EMA crossover, RSI, and volume filter.

    Entry: EMA(12) crosses above EMA(26) + RSI 30-70 + volume > 1.5x average
    Exit: Opposite crossover OR trailing stop (2x ATR) OR RSI extreme (>70)
    """

    def __init__(self, config: MomentumConfig, market: Market):
        self._config = config
        self._market = market
        self._trailing_stops: dict[str, Decimal] = {}
        self._active_positions: dict[str, dict] = {}

    @property
    def name(self) -> str:
        return "momentum"

    async def evaluate(
        self,
        symbol: str,
        candles: pd.DataFrame,
        current_position: Any | None,
    ) -> Signal | None:
        """Evaluate EMA crossover + RSI + volume for entry/exit signals.

        Args:
            candles: DataFrame with columns: open, high, low, close, volume.
                     Must have at least ema_slow + 1 rows.
            current_position: Existing position dict with 'quantity', 'avg_cost'.
        """
        min_periods = self._config.ema_slow + 1
        if len(candles) < min_periods:
            return None

        close = candles["close"].astype(float)
        volume = candles["volume"].astype(float)
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)

        # Calculate indicators
        ema_fast = close.ewm(span=self._config.ema_fast, adjust=False).mean()
        ema_slow = close.ewm(span=self._config.ema_slow, adjust=False).mean()
        rsi = self._calculate_rsi(close, self._config.rsi_period)
        atr = self._calculate_atr(high, low, close, 14)
        avg_volume = volume.rolling(window=20).mean()

        current_price = Decimal(str(close.iloc[-1]))
        current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0
        current_atr = Decimal(str(atr.iloc[-1])) if not pd.isna(atr.iloc[-1]) else Decimal("0")
        vol_ratio = (
            volume.iloc[-1] / avg_volume.iloc[-1]
            if avg_volume.iloc[-1] > 0
            else 0.0
        )

        # Previous and current EMA values
        prev_ema_fast = ema_fast.iloc[-2]
        prev_ema_slow = ema_slow.iloc[-2]
        curr_ema_fast = ema_fast.iloc[-1]
        curr_ema_slow = ema_slow.iloc[-1]

        has_position = current_position is not None

        # --- EXIT SIGNALS ---
        if has_position:
            # Check trailing stop
            if symbol in self._trailing_stops:
                if current_price <= self._trailing_stops[symbol]:
                    logger.info(
                        f"Momentum EXIT (trailing stop): {symbol} "
                        f"price {current_price} <= stop {self._trailing_stops[symbol]}"
                    )
                    del self._trailing_stops[symbol]
                    self._active_positions.pop(symbol, None)
                    return Signal(
                        symbol=symbol,
                        side=Side.SELL,
                        market=self._market,
                        strategy=self.name,
                        quantity=Decimal(str(current_position.get("quantity", 0))),
                        reason="trailing_stop",
                    )

            # Bearish crossover
            if prev_ema_fast >= prev_ema_slow and curr_ema_fast < curr_ema_slow:
                logger.info(f"Momentum EXIT (bearish crossover): {symbol}")
                self._trailing_stops.pop(symbol, None)
                self._active_positions.pop(symbol, None)
                return Signal(
                    symbol=symbol,
                    side=Side.SELL,
                    market=self._market,
                    strategy=self.name,
                    quantity=Decimal(str(current_position.get("quantity", 0))),
                    reason="trend_reversal",
                )

            # RSI overbought exit
            if current_rsi > 70:
                logger.info(f"Momentum EXIT (RSI overbought {current_rsi:.1f}): {symbol}")
                self._trailing_stops.pop(symbol, None)
                self._active_positions.pop(symbol, None)
                return Signal(
                    symbol=symbol,
                    side=Side.SELL,
                    market=self._market,
                    strategy=self.name,
                    quantity=Decimal(str(current_position.get("quantity", 0))),
                    reason="rsi_overbought",
                )

            # Update trailing stop
            if current_atr > 0:
                new_stop = current_price - 2 * current_atr
                old_stop = self._trailing_stops.get(symbol, Decimal("0"))
                if new_stop > old_stop:
                    self._trailing_stops[symbol] = new_stop

            return None

        # --- ENTRY SIGNALS ---
        # Check position count limit
        positions_in_market = len(self._active_positions)
        if positions_in_market >= self._config.max_positions_per_market:
            return None

        # Bullish EMA crossover
        bullish_crossover = (
            prev_ema_fast <= prev_ema_slow and curr_ema_fast > curr_ema_slow
        )
        if not bullish_crossover:
            return None

        # RSI confirmation (between 30 and 70, trending up)
        if not (30 < current_rsi < 70):
            return None

        # Volume filter
        if vol_ratio < self._config.volume_threshold:
            return None

        # All conditions met — generate BUY signal
        stop_loss = current_price - 2 * current_atr if current_atr > 0 else None

        logger.info(
            f"Momentum ENTRY: {symbol} @ {current_price} "
            f"RSI={current_rsi:.1f} Vol={vol_ratio:.2f}x"
        )

        if stop_loss:
            self._trailing_stops[symbol] = stop_loss

        self._active_positions[symbol] = {"entry_price": current_price}

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            market=self._market,
            strategy=self.name,
            price=current_price,
            stop_loss=stop_loss,
            reason="ema_crossover",
        )

    async def on_fill(self, trade: dict) -> None:
        """Track fills for position management."""
        symbol = trade.get("symbol", "")
        side = trade.get("side", "")
        if side == "SELL":
            self._active_positions.pop(symbol, None)
            self._trailing_stops.pop(symbol, None)

    def get_state(self) -> dict:
        return {
            "trailing_stops": {k: str(v) for k, v in self._trailing_stops.items()},
            "active_positions": self._active_positions,
        }

    def load_state(self, data: dict) -> None:
        self._trailing_stops = {
            k: Decimal(v) for k, v in data.get("trailing_stops", {}).items()
        }
        self._active_positions = data.get("active_positions", {})

    @staticmethod
    def _calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _calculate_atr(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        """Calculate Average True Range."""
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return true_range.rolling(window=period).mean()
