"""Configuration loader - reads from .env and provides defaults."""

import os
from pathlib import Path

from dotenv import load_dotenv


def load_config() -> dict:
    """Load configuration from .env file and environment variables."""
    # Load .env file if it exists
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    return {
        # Claude AI
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "claude_model": os.getenv("CLAUDE_MODEL", "claude-opus-4-20250918"),

        # Alpaca (stocks)
        "alpaca_api_key": os.getenv("ALPACA_API_KEY", ""),
        "alpaca_secret_key": os.getenv("ALPACA_SECRET_KEY", ""),
        "alpaca_base_url": os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),

        # Crypto exchange
        "crypto_exchange": os.getenv("CRYPTO_EXCHANGE", "coinbasepro"),
        "crypto_api_key": os.getenv("CRYPTO_API_KEY", ""),
        "crypto_secret": os.getenv("CRYPTO_SECRET", ""),
        "crypto_password": os.getenv("CRYPTO_PASSWORD", ""),

        # News
        "news_api_key": os.getenv("NEWS_API_KEY", ""),

        # Trading
        "trading_mode": os.getenv("TRADING_MODE", "paper"),
        "starting_cash": float(os.getenv("STARTING_CASH", "100000")),
        "max_position_pct": float(os.getenv("MAX_POSITION_PCT", "0.10")),
        "max_daily_trades": int(os.getenv("MAX_DAILY_TRADES", "20")),
        "stop_loss_pct": float(os.getenv("STOP_LOSS_PCT", "0.05")),
        "take_profit_pct": float(os.getenv("TAKE_PROFIT_PCT", "0.15")),
        "max_portfolio_risk": float(os.getenv("MAX_PORTFOLIO_RISK", "0.02")),
        "max_drawdown_pct": float(os.getenv("MAX_DRAWDOWN_PCT", "0.10")),
        "analysis_interval_min": int(os.getenv("ANALYSIS_INTERVAL_MIN", "15")),

        # Watchlists (comma-separated in env)
        "stock_watchlist": os.getenv(
            "STOCK_WATCHLIST",
            "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,JPM,V,JNJ,SPY,QQQ"
        ).split(","),
        "crypto_watchlist": os.getenv(
            "CRYPTO_WATCHLIST",
            "BTC-USD,ETH-USD,SOL-USD,ADA-USD"
        ).split(","),
    }
