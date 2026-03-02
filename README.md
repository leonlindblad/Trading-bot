# Trading Bot

Automated cryptocurrency trading bot built with Python and [ccxt](https://github.com/ccxt/ccxt). Uses technical analysis indicators (SMA crossover, RSI) to generate buy/sell signals.

## Project Structure

```
Trading-bot/
├── main.py              # Entry point
├── config/
│   └── settings.py      # Configuration loaded from environment
├── src/
│   ├── bot.py           # Main trading bot loop
│   ├── exchange.py      # Exchange connection and data fetching
│   └── strategy.py      # Technical analysis and signal generation
├── tests/
│   └── test_strategy.py # Unit tests for the strategy module
├── data/                # Market data (gitignored)
├── logs/                # Log files (gitignored)
├── .env.example         # Environment variable template
└── requirements.txt     # Python dependencies
```

## Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/leonlindblad/Trading-bot.git
   cd Trading-bot
   ```

2. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your exchange API credentials and trading parameters.

4. **Run the bot**

   ```bash
   python main.py
   ```

   By default `DRY_RUN=true`, so no real trades will be placed.

## Running Tests

```bash
pytest
```

## Configuration

| Variable       | Default      | Description                          |
| -------------- | ------------ | ------------------------------------ |
| `EXCHANGE_NAME`| `binance`    | Exchange to connect to (ccxt name)   |
| `API_KEY`      | —            | Your exchange API key                |
| `API_SECRET`   | —            | Your exchange API secret             |
| `TRADING_PAIR` | `BTC/USDT`   | Trading pair symbol                  |
| `TIMEFRAME`    | `1h`         | Candlestick timeframe                |
| `DRY_RUN`      | `true`       | If true, no real orders are placed   |
| `LOG_LEVEL`    | `INFO`       | Logging level                        |
