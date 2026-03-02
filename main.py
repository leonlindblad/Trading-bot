import logging
from config.settings import LOG_LEVEL
from src.bot import TradingBot


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/bot.log"),
        ],
    )


def main():
    setup_logging()
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()
