"""Redis cache helpers for price data and session state."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from loguru import logger


class RedisCache:
    """Redis-backed cache for real-time price data and state."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url = redis_url
        self._redis = None

    async def connect(self):
        """Connect to Redis."""
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True
            )
            await self._redis.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Running without cache.")
            self._redis = None

    async def disconnect(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    @property
    def is_connected(self) -> bool:
        return self._redis is not None

    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        if not self._redis:
            return None
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None):
        """Set a value with optional TTL in seconds."""
        if not self._redis:
            return
        if ttl:
            await self._redis.setex(key, ttl, value)
        else:
            await self._redis.set(key, value)

    async def set_price(self, symbol: str, price: Decimal):
        """Cache a price with 60-second TTL."""
        await self.set(f"price:{symbol}", str(price), ttl=60)

    async def get_price(self, symbol: str) -> Decimal | None:
        """Get cached price for a symbol."""
        val = await self.get(f"price:{symbol}")
        return Decimal(val) if val else None

    async def set_json(self, key: str, data: Any, ttl: int | None = None):
        """Store JSON-serializable data."""
        await self.set(key, json.dumps(data, default=str), ttl=ttl)

    async def get_json(self, key: str) -> Any | None:
        """Retrieve JSON data."""
        val = await self.get(key)
        return json.loads(val) if val else None
