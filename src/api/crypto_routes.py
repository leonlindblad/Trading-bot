"""REST API endpoints for the crypto-only trading bot."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request

from src.api.market_feed import _fetch_crypto_prices

import time


def create_crypto_router() -> APIRouter:
    """Create API router with crypto bot endpoints."""
    router = APIRouter()

    def _get_bot(request: Request):
        return request.app.state.bot

    @router.get("/health")
    async def health(request: Request):
        """System health check."""
        bot = _get_bot(request)
        connectors_status = {}
        if bot:
            for name, conn in bot.connectors.items():
                connectors_status[name] = {
                    "connected": conn.is_connected,
                    "pending_orders": conn.pending_order_count,
                }
        return {
            "status": "healthy" if bot and bot._running else "stopped",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "connectors": connectors_status,
            "mode": "paper",
        }

    @router.get("/portfolio")
    async def portfolio(request: Request):
        """Current portfolio summary."""
        bot = _get_bot(request)
        if not bot or not bot.portfolio:
            return {"error": "Bot not running"}

        pm = bot.portfolio
        balance = pm.get_balance()
        return {
            "total_equity": str(balance.total_equity),
            "cash_balance": str(balance.available_cash),
            "positions_value": str(balance.positions_value),
            "daily_pnl": str(pm.get_daily_pnl()),
            "weekly_pnl": str(pm.get_weekly_pnl()),
            "total_pnl": str(pm.get_total_pnl()),
            "open_positions": pm.get_open_position_count(),
        }

    @router.get("/positions")
    async def positions(request: Request):
        """All open crypto positions with live P&L."""
        bot = _get_bot(request)
        if not bot or not bot.portfolio:
            return {"error": "Bot not running"}

        return [
            {
                "symbol": p.symbol,
                "market": p.market.value,
                "quantity": str(p.quantity),
                "avg_cost": str(p.avg_cost),
                "current_price": str(p.current_price),
                "unrealised_pnl": str(p.unrealised_pnl),
                "strategy": p.strategy,
            }
            for p in bot.portfolio.get_positions()
        ]

    @router.get("/trades")
    async def trades(request: Request, limit: int = 100):
        """Trade history."""
        bot = _get_bot(request)
        if not bot or not bot.portfolio:
            return {"error": "Bot not running"}
        return bot.portfolio.get_trades()[-limit:]

    @router.get("/strategies")
    async def strategies(request: Request):
        """Strategy status."""
        bot = _get_bot(request)
        if not bot:
            return {"error": "Bot not running"}

        if bot.strategy_manager:
            return bot.strategy_manager.get_status()

        return {
            "strategies": {
                "momentum": {"enabled": bot.config.momentum.enabled},
                "dca": {"enabled": bot.config.dca.enabled},
                "grid": {"enabled": bot.config.grid.enabled},
            },
            "eval_count": 0,
            "signal_count": 0,
        }

    @router.post("/strategies/{name}/toggle")
    async def toggle_strategy(name: str, request: Request):
        """Enable or disable a strategy."""
        bot = _get_bot(request)
        if not bot:
            return {"error": "Bot not running"}

        if name == "momentum":
            bot.config.momentum.enabled = not bot.config.momentum.enabled
            return {"momentum": {"enabled": bot.config.momentum.enabled}}
        elif name == "dca":
            bot.config.dca.enabled = not bot.config.dca.enabled
            return {"dca": {"enabled": bot.config.dca.enabled}}
        elif name == "grid":
            bot.config.grid.enabled = not bot.config.grid.enabled
            return {"grid": {"enabled": bot.config.grid.enabled}}
        return {"error": f"Unknown strategy: {name}"}

    @router.get("/risk/status")
    async def risk_status(request: Request):
        """Risk limits usage and circuit breaker state."""
        bot = _get_bot(request)
        if not bot or not bot.portfolio or not bot.risk_manager:
            return {"error": "Bot not running"}

        pm = bot.portfolio
        equity = pm.get_total_equity()
        config = bot.config.risk

        return {
            "total_equity": str(equity),
            "daily_pnl": str(pm.get_daily_pnl()),
            "weekly_pnl": str(pm.get_weekly_pnl()),
            "open_positions": pm.get_open_position_count(),
            "max_positions": config.max_open_positions,
            "cash_reserve_pct": str(config.cash_reserve_pct),
            "circuit_breaker": bot.circuit_breakers.get_status()
            if bot.circuit_breakers
            else None,
        }

    @router.get("/logs")
    async def logs(limit: int = 100):
        """Return recent log lines from the crypto bot log file."""
        log_file = Path("logs/crypto_bot.log")
        if not log_file.exists():
            return {"lines": []}
        try:
            with open(log_file) as f:
                all_lines = f.readlines()
            return {"lines": [line.rstrip() for line in all_lines[-limit:]]}
        except Exception:
            return {"lines": []}

    @router.get("/market-feed")
    async def market_feed():
        """Live crypto market data."""
        crypto = await _fetch_crypto_prices()
        return {
            "crypto": crypto,
            "timestamp": time.time(),
        }

    @router.post("/emergency-stop")
    async def emergency_stop(request: Request):
        """Halt all trading immediately."""
        bot = _get_bot(request)
        if not bot or not bot.circuit_breakers:
            return {"error": "Bot not running"}

        await bot.circuit_breakers.trip("Manual emergency stop", auto_reset=False)
        return {"status": "Trading halted", "circuit_breaker": "tripped"}

    return router
