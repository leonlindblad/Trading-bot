"""FastAPI application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.dashboard import create_dashboard_router
from src.api.routes import create_router

if TYPE_CHECKING:
    from src.main import TradingBot


def create_app(bot: TradingBot | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Unified Trading Bot",
        description="Multi-market automated trading system",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store bot reference for route handlers
    app.state.bot = bot

    # Include API routes
    router = create_router()
    app.include_router(router, prefix="/api")

    # Dashboard (password-protected if DASHBOARD_PASSWORD is set)
    password = ""
    if bot and bot.config:
        password = bot.config.settings.dashboard_password
    app.include_router(create_dashboard_router(password))

    return app
