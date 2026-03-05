"""FastAPI application factory for the crypto-only bot."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.crypto_dashboard import create_crypto_dashboard_router
from src.api.crypto_routes import create_crypto_router

if TYPE_CHECKING:
    from src.crypto_main import CryptoBot


def create_crypto_app(bot: CryptoBot | None = None) -> FastAPI:
    """Create and configure the crypto bot FastAPI application."""
    app = FastAPI(
        title="Crypto Trading Bot",
        description="Crypto-only automated trading system",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.bot = bot

    # API routes
    router = create_crypto_router()
    app.include_router(router, prefix="/api")

    # Dashboard
    password = ""
    if bot and bot.config:
        password = bot.config.settings.dashboard_password
    app.include_router(create_crypto_dashboard_router(password))

    return app
