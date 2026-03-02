"""Grid Trading strategy.

Places buy and sell orders at predetermined price intervals,
profiting from natural price oscillation in ranging markets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from typing import Any

import pandas as pd
from loguru import logger

from src.config import GridConfig
from src.connectors.base import Market, Side, Signal
from src.strategies.base import BaseStrategy


@dataclass
class GridLevel:
    """A single level in the grid."""

    price: Decimal
    side: Side
    quantity: Decimal
    is_filled: bool = False
    order_id: str | None = None


@dataclass
class GridState:
    """State for a single symbol's grid."""

    symbol: str
    upper_bound: Decimal
    lower_bound: Decimal
    levels: list[GridLevel] = field(default_factory=list)
    is_active: bool = True


class GridStrategy(BaseStrategy):
    """Grid trading with configurable levels and spacing.

    Places buy orders below current price and sell orders above,
    profiting from each completed grid cycle.
    """

    def __init__(self, config: GridConfig, market: Market, total_budget: Decimal):
        self._config = config
        self._market = market
        self._total_budget = total_budget
        self._grids: dict[str, GridState] = {}
        self._pending_signals: dict[str, list[Signal]] = {}

    @property
    def name(self) -> str:
        return "grid"

    def _initialize_grid(
        self, symbol: str, current_price: Decimal, atr: Decimal | None = None
    ) -> GridState:
        """Create a new grid centered on the current price."""
        num_levels = self._config.num_levels
        spacing_pct = Decimal(str(self._config.spacing_pct)) / Decimal("100")

        if self._config.auto_range and atr and atr > 0:
            # Auto-range: use ATR to set grid boundaries
            half_range = atr * Decimal("3")
            upper = current_price + half_range
            lower = current_price - half_range
        else:
            # Fixed spacing
            half_levels = num_levels // 2
            upper = current_price * (Decimal("1") + spacing_pct * half_levels)
            lower = current_price * (Decimal("1") - spacing_pct * half_levels)

        lower = max(lower, Decimal("0.01"))

        # Calculate budget per level
        grid_budget = (
            self._total_budget
            * Decimal(str(self._config.budget_per_asset_pct))
            / Decimal("100")
        )
        budget_per_level = grid_budget / Decimal(str(num_levels))

        # Generate levels
        levels = []
        step = (upper - lower) / Decimal(str(num_levels - 1)) if num_levels > 1 else Decimal("0")

        for i in range(num_levels):
            level_price = (lower + step * Decimal(str(i))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            quantity = (budget_per_level / level_price).quantize(
                Decimal("0.00000001"), rounding=ROUND_DOWN
            )
            side = Side.BUY if level_price < current_price else Side.SELL
            levels.append(
                GridLevel(price=level_price, side=side, quantity=quantity)
            )

        grid = GridState(
            symbol=symbol,
            upper_bound=upper,
            lower_bound=lower,
            levels=sorted(levels, key=lambda l: l.price),
        )

        self._grids[symbol] = grid
        logger.info(
            f"Grid initialized for {symbol}: {num_levels} levels, "
            f"range [{lower:.2f}, {upper:.2f}]"
        )
        return grid

    async def evaluate(
        self,
        symbol: str,
        candles: pd.DataFrame,
        current_position: Any | None,
    ) -> Signal | None:
        """Evaluate grid levels against current price.

        Returns a signal if price has crossed a grid level.
        """
        if len(candles) < 2:
            return None

        close = candles["close"].astype(float)
        current_price = Decimal(str(close.iloc[-1]))

        # Initialize grid if needed
        if symbol not in self._grids:
            atr = None
            if len(candles) >= 14:
                high = candles["high"].astype(float)
                low = candles["low"].astype(float)
                prev_close = close.shift(1)
                tr = pd.concat(
                    [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
                    axis=1,
                ).max(axis=1)
                atr_val = tr.rolling(14).mean().iloc[-1]
                if not pd.isna(atr_val):
                    atr = Decimal(str(atr_val))
            self._initialize_grid(symbol, current_price, atr)
            return None  # Don't trade on initialization tick

        grid = self._grids[symbol]
        if not grid.is_active:
            return None

        # Check range break
        if current_price > grid.upper_bound or current_price < grid.lower_bound:
            logger.warning(
                f"Grid range break for {symbol}: price {current_price} "
                f"outside [{grid.lower_bound}, {grid.upper_bound}]"
            )
            grid.is_active = False
            return None

        # Check if price crossed any grid levels
        prev_price = Decimal(str(close.iloc[-2]))

        for level in grid.levels:
            if level.is_filled:
                continue

            # Buy level: price dropped to or below the level
            if level.side == Side.BUY:
                if prev_price > level.price >= current_price:
                    level.is_filled = True
                    logger.info(
                        f"Grid BUY triggered: {symbol} @ {level.price} "
                        f"(current: {current_price})"
                    )
                    # After buy fills, we want to sell one level above
                    self._set_counter_order(grid, level, Side.SELL)
                    return Signal(
                        symbol=symbol,
                        side=Side.BUY,
                        market=self._market,
                        strategy=self.name,
                        quantity=level.quantity,
                        price=level.price,
                        reason="grid_level_buy",
                    )

            # Sell level: price rose to or above the level
            elif level.side == Side.SELL:
                if prev_price < level.price <= current_price:
                    level.is_filled = True
                    logger.info(
                        f"Grid SELL triggered: {symbol} @ {level.price} "
                        f"(current: {current_price})"
                    )
                    # After sell fills, we want to buy one level below
                    self._set_counter_order(grid, level, Side.BUY)
                    return Signal(
                        symbol=symbol,
                        side=Side.SELL,
                        market=self._market,
                        strategy=self.name,
                        quantity=level.quantity,
                        price=level.price,
                        reason="grid_level_sell",
                    )

        return None

    def _set_counter_order(
        self, grid: GridState, filled_level: GridLevel, new_side: Side
    ) -> None:
        """After a fill, find the adjacent level and set it as a counter order."""
        levels = grid.levels
        idx = levels.index(filled_level)

        if new_side == Side.SELL and idx + 1 < len(levels):
            target = levels[idx + 1]
            target.side = Side.SELL
            target.is_filled = False
        elif new_side == Side.BUY and idx - 1 >= 0:
            target = levels[idx - 1]
            target.side = Side.BUY
            target.is_filled = False

    async def on_fill(self, trade: dict) -> None:
        """Track grid fills."""
        pass

    def get_state(self) -> dict:
        result = {}
        for symbol, grid in self._grids.items():
            result[symbol] = {
                "upper_bound": str(grid.upper_bound),
                "lower_bound": str(grid.lower_bound),
                "is_active": grid.is_active,
                "levels": [
                    {
                        "price": str(l.price),
                        "side": l.side.value,
                        "quantity": str(l.quantity),
                        "is_filled": l.is_filled,
                    }
                    for l in grid.levels
                ],
            }
        return result

    def load_state(self, data: dict) -> None:
        for symbol, grid_data in data.items():
            levels = [
                GridLevel(
                    price=Decimal(l["price"]),
                    side=Side(l["side"]),
                    quantity=Decimal(l["quantity"]),
                    is_filled=l["is_filled"],
                )
                for l in grid_data.get("levels", [])
            ]
            self._grids[symbol] = GridState(
                symbol=symbol,
                upper_bound=Decimal(grid_data["upper_bound"]),
                lower_bound=Decimal(grid_data["lower_bound"]),
                levels=levels,
                is_active=grid_data.get("is_active", True),
            )
