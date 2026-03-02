"""REST API endpoints for monitoring and controlling the trading bot."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request


def create_router() -> APIRouter:
    """Create API router with all endpoints."""
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
        """All open positions with live P&L."""
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
        """Strategy status and configuration."""
        bot = _get_bot(request)
        if not bot:
            return {"error": "Bot not running"}

        return {
            "momentum": {
                "enabled": bot.config.momentum.enabled,
                "timeframe": bot.config.momentum.timeframe,
            },
            "dca": {
                "enabled": bot.config.dca.enabled,
                "schedule": bot.config.dca.schedule,
                "base_amount": bot.config.dca.base_amount,
            },
            "grid": {
                "enabled": bot.config.grid.enabled,
                "num_levels": bot.config.grid.num_levels,
                "spacing_pct": bot.config.grid.spacing_pct,
            },
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

    @router.post("/emergency-stop")
    async def emergency_stop(request: Request):
        """Halt all trading immediately."""
        bot = _get_bot(request)
        if not bot or not bot.circuit_breakers:
            return {"error": "Bot not running"}

        await bot.circuit_breakers.trip("Manual emergency stop", auto_reset=False)
        return {"status": "Trading halted", "circuit_breaker": "tripped"}

    return router
