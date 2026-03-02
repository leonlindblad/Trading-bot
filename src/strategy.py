import pandas as pd
import ta
import logging

logger = logging.getLogger(__name__)


def ohlcv_to_dataframe(ohlcv_data):
    """Convert raw OHLCV data to a pandas DataFrame."""
    df = pd.DataFrame(
        ohlcv_data,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def apply_indicators(df):
    """Apply technical indicators to the OHLCV DataFrame."""
    df["sma_short"] = ta.trend.sma_indicator(df["close"], window=10)
    df["sma_long"] = ta.trend.sma_indicator(df["close"], window=30)
    df["rsi"] = ta.momentum.rsi(df["close"], window=14)
    return df


def generate_signal(df):
    """Generate a buy/sell/hold signal based on indicators.

    Returns one of: "buy", "sell", or "hold".
    """
    if len(df) < 2:
        return "hold"

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    # SMA crossover strategy
    if previous["sma_short"] <= previous["sma_long"] and latest["sma_short"] > latest["sma_long"]:
        logger.info("BUY signal: SMA crossover detected")
        return "buy"

    if previous["sma_short"] >= previous["sma_long"] and latest["sma_short"] < latest["sma_long"]:
        logger.info("SELL signal: SMA crossunder detected")
        return "sell"

    return "hold"
