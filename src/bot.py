import logging
import time

from config.settings import TRADING_PAIR, TIMEFRAME, DRY_RUN
from src.exchange import create_exchange, fetch_ohlcv
from src.strategy import ohlcv_to_dataframe, apply_indicators, generate_signal

logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(self):
        self.exchange = create_exchange()
        self.symbol = TRADING_PAIR
        self.timeframe = TIMEFRAME

    def analyze(self):
        """Fetch market data and generate a trading signal."""
        ohlcv = fetch_ohlcv(self.exchange, self.symbol, self.timeframe)
        df = ohlcv_to_dataframe(ohlcv)
        df = apply_indicators(df)
        signal = generate_signal(df)
        return signal, df

    def execute(self, signal):
        """Execute a trade based on the signal (placeholder for live trading)."""
        if signal == "hold":
            logger.info("Signal: HOLD — no action taken")
            return

        if DRY_RUN:
            logger.info("[DRY RUN] Would execute %s on %s", signal.upper(), self.symbol)
            return

        # Placeholder: implement actual order placement here
        logger.info("Executing %s on %s", signal.upper(), self.symbol)

    def run_once(self):
        """Run a single analysis-and-execute cycle."""
        logger.info("Analyzing %s on %s timeframe...", self.symbol, self.timeframe)
        signal, df = self.analyze()
        logger.info("Latest close: %s | Signal: %s", df.iloc[-1]["close"], signal)
        self.execute(signal)
        return signal

    def run(self, interval_seconds=60):
        """Run the bot in a loop."""
        logger.info("Starting trading bot for %s", self.symbol)
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Error during bot cycle")
            time.sleep(interval_seconds)
