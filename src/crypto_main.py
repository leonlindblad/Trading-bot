"""Crypto-only trading bot — entry point and orchestrator."""

from __future__ import annotations

import asyncio
import signal
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from loguru import logger

from src.config import (
    AppConfig,
    Settings,
)
from src.connectors.base import Market
from src.connectors.paper import PaperConnector
from src.event_bus import EventBus
from src.execution.engine import ExecutionEngine
from src.execution.order_manager import OrderManager
from src.portfolio.manager import PortfolioManager
from src.alerting.telegram import TelegramAlerter
from src.risk.circuit_breakers import CircuitBreakerManager
from src.risk.manager import RiskManager
from src.risk.position_sizer import PositionSizer
from src.strategies.manager import StrategyManager


def _load_crypto_config() -> dict[str, Any]:
    """Load crypto-specific config from crypto_config.yaml."""
    config_path = Path(__file__).parent.parent / "crypto_config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    raise FileNotFoundError(f"Crypto config not found: {config_path}")


class CryptoBot:
    """Crypto-only trading bot orchestrator."""

    def __init__(self, config: AppConfig | None = None):
        if config is None:
            yaml_data = _load_crypto_config()
            settings = Settings()
            settings.api_port = 8001
            config = AppConfig(settings=settings, yaml_data=yaml_data)
        self.config = config
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
        logger.info("Starting Crypto Trading Bot...")

        # Single paper trading connector for crypto market
        paper_config = self.config.paper_trading_config
        connector = PaperConnector(
            market=Market.CRYPTO,
            event_bus=self.event_bus,
            initial_balance=paper_config.initial_balance,
            slippage_pct=paper_config.slippage_pct / Decimal("100"),
            fee_pct=paper_config.fee_pct / Decimal("100"),
        )
        await connector.connect()
        self.connectors[Market.CRYPTO.value] = connector

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

        # Telegram alerts
        self.telegram = TelegramAlerter(
            bot_token=self.config.settings.telegram_bot_token,
            chat_id=self.config.settings.telegram_chat_id,
            event_bus=self.event_bus,
        )
        await self.telegram.start()

        # Strategy manager
        position_sizer = PositionSizer(self.config.risk, self.portfolio)
        self.strategy_manager = StrategyManager(
            event_bus=self.event_bus,
            config=self.config,
            portfolio=self.portfolio,
            position_sizer=position_sizer,
        )
        await self.strategy_manager.start()

        # Start price feeds
        market_assets = self.config.get_assets_for_market("crypto")
        symbols = [a.symbol for a in market_assets]
        if symbols:
            await connector.subscribe_prices(symbols, self._on_price)

        self._running = True
        logger.info("Crypto Bot started successfully")
        logger.info(
            f"Paper trading with ${paper_config.initial_balance} initial balance"
        )
        logger.info(f"Tracking {len(symbols)} crypto pairs")

    async def _on_price(self, symbol: str, price: Decimal) -> None:
        """Price callback from connector."""
        pass

    async def stop(self) -> None:
        """Gracefully shut down all components."""
        logger.info("Shutting down Crypto Bot...")
        self._running = False

        if self.strategy_manager:
            await self.strategy_manager.stop()

        for task in self._tasks:
            task.cancel()

        for connector in self.connectors.values():
            await connector.disconnect()

        logger.info("Crypto Bot stopped")


async def run_crypto_bot():
    """Run the crypto bot with the FastAPI server."""
    bot = CryptoBot()
    await bot.start()

    from src.api.crypto_app import create_crypto_app

    app = create_crypto_app(bot)

    config = uvicorn.Config(
        app,
        host=bot.config.settings.api_host,
        port=bot.config.settings.api_port,
        log_level="info",
    )
    server = uvicorn.Server(config)

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
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>CRYPTO</cyan> | {message}",
    )
    logger.add(
        "logs/crypto_bot.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
    )

    asyncio.run(run_crypto_bot())


if __name__ == "__main__":
    main()
