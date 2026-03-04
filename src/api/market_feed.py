"""Live market feed — fetches real-time prices for major cryptos and stocks."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from loguru import logger


class MarketFeedCache:
    """Simple in-memory cache with TTL for market data."""

    def __init__(self, ttl_seconds: int = 60):
        self._ttl = ttl_seconds
        self._data: dict[str, Any] = {}
        self._timestamps: dict[str, float] = {}

    def get(self, key: str) -> Any | None:
        ts = self._timestamps.get(key)
        if ts and (time.time() - ts) < self._ttl:
            return self._data.get(key)
        return None

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._timestamps[key] = time.time()


_cache = MarketFeedCache(ttl_seconds=30)

# Major crypto IDs for CoinGecko
CRYPTO_IDS = [
    "bitcoin", "ethereum", "binancecoin", "solana", "cardano",
    "ripple", "polkadot", "dogecoin", "avalanche-2", "chainlink",
    "tron", "polygon", "litecoin", "uniswap", "stellar",
]

# Major US stock symbols
US_STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "BRK-B", "JPM", "V", "UNH", "MA", "HD", "PG", "JNJ",
]

# Major UK stock symbols (LSE)
UK_STOCKS = [
    "SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L",
    "GSK.L", "RIO.L", "LSEG.L", "REL.L", "DGE.L",
    "BATS.L", "GLEN.L", "VOD.L", "AHT.L", "NG.L",
]


async def _fetch_crypto_prices() -> list[dict]:
    """Fetch crypto prices from CoinGecko free API."""
    cached = _cache.get("crypto")
    if cached is not None:
        return cached

    try:
        ids = ",".join(CRYPTO_IDS)
        url = (
            f"https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency=usd&ids={ids}"
            f"&order=market_cap_desc&per_page=50&page=1"
            f"&sparkline=false&price_change_percentage=24h"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for coin in data:
            results.append({
                "symbol": coin.get("symbol", "").upper(),
                "name": coin.get("name", ""),
                "price": coin.get("current_price"),
                "change_24h": coin.get("price_change_percentage_24h"),
                "market_cap": coin.get("market_cap"),
                "volume_24h": coin.get("total_volume"),
                "high_24h": coin.get("high_24h"),
                "low_24h": coin.get("low_24h"),
                "image": coin.get("image"),
            })
        _cache.set("crypto", results)
        return results
    except Exception as e:
        logger.warning(f"CoinGecko fetch failed: {e}")
        return _cache.get("crypto") or []


async def _fetch_stock_prices(symbols: list[str], market_label: str) -> list[dict]:
    """Fetch stock prices from Yahoo Finance v8 API."""
    cache_key = f"stocks_{market_label}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        symbols_str = ",".join(symbols)
        url = (
            f"https://query1.finance.yahoo.com/v7/finance/quote"
            f"?symbols={symbols_str}"
            f"&fields=symbol,shortName,regularMarketPrice,"
            f"regularMarketChangePercent,regularMarketVolume,"
            f"regularMarketDayHigh,regularMarketDayLow,"
            f"marketCap,regularMarketPreviousClose"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        quotes = data.get("quoteResponse", {}).get("result", [])
        results = []
        for q in quotes:
            results.append({
                "symbol": q.get("symbol", ""),
                "name": q.get("shortName", q.get("longName", "")),
                "price": q.get("regularMarketPrice"),
                "change_24h": q.get("regularMarketChangePercent"),
                "market_cap": q.get("marketCap"),
                "volume_24h": q.get("regularMarketVolume"),
                "high_24h": q.get("regularMarketDayHigh"),
                "low_24h": q.get("regularMarketDayLow"),
                "prev_close": q.get("regularMarketPreviousClose"),
            })
        _cache.set(cache_key, results)
        return results
    except Exception as e:
        logger.warning(f"Yahoo Finance fetch failed for {market_label}: {e}")
        return _cache.get(cache_key) or []


async def get_market_feed() -> dict:
    """Fetch all market data concurrently."""
    crypto, us_stocks, uk_stocks = await asyncio.gather(
        _fetch_crypto_prices(),
        _fetch_stock_prices(US_STOCKS, "us"),
        _fetch_stock_prices(UK_STOCKS, "uk"),
        return_exceptions=True,
    )

    # Handle any exceptions from gather
    if isinstance(crypto, Exception):
        logger.error(f"Crypto feed error: {crypto}")
        crypto = []
    if isinstance(us_stocks, Exception):
        logger.error(f"US stocks feed error: {us_stocks}")
        us_stocks = []
    if isinstance(uk_stocks, Exception):
        logger.error(f"UK stocks feed error: {uk_stocks}")
        uk_stocks = []

    return {
        "crypto": crypto,
        "us_stocks": us_stocks,
        "uk_stocks": uk_stocks,
        "timestamp": time.time(),
    }
