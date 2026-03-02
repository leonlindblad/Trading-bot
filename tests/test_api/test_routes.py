"""Tests for API endpoints."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import AppConfig, Settings
from src.connectors.base import Market
from src.connectors.paper import PaperConnector
from src.event_bus import EventBus
from src.portfolio.manager import PortfolioManager
from src.risk.circuit_breakers import CircuitBreakerManager
from src.risk.manager import RiskManager


@pytest.fixture
def client():
    """Create a test client with a mock bot."""
    bot = MagicMock()
    bot._running = True

    event_bus = EventBus()
    bot.connectors = {
        "crypto": MagicMock(is_connected=True, pending_order_count=0),
    }
    bot.portfolio = PortfolioManager(event_bus=event_bus, initial_cash=Decimal("10000"))
    bot.circuit_breakers = CircuitBreakerManager(event_bus)
    bot.risk_manager = MagicMock()
    bot.config = AppConfig(settings=Settings(), yaml_data={})

    app = create_app(bot)
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_portfolio_endpoint(client):
    response = client.get("/api/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert "total_equity" in data
    assert "cash_balance" in data


def test_positions_endpoint(client):
    response = client.get("/api/positions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_trades_endpoint(client):
    response = client.get("/api/trades")
    assert response.status_code == 200


def test_strategies_endpoint(client):
    response = client.get("/api/strategies")
    assert response.status_code == 200


def test_risk_status_endpoint(client):
    response = client.get("/api/risk/status")
    assert response.status_code == 200
    data = response.json()
    assert "total_equity" in data


def test_emergency_stop(client):
    response = client.post("/api/emergency-stop")
    assert response.status_code == 200
    assert "halted" in response.json().get("status", "").lower()
