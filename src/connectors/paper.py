"""Paper trading connector — simulates exchange execution for strategy validation."""

from __future__ import annotations

import asyncio
import random
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable
from uuid import uuid4

from loguru import logger

from src.connectors.base import (
    Balance,
    BaseConnector,
    Market,
    Order,
    OrderBook,
    OrderBookLevel,
    OrderResult,
    OrderStatus,
    OrderType,
    PositionInfo,
    Side,
)
from src.event_bus import Event, EventBus, EventType


class PaperPosition:
    """Internal position tracking for the paper connector."""

    def __init__(self, symbol: str, market: Market):
        self.symbol = symbol
        self.market = market
        self.quantity = Decimal("0")
        self.avg_cost = Decimal("0")
        self.realised_pnl = Decimal("0")

    def add(self, quantity: Decimal, price: Decimal) -> None:
        """Add to position (buy)."""
        if self.quantity == 0:
            self.avg_cost = price
            self.quantity = quantity
        else:
            total_cost = self.avg_cost * self.quantity + price * quantity
            self.quantity += quantity
            self.avg_cost = (total_cost / self.quantity).quantize(
                Decimal("0.00000001"), rounding=ROUND_HALF_UP
            )

    def reduce(self, quantity: Decimal, price: Decimal) -> Decimal:
        """Reduce position (sell). Returns realised P&L for this portion."""
        quantity = min(quantity, self.quantity)
        pnl = (price - self.avg_cost) * quantity
        self.realised_pnl += pnl
        self.quantity -= quantity
        if self.quantity == 0:
            self.avg_cost = Decimal("0")
        return pnl

    @property
    def is_open(self) -> bool:
        return self.quantity > 0


class PaperConnector(BaseConnector):
    """Simulated exchange for paper trading.

    Supports market and limit orders with configurable slippage and fees.
    Maintains virtual cash balance and positions.
    """

    def __init__(
        self,
        market: Market,
        event_bus: EventBus,
        initial_balance: Decimal = Decimal("10000"),
        slippage_pct: Decimal = Decimal("0.0005"),
        fee_pct: Decimal = Decimal("0.001"),
    ):
        super().__init__(name=f"paper_{market.value}", market=market)
        self.event_bus = event_bus
        self._cash = initial_balance
        self._initial_balance = initial_balance
        self._slippage_pct = slippage_pct
        self._fee_pct = fee_pct

        # State
        self._positions: dict[str, PaperPosition] = {}
        self._prices: dict[str, Decimal] = {}
        self._pending_orders: dict[str, Order] = {}
        self._filled_orders: list[OrderResult] = []

        # Price feed
        self._price_callbacks: list[Callable] = []
        self._price_feed_task: asyncio.Task | None = None
        self._running = False

    async def connect(self) -> bool:
        self._connected = True
        logger.info(f"Paper connector ({self.market.value}) connected")
        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._price_feed_task and not self._price_feed_task.done():
            self._price_feed_task.cancel()
            try:
                await self._price_feed_task
            except asyncio.CancelledError:
                pass
        self._connected = False
        logger.info(f"Paper connector ({self.market.value}) disconnected")

    def set_price(self, symbol: str, price: Decimal) -> None:
        """Manually set a price (useful for testing and initial seeding)."""
        self._prices[symbol] = price

    async def get_price(self, symbol: str) -> Decimal:
        if symbol not in self._prices:
            raise ValueError(f"No price available for {symbol}")
        return self._prices[symbol]

    async def get_orderbook(self, symbol: str) -> OrderBook:
        price = await self.get_price(symbol)
        spacing = price * Decimal("0.001")
        bids = [
            OrderBookLevel(
                price=price - spacing * Decimal(str(i + 1)),
                quantity=Decimal(str(random.uniform(0.1, 10.0))).quantize(
                    Decimal("0.001")
                ),
            )
            for i in range(10)
        ]
        asks = [
            OrderBookLevel(
                price=price + spacing * Decimal(str(i + 1)),
                quantity=Decimal(str(random.uniform(0.1, 10.0))).quantize(
                    Decimal("0.001")
                ),
            )
            for i in range(10)
        ]
        return OrderBook(symbol=symbol, bids=bids, asks=asks)

    async def place_order(self, order: Order) -> OrderResult:
        """Execute an order against the paper trading simulator."""
        if order.order_type == OrderType.MARKET:
            return await self._execute_market_order(order)
        elif order.order_type == OrderType.LIMIT:
            return await self._place_limit_order(order)
        else:
            raise ValueError(f"Unsupported order type: {order.order_type}")

    async def _execute_market_order(self, order: Order) -> OrderResult:
        """Fill a market order immediately with slippage."""
        current_price = await self.get_price(order.symbol)

        # Apply slippage
        if order.side == Side.BUY:
            fill_price = current_price * (Decimal("1") + self._slippage_pct)
        else:
            fill_price = current_price * (Decimal("1") - self._slippage_pct)

        fill_price = fill_price.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        cost = fill_price * order.quantity
        fees = cost * self._fee_pct

        # Check balance for buys
        if order.side == Side.BUY:
            total_cost = cost + fees
            if total_cost > self._cash:
                return OrderResult(
                    order_id=order.order_id,
                    exchange_order_id=str(uuid4()),
                    status=OrderStatus.REJECTED,
                    filled_quantity=Decimal("0"),
                    filled_price=Decimal("0"),
                    fees=Decimal("0"),
                    symbol=order.symbol,
                    side=order.side,
                    market=order.market,
                    strategy=order.strategy,
                )

        # Execute
        result = self._fill_order(order, fill_price, fees)

        # Publish fill event
        await self.event_bus.publish(
            Event(
                event_type=EventType.ORDER_FILLED,
                data={
                    "order_id": result.order_id,
                    "symbol": result.symbol,
                    "side": result.side.value,
                    "quantity": str(result.filled_quantity),
                    "price": str(result.filled_price),
                    "fees": str(result.fees),
                    "market": result.market.value,
                    "strategy": result.strategy,
                    "cost": str(result.filled_price * result.filled_quantity),
                },
                source=self.name,
            )
        )

        return result

    async def _place_limit_order(self, order: Order) -> OrderResult:
        """Place a limit order. Checks if it can be filled immediately."""
        if order.price is None:
            raise ValueError("Limit orders require a price")

        current_price = await self.get_price(order.symbol)

        # Check if limit order can fill immediately
        can_fill = (
            (order.side == Side.BUY and current_price <= order.price)
            or (order.side == Side.SELL and current_price >= order.price)
        )

        if can_fill:
            fill_price = order.price
            cost = fill_price * order.quantity
            fees = cost * self._fee_pct

            if order.side == Side.BUY and (cost + fees) > self._cash:
                return OrderResult(
                    order_id=order.order_id,
                    exchange_order_id=str(uuid4()),
                    status=OrderStatus.REJECTED,
                    filled_quantity=Decimal("0"),
                    filled_price=Decimal("0"),
                    fees=Decimal("0"),
                    symbol=order.symbol,
                    side=order.side,
                    market=order.market,
                    strategy=order.strategy,
                )

            result = self._fill_order(order, fill_price, fees)
            await self.event_bus.publish(
                Event(
                    event_type=EventType.ORDER_FILLED,
                    data={
                        "order_id": result.order_id,
                        "symbol": result.symbol,
                        "side": result.side.value,
                        "quantity": str(result.filled_quantity),
                        "price": str(result.filled_price),
                        "fees": str(result.fees),
                        "market": result.market.value,
                        "strategy": result.strategy,
                        "cost": str(result.filled_price * result.filled_quantity),
                    },
                    source=self.name,
                )
            )
            return result

        # Store as pending
        self._pending_orders[order.order_id] = order
        return OrderResult(
            order_id=order.order_id,
            exchange_order_id=str(uuid4()),
            status=OrderStatus.PENDING,
            filled_quantity=Decimal("0"),
            filled_price=Decimal("0"),
            fees=Decimal("0"),
            symbol=order.symbol,
            side=order.side,
            market=order.market,
            strategy=order.strategy,
        )

    def _fill_order(self, order: Order, fill_price: Decimal, fees: Decimal) -> OrderResult:
        """Apply a fill to internal state (positions and cash)."""
        if order.side == Side.BUY:
            cost = fill_price * order.quantity + fees
            self._cash -= cost
            pos = self._positions.setdefault(
                order.symbol, PaperPosition(order.symbol, order.market)
            )
            pos.add(order.quantity, fill_price)
        else:
            pos = self._positions.get(order.symbol)
            if pos and pos.is_open:
                pos.reduce(order.quantity, fill_price)
            revenue = fill_price * order.quantity - fees
            self._cash += revenue

        result = OrderResult(
            order_id=order.order_id,
            exchange_order_id=str(uuid4()),
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            filled_price=fill_price,
            fees=fees,
            symbol=order.symbol,
            side=order.side,
            market=order.market,
            strategy=order.strategy,
        )
        self._filled_orders.append(result)

        logger.info(
            f"Paper {order.side.value} {order.quantity} {order.symbol} "
            f"@ {fill_price} (fees: {fees})"
        )
        return result

    async def check_pending_orders(self) -> list[OrderResult]:
        """Check if any pending limit orders should now be filled."""
        filled = []
        to_remove = []

        for order_id, order in self._pending_orders.items():
            if order.price is None:
                continue

            current_price = self._prices.get(order.symbol)
            if current_price is None:
                continue

            can_fill = (
                (order.side == Side.BUY and current_price <= order.price)
                or (order.side == Side.SELL and current_price >= order.price)
            )

            if can_fill:
                fees = order.price * order.quantity * self._fee_pct

                if order.side == Side.BUY and (order.price * order.quantity + fees) > self._cash:
                    continue

                result = self._fill_order(order, order.price, fees)
                filled.append(result)
                to_remove.append(order_id)

                await self.event_bus.publish(
                    Event(
                        event_type=EventType.ORDER_FILLED,
                        data={
                            "order_id": result.order_id,
                            "symbol": result.symbol,
                            "side": result.side.value,
                            "quantity": str(result.filled_quantity),
                            "price": str(result.filled_price),
                            "fees": str(result.fees),
                            "market": result.market.value,
                            "strategy": result.strategy,
                            "cost": str(result.filled_price * result.filled_quantity),
                        },
                        source=self.name,
                    )
                )

        for order_id in to_remove:
            del self._pending_orders[order_id]

        return filled

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self._pending_orders:
            del self._pending_orders[order_id]
            return True
        return False

    async def get_positions(self) -> list[PositionInfo]:
        positions = []
        for symbol, pos in self._positions.items():
            if not pos.is_open:
                continue
            current_price = self._prices.get(symbol, pos.avg_cost)
            unrealised = (current_price - pos.avg_cost) * pos.quantity
            positions.append(
                PositionInfo(
                    symbol=symbol,
                    market=pos.market,
                    quantity=pos.quantity,
                    avg_cost=pos.avg_cost,
                    current_price=current_price,
                    unrealised_pnl=unrealised,
                )
            )
        return positions

    async def get_balance(self) -> Balance:
        positions_value = Decimal("0")
        for symbol, pos in self._positions.items():
            if pos.is_open:
                price = self._prices.get(symbol, pos.avg_cost)
                positions_value += price * pos.quantity

        return Balance(
            total_equity=self._cash + positions_value,
            available_cash=self._cash,
            positions_value=positions_value,
        )

    async def subscribe_prices(
        self,
        symbols: list[str],
        callback: Callable,
    ) -> None:
        """Start synthetic price feed for given symbols."""
        self._price_callbacks.append(callback)

        if not self._running:
            self._running = True
            self._price_feed_task = asyncio.create_task(
                self._run_price_feed(symbols)
            )

    async def _run_price_feed(self, symbols: list[str], interval: float = 1.0) -> None:
        """Generate synthetic price movements using random walk."""
        # Seed initial prices if not set
        default_prices = {
            "BTC/USDT": Decimal("60000"),
            "ETH/USDT": Decimal("3000"),
            "SOL/USDT": Decimal("150"),
            "AAPL": Decimal("180"),
            "NVDA": Decimal("800"),
            "TSLA": Decimal("250"),
            "SHEL.L": Decimal("2500"),
            "AZN.L": Decimal("10000"),
            "HSBA.L": Decimal("650"),
        }
        for symbol in symbols:
            if symbol not in self._prices:
                self._prices[symbol] = default_prices.get(
                    symbol, Decimal("100")
                )

        while self._running:
            try:
                for symbol in symbols:
                    price = self._prices[symbol]
                    # Random walk: ±0.5% per tick
                    change_pct = Decimal(str(random.gauss(0, 0.005)))
                    new_price = price * (Decimal("1") + change_pct)
                    new_price = max(new_price, Decimal("0.01"))
                    new_price = new_price.quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    self._prices[symbol] = new_price

                    # Publish price update event
                    await self.event_bus.publish(
                        Event(
                            event_type=EventType.PRICE_UPDATE,
                            data={
                                "symbol": symbol,
                                "price": str(new_price),
                                "market": self.market.value,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                            source=self.name,
                        )
                    )

                    for cb in self._price_callbacks:
                        await cb(symbol, new_price)

                # Check pending limit orders
                await self.check_pending_orders()

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Price feed error: {e}")
                await asyncio.sleep(interval)

    @property
    def pending_order_count(self) -> int:
        return len(self._pending_orders)

    @property
    def cash(self) -> Decimal:
        return self._cash
