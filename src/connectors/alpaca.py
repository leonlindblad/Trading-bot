"""Alpaca connector stub — placeholder for Phase 3 implementation."""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from src.connectors.base import (
    Balance,
    BaseConnector,
    Market,
    Order,
    OrderBook,
    OrderResult,
    PositionInfo,
)


class AlpacaConnector(BaseConnector):
    """Alpaca US stocks connector (Phase 3)."""

    def __init__(self):
        super().__init__(name="alpaca", market=Market.US_STOCKS)

    async def connect(self) -> bool:
        raise NotImplementedError("Alpaca connector not yet implemented (Phase 3)")

    async def disconnect(self) -> None:
        raise NotImplementedError

    async def get_price(self, symbol: str) -> Decimal:
        raise NotImplementedError

    async def get_orderbook(self, symbol: str) -> OrderBook:
        raise NotImplementedError

    async def place_order(self, order: Order) -> OrderResult:
        raise NotImplementedError

    async def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError

    async def get_positions(self) -> list[PositionInfo]:
        raise NotImplementedError

    async def get_balance(self) -> Balance:
        raise NotImplementedError

    async def subscribe_prices(self, symbols: list[str], callback: Callable) -> None:
        raise NotImplementedError
