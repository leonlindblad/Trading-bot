"""Email alerting stub — placeholder for Phase 2 implementation."""

from __future__ import annotations

from loguru import logger

from src.event_bus import EventBus


class EmailAlerter:
    """Email alerts (Phase 2). Currently logs instead of sending."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    async def start(self) -> None:
        logger.info("Email alerter stub initialized (not configured)")

    async def send(self, subject: str, body: str) -> None:
        logger.info(f"[Email stub] {subject}: {body}")
