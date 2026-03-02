"""Circuit breakers — automated trading halts for unusual conditions."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger

from src.event_bus import Event, EventBus, EventType


class CircuitBreakerManager:
    """Monitors for dangerous conditions and halts trading when triggered.

    Circuit breakers:
    - Daily loss limit hit
    - Weekly loss limit hit
    - Consecutive API/execution failures
    - Price anomaly (>10% move in 1 minute)
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._tripped = False
        self._trip_reason = ""
        self._trip_time: datetime | None = None
        self._auto_reset = True  # Auto-reset for daily breaker

        # Tracking state
        self._execution_failures: dict[str, int] = defaultdict(int)
        self._last_prices: dict[str, tuple[Decimal, datetime]] = {}

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    @property
    def trip_reason(self) -> str:
        return self._trip_reason

    async def trip(self, reason: str, auto_reset: bool = True) -> None:
        """Activate circuit breaker, halting all trading."""
        self._tripped = True
        self._trip_reason = reason
        self._trip_time = datetime.now(timezone.utc)
        self._auto_reset = auto_reset
        logger.critical(f"CIRCUIT BREAKER TRIPPED: {reason}")

        await self.event_bus.publish(
            Event(
                event_type=EventType.CIRCUIT_BREAKER_TRIGGERED,
                data={
                    "reason": reason,
                    "auto_reset": auto_reset,
                    "timestamp": self._trip_time.isoformat(),
                },
                source="circuit_breaker",
            )
        )

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        logger.info(f"Circuit breaker reset (was: {self._trip_reason})")
        self._tripped = False
        self._trip_reason = ""
        self._trip_time = None
        self._execution_failures.clear()

    def record_execution_failure(self, connector_name: str) -> bool:
        """Record an execution failure. Returns True if breaker should trip."""
        self._execution_failures[connector_name] += 1
        count = self._execution_failures[connector_name]
        if count >= 3:
            return True
        return False

    def record_execution_success(self, connector_name: str) -> None:
        """Reset failure count on success."""
        self._execution_failures[connector_name] = 0

    def check_price_anomaly(
        self, symbol: str, price: Decimal, threshold_pct: Decimal = Decimal("10")
    ) -> bool:
        """Check for unusual price movement. Returns True if anomaly detected."""
        now = datetime.now(timezone.utc)

        if symbol in self._last_prices:
            last_price, last_time = self._last_prices[symbol]
            elapsed = (now - last_time).total_seconds()

            if elapsed <= 60 and last_price > 0:
                change_pct = abs(price - last_price) / last_price * Decimal("100")
                if change_pct > threshold_pct:
                    logger.warning(
                        f"Price anomaly: {symbol} moved {change_pct:.2f}% "
                        f"in {elapsed:.0f}s"
                    )
                    return True

        self._last_prices[symbol] = (price, now)
        return False

    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "tripped": self._tripped,
            "reason": self._trip_reason,
            "trip_time": self._trip_time.isoformat() if self._trip_time else None,
            "auto_reset": self._auto_reset,
            "execution_failures": dict(self._execution_failures),
        }
