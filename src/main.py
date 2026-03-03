"""Application entry point — wires all components together and starts the bot."""

from __future__ import annotations

import asyncio
import signal
import sys
from decimal import Decimal

import uvicorn
from loguru import logger

from src.config import AppConfig, get_config
from src.connectors.base import Market
from src.connectors.paper import PaperConnector
from src.event_bus import EventBus
from src.execution.engine import ExecutionEngine
from src.execution.order_manager import OrderManager
from src.portfolio.manager import PortfolioManager
from src.risk.circuit_breakers import CircuitBreakerManager
from src.risk.manager import RiskManager
from src.risk.position_sizer import PositionSizer
from src.strategies.manager import StrategyManager


class TradingBot:
    """Main application orchestrator."""

    def __init__(self, config: AppConfig | None = None):
        self.config = config or get_config()
        self.event_bus = EventBus()
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Components
        self.connectors: dict[str, PaperConnector] = {}
        self.portfolio: PortfolioManager | None = None
        self.risk_manager: RiskManager | None = None
        self.circuit_breakers: CircuitBreakerManager | None = None
        self.execution_engine: ExecutionEngine | None = None
        self.order_manager: OrderManager | None = None
        self.strategy_manager: StrategyManager | None = None

    async def start(self) -> None:
        """Initialize and start all components."""
        logger.info("Starting Unified Trading Bot...")

        # Create paper trading connectors for each market
        paper_config = self.config.paper_trading_config
        for market in [Market.CRYPTO, Market.US_STOCKS, Market.UK_STOCKS]:
            connector = PaperConnector(
                market=market,
                event_bus=self.event_bus,
                initial_balance=paper_config.initial_balance / Decimal("3"),
                slippage_pct=paper_config.slippage_pct / Decimal("100"),
                fee_pct=paper_config.fee_pct / Decimal("100"),
            )
            await connector.connect()
            self.connectors[market.value] = connector

        # Portfolio manager
        self.portfolio = PortfolioManager(
            event_bus=self.event_bus,
            initial_cash=paper_config.initial_balance,
        )
        await self.portfolio.start()

        # Circuit breakers
        self.circuit_breakers = CircuitBreakerManager(self.event_bus)

        # Risk manager
        self.risk_manager = RiskManager(
            event_bus=self.event_bus,
            portfolio=self.portfolio,
            risk_config=self.config.risk,
            circuit_breakers=self.circuit_breakers,
        )
        await self.risk_manager.start()

        # Order manager
        self.order_manager = OrderManager(self.event_bus)
        await self.order_manager.start()

        # Execution engine
        self.execution_engine = ExecutionEngine(
            event_bus=self.event_bus,
            connectors=self.connectors,
        )
        await self.execution_engine.start()

        # Strategy manager — evaluates strategies against price data
        position_sizer = PositionSizer(self.config.risk, self.portfolio)
        self.strategy_manager = StrategyManager(
            event_bus=self.event_bus,
            config=self.config,
            portfolio=self.portfolio,
            position_sizer=position_sizer,
        )
        await self.strategy_manager.start()

        # Start price feeds (must be after strategy manager so it receives events)
        for market_name, connector in self.connectors.items():
            market_assets = self.config.get_assets_for_market(market_name)
            symbols = [a.symbol for a in market_assets]
            if symbols:
                await connector.subscribe_prices(symbols, self._on_price)

        self._running = True
        logger.info("Trading Bot started successfully")
        logger.info(
            f"Paper trading with {paper_config.initial_balance} initial balance"
        )
        logger.info(
            f"Tracking {len(self.config.assets)} assets across "
            f"{len(self.connectors)} markets"
        )

    async def _on_price(self, symbol: str, price: Decimal) -> None:
        """Price callback from connectors (used for logging)."""
        pass

    async def stop(self) -> None:
        """Gracefully shut down all components."""
        logger.info("Shutting down Trading Bot...")
        self._running = False

        if self.strategy_manager:
            await self.strategy_manager.stop()

        for task in self._tasks:
            task.cancel()

        for connector in self.connectors.values():
            await connector.disconnect()

        logger.info("Trading Bot stopped")


async def run_bot():
    """Run the trading bot with the FastAPI server."""
    bot = TradingBot()
    await bot.start()

    # Import and configure the FastAPI app
    from src.api.app import create_app

    app = create_app(bot)

    config = uvicorn.Config(
        app,
        host=bot.config.settings.api_host,
        port=bot.config.settings.api_port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.stop()))

    try:
        await server.serve()
    finally:
        await bot.stop()


def main():
    """CLI entry point."""
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    logger.add(
        "logs/trading_bot.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
    )

    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
