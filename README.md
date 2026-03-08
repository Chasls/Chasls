# Chasls AI Trading Bot

An AI-powered trading bot that uses **Claude Opus** to analyze market data, news, and technical indicators to make intelligent stock and cryptocurrency trading decisions.

## Features

- **AI-Driven Analysis**: Claude Opus analyzes technical indicators, news sentiment, macro conditions, and market psychology
- **Stocks + Crypto**: Trades both equities (via Alpaca) and cryptocurrencies (via CCXT - Coinbase, Binance, etc.)
- **Risk Management**: Built-in stop losses, take profits, position sizing, drawdown limits, and daily trade caps
- **Technical Indicators**: RSI, MACD, Bollinger Bands, SMA 20/50, volume analysis
- **News & Sentiment**: Pulls from Yahoo Finance, Reuters, MarketWatch, CoinTelegraph, and NewsAPI
- **Market Awareness**: Monitors S&P 500, VIX, Treasury yields, DXY, Gold, Oil for macro context
- **Paper Trading**: Test strategies with simulated money before going live
- **Continuous Mode**: Run on a loop with configurable intervals (default: 15 min)
- **Trade Logging**: Full audit trail of all decisions in JSON format

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/Chasls/Chasls.git
cd Chasls
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY (required)

# 3. Run in paper trading mode (default - no real money)
python main.py

# 4. Run continuously
python main.py --loop

# 5. Check portfolio status
python main.py --status
```

## Configuration

Copy `.env.example` to `.env` and set your API keys:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for AI analysis |
| `ALPACA_API_KEY` | For stocks | Alpaca brokerage API key |
| `ALPACA_SECRET_KEY` | For stocks | Alpaca secret key |
| `CRYPTO_API_KEY` | For crypto | Exchange API key (via CCXT) |
| `NEWS_API_KEY` | No | NewsAPI.org key for extra news |
| `TRADING_MODE` | No | `paper` (default) or `live` |

## How It Works

1. **Data Collection**: Fetches price data, technical indicators, and news for watchlist assets
2. **Market Overview**: Checks broad market conditions (indices, VIX, yields, commodities)
3. **AI Analysis**: Sends all data to Claude Opus, which returns trade recommendations with:
   - Signal (strong_buy / buy / hold / sell / strong_sell)
   - Confidence score (0-1)
   - Target price, stop loss, take profit levels
   - Position sizing recommendation
   - Catalysts and risks
4. **Risk Check**: Every recommendation passes through the risk manager
5. **Execution**: Approved trades are executed (paper or live)
6. **Monitoring**: Stop losses and take profits are checked each cycle

## Architecture

```
main.py                     # CLI entry point
src/
  bot.py                    # Main orchestrator
  config.py                 # Config loader
  models/schemas.py         # Data models
  services/
    ai_analyst.py           # Claude AI integration
    market_data.py          # Price/news data fetching
    trade_executor.py       # Order execution (paper/stock/crypto)
  strategies/
    risk_manager.py         # Risk rules and position sizing
```

## CLI Usage

```bash
python main.py                    # Single analysis cycle
python main.py --loop             # Continuous mode
python main.py --loop --interval 5  # Every 5 minutes
python main.py --status           # Portfolio view
python main.py --mode paper       # Force paper mode
python main.py --mode live        # Force live mode (requires confirmation)
python main.py -v                 # Verbose logging
```

## Risk Management

The bot enforces these safety limits (all configurable in `.env`):

- **Max Position**: 10% of portfolio per asset
- **Stop Loss**: 5% per position
- **Take Profit**: 15% per position
- **Max Risk Per Trade**: 2% of portfolio
- **Drawdown Halt**: Trading stops at 10% drawdown
- **Daily Trade Limit**: 20 trades/day
- **Live Trading**: Requires typing "I UNDERSTAND THE RISKS"

## Important Disclaimers

- **Start with paper trading** to validate the strategy with your watchlist
- **This is not financial advice** - the bot makes AI-driven decisions that can lose money
- **Monitor closely** when running in live mode
- Past performance does not guarantee future results
- You are responsible for all trading decisions and outcomes

---
Built by @Chasls | Powered by Claude Opus
