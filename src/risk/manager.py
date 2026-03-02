"""Risk management engine — validates every trade against portfolio risk limits."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from loguru import logger

from src.config import RiskConfig
from src.connectors.base import Market, Order, Side, Signal
from src.event_bus import Event, EventBus, EventType
from src.portfolio.manager import PortfolioManager
from src.risk.circuit_breakers import CircuitBreakerManager


@dataclass
class RiskDecision:
    """Result of risk validation."""

    approved: bool
    reason: str = ""


class RiskManager:
    """Validates every trade signal against configurable risk parameters.

    Every signal must pass ALL checks before it can be executed.
    """

    def __init__(
        self,
        event_bus: EventBus,
        portfolio: PortfolioManager,
        risk_config: RiskConfig,
        circuit_breakers: CircuitBreakerManager,
    ):
        self.event_bus = event_bus
        self.portfolio = portfolio
        self.config = risk_config
        self.circuit_breakers = circuit_breakers
        self._pending_orders_per_exchange: dict[str, int] = {}

    async def start(self) -> None:
        """Subscribe to signal events."""
        await self.event_bus.subscribe(
            EventType.SIGNAL_GENERATED, self._on_signal
        )
        await self.event_bus.subscribe(
            EventType.ORDER_FILLED, self._on_order_filled
        )

    async def _on_signal(self, event: Event) -> None:
        """Evaluate a trading signal through all risk checks."""
        signal_data = event.data
        order = Order(
            symbol=signal_data["symbol"],
            side=Side(signal_data["side"]),
            order_type=signal_data.get("order_type", "MARKET"),
            quantity=Decimal(str(signal_data["quantity"])),
            market=Market(signal_data["market"]),
            strategy=signal_data.get("strategy", ""),
            price=Decimal(str(signal_data["price"])) if signal_data.get("price") else None,
            stop_loss=Decimal(str(signal_data["stop_loss"])) if signal_data.get("stop_loss") else None,
        )

        decision = self.validate_trade(order)

        if decision.approved:
            logger.info(f"Risk approved: {order.side.value} {order.quantity} {order.symbol}")
            exchange_key = order.market.value
            self._pending_orders_per_exchange[exchange_key] = (
                self._pending_orders_per_exchange.get(exchange_key, 0) + 1
            )
            await self.event_bus.publish(
                Event(
                    event_type=EventType.ORDER_APPROVED,
                    data={
                        "symbol": order.symbol,
                        "side": order.side.value,
                        "order_type": order.order_type if isinstance(order.order_type, str) else order.order_type.value,
                        "quantity": str(order.quantity),
                        "market": order.market.value,
                        "strategy": order.strategy,
                        "price": str(order.price) if order.price else None,
                        "stop_loss": str(order.stop_loss) if order.stop_loss else None,
                        "order_id": order.order_id,
                    },
                    source="risk_manager",
                )
            )
        else:
            logger.warning(
                f"Risk rejected: {order.side.value} {order.quantity} {order.symbol} "
                f"— {decision.reason}"
            )
            await self.event_bus.publish(
                Event(
                    event_type=EventType.ORDER_REJECTED,
                    data={
                        "symbol": order.symbol,
                        "side": order.side.value,
                        "quantity": str(order.quantity),
                        "reason": decision.reason,
                        "strategy": order.strategy,
                    },
                    source="risk_manager",
                )
            )

    async def _on_order_filled(self, event: Event) -> None:
        """Decrement pending order count on fill."""
        market = event.data.get("market", "crypto")
        if market in self._pending_orders_per_exchange:
            self._pending_orders_per_exchange[market] = max(
                0, self._pending_orders_per_exchange[market] - 1
            )

    def validate_trade(self, order: Order) -> RiskDecision:
        """Run all risk checks against the order. First failure rejects."""
        checks = [
            self._check_circuit_breaker,
            self._check_budget_available,
            self._check_position_limit,
            self._check_market_exposure,
            self._check_daily_loss_limit,
            self._check_weekly_loss_limit,
            self._check_cash_reserve,
            self._check_max_open_positions,
            self._check_max_concurrent_orders,
        ]

        for check in checks:
            decision = check(order)
            if not decision.approved:
                return decision

        return RiskDecision(approved=True)

    def _check_circuit_breaker(self, order: Order) -> RiskDecision:
        """Reject if any circuit breaker is tripped."""
        if self.circuit_breakers.is_tripped:
            return RiskDecision(
                approved=False,
                reason=f"Circuit breaker active: {self.circuit_breakers.trip_reason}",
            )
        return RiskDecision(approved=True)

    def _check_budget_available(self, order: Order) -> RiskDecision:
        """Check if there's enough cash for the trade."""
        if order.side == Side.SELL:
            return RiskDecision(approved=True)

        price = order.price or self._get_estimated_price(order.symbol)
        if price is None:
            return RiskDecision(approved=False, reason="Cannot determine price")

        cost = price * order.quantity
        if cost > self.portfolio.get_cash_balance():
            return RiskDecision(
                approved=False,
                reason=f"Insufficient cash: need {cost}, have {self.portfolio.get_cash_balance()}",
            )
        return RiskDecision(approved=True)

    def _check_position_limit(self, order: Order) -> RiskDecision:
        """Per-asset exposure must not exceed configured percentage."""
        if order.side == Side.SELL:
            return RiskDecision(approved=True)

        equity = self.portfolio.get_total_equity()
        if equity == 0:
            return RiskDecision(approved=False, reason="Zero equity")

        max_per_asset = equity * self.config.per_asset_max_pct / Decimal("100")
        current_exposure = self.portfolio.get_asset_exposure(order.symbol)
        price = order.price or self._get_estimated_price(order.symbol)
        if price is None:
            return RiskDecision(approved=False, reason="Cannot determine price")

        new_exposure = current_exposure + price * order.quantity
        if new_exposure > max_per_asset:
            return RiskDecision(
                approved=False,
                reason=f"Per-asset limit: {order.symbol} exposure {new_exposure} "
                f"would exceed {max_per_asset} ({self.config.per_asset_max_pct}%)",
            )
        return RiskDecision(approved=True)

    def _check_market_exposure(self, order: Order) -> RiskDecision:
        """Per-market exposure must not exceed configured percentage."""
        if order.side == Side.SELL:
            return RiskDecision(approved=True)

        equity = self.portfolio.get_total_equity()
        if equity == 0:
            return RiskDecision(approved=False, reason="Zero equity")

        max_per_market = equity * self.config.per_market_max_pct / Decimal("100")
        current_exposure = self.portfolio.get_market_exposure(order.market)
        price = order.price or self._get_estimated_price(order.symbol)
        if price is None:
            return RiskDecision(approved=False, reason="Cannot determine price")

        new_exposure = current_exposure + price * order.quantity
        if new_exposure > max_per_market:
            return RiskDecision(
                approved=False,
                reason=f"Per-market limit: {order.market.value} exposure {new_exposure} "
                f"would exceed {max_per_market} ({self.config.per_market_max_pct}%)",
            )
        return RiskDecision(approved=True)

    def _check_daily_loss_limit(self, order: Order) -> RiskDecision:
        """Halt if daily losses exceed configured percentage."""
        equity = self.portfolio.get_total_equity()
        if equity == 0:
            return RiskDecision(approved=True)

        daily_pnl = self.portfolio.get_daily_pnl()
        max_loss = equity * self.config.daily_loss_limit_pct / Decimal("100")

        if daily_pnl < -max_loss:
            return RiskDecision(
                approved=False,
                reason=f"Daily loss limit: P&L {daily_pnl} exceeds -{max_loss} "
                f"({self.config.daily_loss_limit_pct}%)",
            )
        return RiskDecision(approved=True)

    def _check_weekly_loss_limit(self, order: Order) -> RiskDecision:
        """Halt if weekly losses exceed configured percentage."""
        equity = self.portfolio.get_total_equity()
        if equity == 0:
            return RiskDecision(approved=True)

        weekly_pnl = self.portfolio.get_weekly_pnl()
        max_loss = equity * self.config.weekly_loss_limit_pct / Decimal("100")

        if weekly_pnl < -max_loss:
            return RiskDecision(
                approved=False,
                reason=f"Weekly loss limit: P&L {weekly_pnl} exceeds -{max_loss} "
                f"({self.config.weekly_loss_limit_pct}%)",
            )
        return RiskDecision(approved=True)

    def _check_cash_reserve(self, order: Order) -> RiskDecision:
        """Ensure cash reserve is maintained after trade."""
        if order.side == Side.SELL:
            return RiskDecision(approved=True)

        equity = self.portfolio.get_total_equity()
        min_cash = equity * self.config.cash_reserve_pct / Decimal("100")
        price = order.price or self._get_estimated_price(order.symbol)
        if price is None:
            return RiskDecision(approved=False, reason="Cannot determine price")

        cost = price * order.quantity
        remaining_cash = self.portfolio.get_cash_balance() - cost

        if remaining_cash < min_cash:
            return RiskDecision(
                approved=False,
                reason=f"Cash reserve: remaining {remaining_cash} would be below "
                f"minimum {min_cash} ({self.config.cash_reserve_pct}%)",
            )
        return RiskDecision(approved=True)

    def _check_max_open_positions(self, order: Order) -> RiskDecision:
        """Check total open positions against maximum."""
        if order.side == Side.SELL:
            return RiskDecision(approved=True)

        # Only count as new if we don't already hold this symbol
        current = self.portfolio.get_open_position_count()
        is_new_position = self.portfolio.get_position(order.symbol) is None
        if is_new_position and current >= self.config.max_open_positions:
            return RiskDecision(
                approved=False,
                reason=f"Max open positions: {current} >= {self.config.max_open_positions}",
            )
        return RiskDecision(approved=True)

    def _check_max_concurrent_orders(self, order: Order) -> RiskDecision:
        """Check pending orders per exchange against maximum."""
        exchange_key = order.market.value
        pending = self._pending_orders_per_exchange.get(exchange_key, 0)
        if pending >= self.config.max_concurrent_orders_per_exchange:
            return RiskDecision(
                approved=False,
                reason=f"Max concurrent orders for {exchange_key}: "
                f"{pending} >= {self.config.max_concurrent_orders_per_exchange}",
            )
        return RiskDecision(approved=True)

    def _get_estimated_price(self, symbol: str) -> Decimal | None:
        """Get estimated price from current position or return None."""
        pos = self.portfolio.get_position(symbol)
        if pos:
            return pos.current_price
        return None
