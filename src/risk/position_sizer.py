"""Position sizing logic — calculates trade size respecting all risk constraints."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from src.config import RiskConfig
from src.connectors.base import Market, Side
from src.portfolio.manager import PortfolioManager


class PositionSizer:
    """Calculates position sizes that respect all risk parameters."""

    def __init__(self, risk_config: RiskConfig, portfolio: PortfolioManager):
        self.config = risk_config
        self.portfolio = portfolio

    def calculate_size(
        self,
        symbol: str,
        side: Side,
        market: Market,
        price: Decimal,
        strategy_pct: Decimal = Decimal("2"),
    ) -> Decimal:
        """Calculate maximum position size respecting all risk limits.

        Args:
            symbol: Trading symbol.
            side: BUY or SELL.
            market: Market type.
            price: Entry price.
            strategy_pct: Strategy-level position size as % of portfolio.

        Returns:
            Quantity to trade (may be 0 if no trade is possible).
        """
        if side == Side.SELL:
            # For sells, return the current position quantity
            pos = self.portfolio.get_position(symbol)
            return pos.quantity if pos else Decimal("0")

        if price <= 0:
            return Decimal("0")

        equity = self.portfolio.get_total_equity()
        if equity <= 0:
            return Decimal("0")

        # 1. Strategy-level size (e.g., 2% of portfolio)
        max_by_strategy = equity * strategy_pct / Decimal("100") / price

        # 2. Per-trade max
        max_by_trade = (
            equity * self.config.per_trade_max_pct / Decimal("100") / price
        )

        # 3. Per-asset limit
        current_asset_exposure = self.portfolio.get_asset_exposure(symbol)
        max_asset_value = equity * self.config.per_asset_max_pct / Decimal("100")
        remaining_asset = max(Decimal("0"), max_asset_value - current_asset_exposure)
        max_by_asset = remaining_asset / price

        # 4. Per-market limit
        current_market_exposure = self.portfolio.get_market_exposure(market)
        max_market_value = equity * self.config.per_market_max_pct / Decimal("100")
        remaining_market = max(Decimal("0"), max_market_value - current_market_exposure)
        max_by_market = remaining_market / price

        # 5. Cash reserve constraint
        min_cash = equity * self.config.cash_reserve_pct / Decimal("100")
        available_for_trading = max(
            Decimal("0"), self.portfolio.get_cash_balance() - min_cash
        )
        max_by_cash = available_for_trading / price

        # Take the minimum of all constraints
        size = min(
            max_by_strategy,
            max_by_trade,
            max_by_asset,
            max_by_market,
            max_by_cash,
        )

        # Round down to avoid exceeding limits due to rounding
        return max(Decimal("0"), size.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN))
