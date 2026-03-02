import pandas as pd
from src.strategy import ohlcv_to_dataframe, apply_indicators, generate_signal


def _make_ohlcv(closes):
    """Helper to create OHLCV data from a list of close prices."""
    return [
        [1000 * i, c, c + 1, c - 1, c, 100]
        for i, c in enumerate(closes)
    ]


def test_ohlcv_to_dataframe():
    raw = _make_ohlcv([100, 101, 102])
    df = ohlcv_to_dataframe(raw)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 3


def test_apply_indicators_adds_columns():
    raw = _make_ohlcv([float(i) for i in range(50)])
    df = ohlcv_to_dataframe(raw)
    df = apply_indicators(df)
    assert "sma_short" in df.columns
    assert "sma_long" in df.columns
    assert "rsi" in df.columns


def test_generate_signal_returns_valid():
    raw = _make_ohlcv([float(i) for i in range(50)])
    df = ohlcv_to_dataframe(raw)
    df = apply_indicators(df)
    signal = generate_signal(df)
    assert signal in ("buy", "sell", "hold")


def test_generate_signal_hold_on_insufficient_data():
    raw = _make_ohlcv([100])
    df = ohlcv_to_dataframe(raw)
    df = apply_indicators(df)
    signal = generate_signal(df)
    assert signal == "hold"
