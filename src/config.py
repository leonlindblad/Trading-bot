"""Application configuration loaded from environment variables and config.yaml."""

from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


def _load_yaml_config() -> dict[str, Any]:
    """Load strategy and asset config from config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


class MomentumConfig:
    """Momentum strategy parameters."""

    def __init__(self, data: dict[str, Any] | None = None):
        data = data or {}
        self.enabled: bool = data.get("enabled", True)
        self.timeframe: str = data.get("timeframe", "1h")
        self.ema_fast: int = data.get("ema_fast", 12)
        self.ema_slow: int = data.get("ema_slow", 26)
        self.rsi_period: int = data.get("rsi_period", 14)
        self.volume_threshold: float = data.get("volume_threshold", 1.5)
        self.trailing_stop_atr_mult: float = data.get("trailing_stop_atr_mult", 2.0)
        self.max_positions_per_market: int = data.get("max_positions_per_market", 3)
        self.position_size_pct: float = data.get("position_size_pct", 2.0)


class DCAConfig:
    """DCA strategy parameters."""

    def __init__(self, data: dict[str, Any] | None = None):
        data = data or {}
        self.enabled: bool = data.get("enabled", True)
        self.schedule: str = data.get("schedule", "daily")
        self.base_amount: float = data.get("base_amount", 50)
        self.dip_threshold_pct: float = data.get("dip_threshold_pct", 5)
        self.dip_multiplier: float = data.get("dip_multiplier", 1.5)
        self.crash_threshold_pct: float = data.get("crash_threshold_pct", 15)
        self.crash_multiplier: float = data.get("crash_multiplier", 2.0)
        self.allocation: dict[str, float] = data.get("allocation", {})


class GridConfig:
    """Grid trading parameters."""

    def __init__(self, data: dict[str, Any] | None = None):
        data = data or {}
        self.enabled: bool = data.get("enabled", True)
        self.num_levels: int = data.get("num_levels", 10)
        self.spacing_pct: float = data.get("spacing_pct", 1.5)
        self.auto_range: bool = data.get("auto_range", True)
        self.recalculate_weekly: bool = data.get("recalculate_weekly", True)
        self.budget_per_asset_pct: float = data.get("budget_per_asset_pct", 5)


class RiskConfig:
    """Risk management parameters."""

    def __init__(self, data: dict[str, Any] | None = None):
        data = data or {}
        self.total_budget: Decimal = Decimal(str(data.get("total_budget", 10000)))
        self.per_trade_max_pct: Decimal = Decimal(str(data.get("per_trade_max_pct", 2)))
        self.per_asset_max_pct: Decimal = Decimal(str(data.get("per_asset_max_pct", 15)))
        self.per_market_max_pct: Decimal = Decimal(str(data.get("per_market_max_pct", 50)))
        self.daily_loss_limit_pct: Decimal = Decimal(
            str(data.get("daily_loss_limit_pct", 3))
        )
        self.weekly_loss_limit_pct: Decimal = Decimal(
            str(data.get("weekly_loss_limit_pct", 7))
        )
        self.max_open_positions: int = data.get("max_open_positions", 15)
        self.max_concurrent_orders_per_exchange: int = data.get(
            "max_concurrent_orders_per_exchange", 5
        )
        self.cash_reserve_pct: Decimal = Decimal(str(data.get("cash_reserve_pct", 20)))


class AssetConfig:
    """Single asset configuration."""

    def __init__(self, symbol: str, strategies: list[str], market: str):
        self.symbol = symbol
        self.strategies = strategies
        self.market = market


class PaperTradingConfig:
    """Paper trading parameters."""

    def __init__(self, data: dict[str, Any] | None = None):
        data = data or {}
        self.initial_balance: Decimal = Decimal(
            str(data.get("initial_balance", 10000))
        )
        self.slippage_pct: Decimal = Decimal(str(data.get("slippage_pct", "0.05")))
        self.fee_pct: Decimal = Decimal(str(data.get("fee_pct", "0.1")))


class Settings(BaseSettings):
    """Main application settings from environment variables."""

    # Database
    database_url: str = "sqlite+aiosqlite:///trading_bot.db"
    redis_url: str = "redis://localhost:6379/0"

    # Binance
    binance_api_key: str = ""
    binance_secret: str = ""
    binance_testnet: bool = True

    # Alpaca
    alpaca_api_key: str = ""
    alpaca_secret: str = ""
    alpaca_paper: bool = True

    # Interactive Brokers
    ib_host: str = "127.0.0.1"
    ib_port: int = 4002
    ib_client_id: int = 1

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Trading mode
    paper_trading: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Dashboard
    dashboard_password: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


class AppConfig:
    """Complete application config combining env settings and YAML config."""

    def __init__(self, settings: Settings | None = None, yaml_data: dict | None = None):
        self.settings = settings or Settings()
        yaml_data = yaml_data if yaml_data is not None else _load_yaml_config()

        strategies = yaml_data.get("strategies", {})
        self.momentum = MomentumConfig(strategies.get("momentum"))
        self.dca = DCAConfig(strategies.get("dca"))
        self.grid = GridConfig(strategies.get("grid"))
        self.risk = RiskConfig(yaml_data.get("risk"))
        self.paper_trading_config = PaperTradingConfig(
            yaml_data.get("paper_trading")
        )

        # Parse assets
        self.assets: list[AssetConfig] = []
        for market, asset_list in yaml_data.get("assets", {}).items():
            for asset in asset_list:
                self.assets.append(
                    AssetConfig(
                        symbol=asset["symbol"],
                        strategies=asset.get("strategies", []),
                        market=market,
                    )
                )

    def get_assets_for_strategy(self, strategy_name: str) -> list[AssetConfig]:
        """Return assets that have a given strategy enabled."""
        return [a for a in self.assets if strategy_name in a.strategies]

    def get_assets_for_market(self, market: str) -> list[AssetConfig]:
        """Return assets in a given market."""
        return [a for a in self.assets if a.market == market]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


@lru_cache()
def get_config() -> AppConfig:
    """Get cached app config instance."""
    return AppConfig()
