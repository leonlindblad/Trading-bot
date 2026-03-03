"""Strategy manager — bridges price feeds to strategy evaluation and signal generation.

This is the component that makes the bot actually trade. It:
1. Subscribes to PRICE_UPDATE events
2. Accumulates ticks into OHLCV candle DataFrames
3. Periodically evaluates each enabled strategy
4. Publishes SIGNAL_GENERATED events for the risk manager
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
from loguru import logger

from src.config import AppConfig
from src.connectors.base import Market, Side, Signal
from src.event_bus import Event, EventBus, EventType
from src.portfolio.manager import PortfolioManager
from src.risk.position_sizer import PositionSizer
from src.strategies.base import BaseStrategy
from src.strategies.dca import DCAStrategy
from src.strategies.grid import GridStrategy
from src.strategies.momentum import MomentumStrategy


class CandleAggregator:
    """Accumulates price ticks into OHLCV candle DataFrames per symbol."""

    def __init__(self, max_candles: int = 200):
        self._max_candles = max_candles
        self._candles: dict[str, list[dict]] = defaultdict(list)
        self._current_bar: dict[str, dict] = {}
        self._bar_count: dict[str, int] = defaultdict(int)

    def add_tick(self, symbol: str, price: float, volume: float = 1.0) -> bool:
        """Add a price tick. Returns True when a new candle closes.

        Uses a simple tick-count approach: every N ticks closes a candle.
        For paper trading with 1-second ticks, 60 ticks ≈ 1 minute.
        We use 10 ticks per candle for faster strategy evaluation during paper trading.
        """
        ticks_per_candle = 10

        if symbol not in self._current_bar:
            self._current_bar[symbol] = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
                "timestamp": datetime.now(timezone.utc),
            }
        else:
            bar = self._current_bar[symbol]
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["close"] = price
            bar["volume"] += volume

        self._bar_count[symbol] += 1

        if self._bar_count[symbol] >= ticks_per_candle:
            # Close the candle
            candle = self._current_bar.pop(symbol)
            self._candles[symbol].append(candle)

            # Trim to max candles
            if len(self._candles[symbol]) > self._max_candles:
                self._candles[symbol] = self._candles[symbol][-self._max_candles:]

            self._bar_count[symbol] = 0
            return True

        return False

    def get_dataframe(self, symbol: str) -> pd.DataFrame:
        """Get candle data as a DataFrame for strategy evaluation."""
        candles = self._candles.get(symbol, [])
        if not candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        return pd.DataFrame(candles)

    def candle_count(self, symbol: str) -> int:
        """Number of completed candles for a symbol."""
        return len(self._candles.get(symbol, []))


class StrategyManager:
    """Orchestrates strategy evaluation against accumulated market data.

    Subscribes to price updates, builds candles, runs strategies,
    and publishes signals for the risk manager to evaluate.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: AppConfig,
        portfolio: PortfolioManager,
        position_sizer: PositionSizer,
    ):
        self.event_bus = event_bus
        self.config = config
        self.portfolio = portfolio
        self.position_sizer = position_sizer

        self._aggregator = CandleAggregator()
        self._strategies: dict[str, list[tuple[BaseStrategy, list[str]]]] = {}
        self._running = False
        self._eval_count = 0
        self._signal_count = 0
        self._last_signals: dict[str, Signal] = {}

    async def start(self) -> None:
        """Initialize strategies and subscribe to price events."""
        self._init_strategies()
        await self.event_bus.subscribe(EventType.PRICE_UPDATE, self._on_price_update)
        self._running = True
        logger.info(
            f"StrategyManager started with {self._count_strategies()} strategy instances"
        )

    async def stop(self) -> None:
        """Stop the strategy manager."""
        self._running = False
        await self.event_bus.unsubscribe(EventType.PRICE_UPDATE, self._on_price_update)
        logger.info("StrategyManager stopped")

    def _init_strategies(self) -> None:
        """Create strategy instances based on config."""
        self._strategies = {
            "momentum": [],
            "dca": [],
            "grid": [],
        }

        # Group assets by market for strategy creation
        market_assets: dict[str, list[str]] = defaultdict(list)
        asset_strategies: dict[str, list[str]] = {}

        for asset in self.config.assets:
            market_assets[asset.market].append(asset.symbol)
            asset_strategies[asset.symbol] = asset.strategies

        # Create Momentum strategies (one per market)
        if self.config.momentum.enabled:
            for market_name, symbols in market_assets.items():
                market = Market(market_name)
                momentum_symbols = [
                    s for s in symbols if "momentum" in asset_strategies.get(s, [])
                ]
                if momentum_symbols:
                    strategy = MomentumStrategy(self.config.momentum, market)
                    self._strategies["momentum"].append((strategy, momentum_symbols))

        # Create DCA strategies (one per market)
        if self.config.dca.enabled:
            for market_name, symbols in market_assets.items():
                market = Market(market_name)
                dca_symbols = [
                    s for s in symbols if "dca" in asset_strategies.get(s, [])
                ]
                if dca_symbols:
                    strategy = DCAStrategy(self.config.dca, market)
                    self._strategies["dca"].append((strategy, dca_symbols))

        # Create Grid strategies (one per market)
        if self.config.grid.enabled:
            for market_name, symbols in market_assets.items():
                market = Market(market_name)
                grid_symbols = [
                    s for s in symbols if "grid" in asset_strategies.get(s, [])
                ]
                if grid_symbols:
                    strategy = GridStrategy(
                        self.config.grid,
                        market,
                        self.config.risk.total_budget,
                    )
                    self._strategies["grid"].append((strategy, grid_symbols))

    def _count_strategies(self) -> int:
        return sum(len(instances) for instances in self._strategies.values())

    async def _on_price_update(self, event: Event) -> None:
        """Handle incoming price tick — aggregate into candles and evaluate."""
        if not self._running:
            return

        symbol = event.data.get("symbol", "")
        price_str = event.data.get("price", "")
        if not symbol or not price_str:
            return

        price = float(price_str)
        candle_closed = self._aggregator.add_tick(symbol, price)

        if candle_closed:
            await self._evaluate_strategies(symbol)

    async def _evaluate_strategies(self, symbol: str) -> None:
        """Run all applicable strategies against current candle data for a symbol."""
        df = self._aggregator.get_dataframe(symbol)
        if df.empty:
            return

        # Get current position for this symbol
        pos_info = self.portfolio.get_position(symbol)
        current_position = None
        if pos_info:
            current_position = {
                "quantity": pos_info.quantity,
                "avg_cost": pos_info.avg_cost,
                "market": pos_info.market.value,
            }

        # Evaluate each strategy type
        for strategy_name, instances in self._strategies.items():
            for strategy, symbols in instances:
                if symbol not in symbols:
                    continue

                try:
                    signal = await strategy.evaluate(symbol, df, current_position)
                    self._eval_count += 1

                    if signal is not None:
                        await self._process_signal(signal, strategy_name)
                except Exception as e:
                    logger.error(
                        f"Strategy {strategy_name} error for {symbol}: {e}"
                    )

    async def _process_signal(self, signal: Signal, strategy_name: str) -> None:
        """Process a signal: apply position sizing and publish event."""
        # Apply position sizing for buy signals without quantity
        if signal.side == Side.BUY and signal.quantity <= 0:
            price = signal.price or Decimal("0")
            if price > 0:
                signal.quantity = self.position_sizer.calculate_size(
                    symbol=signal.symbol,
                    side=signal.side,
                    market=signal.market,
                    price=price,
                    strategy_pct=Decimal(str(self.config.momentum.position_size_pct)),
                )

            if signal.quantity <= 0:
                logger.debug(
                    f"Signal for {signal.symbol} dropped — position sizer returned 0"
                )
                return

        self._signal_count += 1
        self._last_signals[signal.symbol] = signal

        logger.info(
            f"Signal #{self._signal_count}: {signal.side.value} {signal.quantity} "
            f"{signal.symbol} via {strategy_name} ({signal.reason})"
        )

        # Publish for risk manager to evaluate
        await self.event_bus.publish(
            Event(
                event_type=EventType.SIGNAL_GENERATED,
                data={
                    "symbol": signal.symbol,
                    "side": signal.side.value,
                    "quantity": str(signal.quantity),
                    "price": str(signal.price) if signal.price else None,
                    "stop_loss": str(signal.stop_loss) if signal.stop_loss else None,
                    "market": signal.market.value,
                    "strategy": signal.strategy,
                    "reason": signal.reason,
                },
                source=f"strategy_manager.{strategy_name}",
            )
        )

    def get_status(self) -> dict:
        """Get strategy manager status for the API."""
        strategies_status = {}
        for name, instances in self._strategies.items():
            symbols = []
            states = {}
            for strategy, syms in instances:
                symbols.extend(syms)
                for s in syms:
                    state = strategy.get_state()
                    if state:
                        states[s] = state.get(s, state)

            strategies_status[name] = {
                "enabled": len(instances) > 0,
                "instances": len(instances),
                "symbols": symbols,
                "states": states,
            }

        return {
            "strategies": strategies_status,
            "eval_count": self._eval_count,
            "signal_count": self._signal_count,
            "last_signals": {
                sym: {
                    "side": sig.side.value,
                    "quantity": str(sig.quantity),
                    "reason": sig.reason,
                }
                for sym, sig in self._last_signals.items()
            },
            "candle_counts": {
                sym: self._aggregator.candle_count(sym)
                for sym in set(
                    s
                    for instances in self._strategies.values()
                    for _, symbols in instances
                    for s in symbols
                )
            },
        }
