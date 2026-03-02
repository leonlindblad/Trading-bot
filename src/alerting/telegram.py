"""Telegram alerting — sends trade notifications and risk alerts."""

from __future__ import annotations

from loguru import logger

from src.event_bus import Event, EventBus, EventType


class TelegramAlerter:
    """Sends alerts via Telegram bot. Logs if not configured."""

    def __init__(self, bot_token: str, chat_id: str, event_bus: EventBus):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self.event_bus = event_bus
        self._configured = bool(bot_token and chat_id)

    async def start(self) -> None:
        """Subscribe to alertable events."""
        await self.event_bus.subscribe(EventType.ORDER_FILLED, self._on_fill)
        await self.event_bus.subscribe(EventType.RISK_BREACH, self._on_risk)
        await self.event_bus.subscribe(
            EventType.CIRCUIT_BREAKER_TRIGGERED, self._on_circuit_breaker
        )

    async def _send_message(self, text: str) -> None:
        """Send message via Telegram or log if not configured."""
        if not self._configured:
            logger.info(f"[Telegram stub] {text}")
            return

        try:
            import httpx

            url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            async with httpx.AsyncClient() as client:
                await client.post(
                    url,
                    json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
                )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    async def _on_fill(self, event: Event) -> None:
        d = event.data
        text = (
            f"<b>Trade Executed</b>\n"
            f"{d.get('side')} {d.get('quantity')} {d.get('symbol')}\n"
            f"Price: {d.get('price')} | Fees: {d.get('fees')}\n"
            f"Strategy: {d.get('strategy')}"
        )
        await self._send_message(text)

    async def _on_risk(self, event: Event) -> None:
        text = f"<b>⚠ Risk Alert</b>\n{event.data.get('reason', 'Unknown')}"
        await self._send_message(text)

    async def _on_circuit_breaker(self, event: Event) -> None:
        text = (
            f"<b>🚨 CIRCUIT BREAKER</b>\n"
            f"Trading halted: {event.data.get('reason', 'Unknown')}"
        )
        await self._send_message(text)
