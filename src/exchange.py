import ccxt
import logging

from config.settings import EXCHANGE_NAME, API_KEY, API_SECRET, DRY_RUN

logger = logging.getLogger(__name__)


def create_exchange():
    """Create and return an exchange connection using ccxt."""
    exchange_class = getattr(ccxt, EXCHANGE_NAME, None)
    if exchange_class is None:
        raise ValueError(f"Exchange '{EXCHANGE_NAME}' is not supported by ccxt")

    exchange = exchange_class({
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "enableRateLimit": True,
    })

    if DRY_RUN:
        exchange.set_sandbox_mode(True)
        logger.info("Running in sandbox/dry-run mode")

    logger.info("Connected to %s", EXCHANGE_NAME)
    return exchange


def fetch_ohlcv(exchange, symbol, timeframe, limit=100):
    """Fetch OHLCV candlestick data from the exchange."""
    return exchange.fetch_ohlcv(symbol, timeframe, limit=limit)


def fetch_ticker(exchange, symbol):
    """Fetch the latest ticker for a symbol."""
    return exchange.fetch_ticker(symbol)


def fetch_balance(exchange):
    """Fetch account balance."""
    return exchange.fetch_balance()
