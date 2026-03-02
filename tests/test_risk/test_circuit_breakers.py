"""Tests for circuit breaker logic."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.event_bus import EventBus
from src.risk.circuit_breakers import CircuitBreakerManager


@pytest.mark.asyncio
async def test_trip_and_reset(event_bus):
    """Circuit breaker should trip and reset correctly."""
    cb = CircuitBreakerManager(event_bus)

    assert not cb.is_tripped

    await cb.trip("test reason")
    assert cb.is_tripped
    assert cb.trip_reason == "test reason"

    cb.reset()
    assert not cb.is_tripped
    assert cb.trip_reason == ""


@pytest.mark.asyncio
async def test_execution_failure_tracking(event_bus):
    """Should trigger after 3 consecutive failures."""
    cb = CircuitBreakerManager(event_bus)

    assert not cb.record_execution_failure("paper")
    assert not cb.record_execution_failure("paper")
    assert cb.record_execution_failure("paper")  # 3rd failure triggers


@pytest.mark.asyncio
async def test_execution_success_resets_count(event_bus):
    """Success should reset failure count."""
    cb = CircuitBreakerManager(event_bus)

    cb.record_execution_failure("paper")
    cb.record_execution_failure("paper")
    cb.record_execution_success("paper")

    # After reset, first failure again
    assert not cb.record_execution_failure("paper")


@pytest.mark.asyncio
async def test_price_anomaly_detection(event_bus):
    """Should detect large price movements."""
    cb = CircuitBreakerManager(event_bus)

    # First price sets baseline
    assert not cb.check_price_anomaly("BTC/USDT", Decimal("60000"))

    # Normal movement
    assert not cb.check_price_anomaly("BTC/USDT", Decimal("60100"))

    # Anomalous movement (>10%)
    assert cb.check_price_anomaly("BTC/USDT", Decimal("70000"))


@pytest.mark.asyncio
async def test_status_report(event_bus):
    """Status should reflect current state."""
    cb = CircuitBreakerManager(event_bus)
    status = cb.get_status()

    assert status["tripped"] is False
    assert status["reason"] == ""

    await cb.trip("test")
    status = cb.get_status()
    assert status["tripped"] is True
    assert status["reason"] == "test"
