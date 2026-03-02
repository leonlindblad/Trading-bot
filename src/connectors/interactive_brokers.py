"""Interactive Brokers connector stub — placeholder for Phase 3 implementation."""

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


class IBConnector(BaseConnector):
    """Interactive Brokers connector for UK/EU stocks (Phase 3)."""

    def __init__(self):
        super().__init__(name="interactive_brokers", market=Market.UK_STOCKS)

    async def connect(self) -> bool:
        raise NotImplementedError(
            "Interactive Brokers connector not yet implemented (Phase 3)"
        )

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
