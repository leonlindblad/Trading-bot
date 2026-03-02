"""Portfolio manager — tracks positions, calculates P&L, persists state."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

from loguru import logger

from src.connectors.base import Balance, Market, PositionInfo, Side
from src.event_bus import Event, EventBus, EventType


class PortfolioManager:
    """Tracks all positions across markets, computes P&L and exposure metrics."""

    def __init__(
        self,
        event_bus: EventBus,
        initial_cash: Decimal = Decimal("10000"),
    ):
        self.event_bus = event_bus
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._positions: dict[str, PositionInfo] = {}
        self._trades: list[dict] = []
        self._daily_start_equity: Decimal | None = None
        self._weekly_start_equity: Decimal | None = None
        self._day_start: datetime | None = None
        self._week_start: datetime | None = None

    async def start(self) -> None:
        """Subscribe to events and initialize tracking."""
        await self.event_bus.subscribe(EventType.ORDER_FILLED, self._on_order_filled)
        await self.event_bus.subscribe(EventType.PRICE_UPDATE, self._on_price_update)
        now = datetime.now(timezone.utc)
        equity = self.get_total_equity()
        self._daily_start_equity = equity
        self._weekly_start_equity = equity
        self._day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self._week_start = now - timedelta(days=now.weekday())
        self._week_start = self._week_start.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    async def _on_order_filled(self, event: Event) -> None:
        """Update positions and cash when an order is filled."""
        data = event.data
        symbol = data["symbol"]
        side = data["side"]
        quantity = Decimal(str(data["quantity"]))
        price = Decimal(str(data["price"]))
        fees = Decimal(str(data.get("fees", "0")))
        market_str = data.get("market", "crypto")
        strategy = data.get("strategy", "")

        try:
            market = Market(market_str)
        except ValueError:
            market = Market.CRYPTO

        if side == Side.BUY.value:
            # Update or create position
            if symbol in self._positions:
                pos = self._positions[symbol]
                old_qty = pos.quantity
                old_cost = pos.avg_cost
                new_qty = old_qty + quantity
                new_avg = (old_cost * old_qty + price * quantity) / new_qty
                self._positions[symbol] = PositionInfo(
                    symbol=symbol,
                    market=market,
                    quantity=new_qty,
                    avg_cost=new_avg,
                    current_price=price,
                    unrealised_pnl=(price - new_avg) * new_qty,
                    strategy=strategy,
                )
            else:
                self._positions[symbol] = PositionInfo(
                    symbol=symbol,
                    market=market,
                    quantity=quantity,
                    avg_cost=price,
                    current_price=price,
                    unrealised_pnl=Decimal("0"),
                    strategy=strategy,
                )
            self._cash -= price * quantity + fees
        elif side == Side.SELL.value:
            if symbol in self._positions:
                pos = self._positions[symbol]
                sell_qty = min(quantity, pos.quantity)
                remaining = pos.quantity - sell_qty
                if remaining > 0:
                    self._positions[symbol] = PositionInfo(
                        symbol=symbol,
                        market=market,
                        quantity=remaining,
                        avg_cost=pos.avg_cost,
                        current_price=price,
                        unrealised_pnl=(price - pos.avg_cost) * remaining,
                        strategy=pos.strategy,
                    )
                else:
                    del self._positions[symbol]
                self._cash += price * sell_qty - fees

        # Record trade
        self._trades.append(
            {
                "symbol": symbol,
                "side": side,
                "quantity": str(quantity),
                "price": str(price),
                "fees": str(fees),
                "market": market_str,
                "strategy": strategy,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        logger.info(
            f"Portfolio updated: {side} {quantity} {symbol} @ {price}. "
            f"Cash: {self._cash:.2f}"
        )

    async def _on_price_update(self, event: Event) -> None:
        """Update current prices and unrealised P&L for positions."""
        symbol = event.data.get("symbol")
        price_str = event.data.get("price")
        if not symbol or not price_str:
            return

        price = Decimal(str(price_str))
        if symbol in self._positions:
            pos = self._positions[symbol]
            self._positions[symbol] = PositionInfo(
                symbol=pos.symbol,
                market=pos.market,
                quantity=pos.quantity,
                avg_cost=pos.avg_cost,
                current_price=price,
                unrealised_pnl=(price - pos.avg_cost) * pos.quantity,
                strategy=pos.strategy,
            )

        # Check if we need to reset daily/weekly tracking
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self._day_start and today_start > self._day_start:
            self._daily_start_equity = self.get_total_equity()
            self._day_start = today_start

        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        if self._week_start and week_start > self._week_start:
            self._weekly_start_equity = self.get_total_equity()
            self._week_start = week_start

    def get_positions(self) -> list[PositionInfo]:
        """Get all open positions."""
        return list(self._positions.values())

    def get_position(self, symbol: str) -> PositionInfo | None:
        """Get position for a specific symbol."""
        return self._positions.get(symbol)

    def get_total_equity(self) -> Decimal:
        """Total portfolio value = cash + sum of position values."""
        positions_value = sum(
            pos.current_price * pos.quantity
            for pos in self._positions.values()
        )
        return self._cash + positions_value

    def get_cash_balance(self) -> Decimal:
        return self._cash

    def get_positions_value(self) -> Decimal:
        return sum(
            pos.current_price * pos.quantity for pos in self._positions.values()
        )

    def get_balance(self) -> Balance:
        positions_value = self.get_positions_value()
        return Balance(
            total_equity=self._cash + positions_value,
            available_cash=self._cash,
            positions_value=positions_value,
        )

    def get_daily_pnl(self) -> Decimal:
        """P&L since start of current trading day."""
        if self._daily_start_equity is None:
            return Decimal("0")
        return self.get_total_equity() - self._daily_start_equity

    def get_weekly_pnl(self) -> Decimal:
        """P&L since start of current trading week."""
        if self._weekly_start_equity is None:
            return Decimal("0")
        return self.get_total_equity() - self._weekly_start_equity

    def get_market_exposure(self, market: Market) -> Decimal:
        """Total position value in a given market."""
        return sum(
            pos.current_price * pos.quantity
            for pos in self._positions.values()
            if pos.market == market
        )

    def get_asset_exposure(self, symbol: str) -> Decimal:
        """Total value of a given asset."""
        pos = self._positions.get(symbol)
        if pos:
            return pos.current_price * pos.quantity
        return Decimal("0")

    def get_open_position_count(self) -> int:
        return len(self._positions)

    def get_trades(self) -> list[dict]:
        return list(self._trades)

    def get_total_pnl(self) -> Decimal:
        """Total unrealised + realised P&L."""
        return self.get_total_equity() - self._initial_cash
