"""Market data service - fetches prices, news, and computes indicators."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import feedparser
import numpy as np
import pandas as pd
import requests
import yfinance as yf

from src.models.schemas import AssetType, MarketData, NewsItem

logger = logging.getLogger(__name__)

# Major RSS feeds for financial news
NEWS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
    "https://www.investing.com/rss/news.rss",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://feeds.reuters.com/reuters/businessNews",
]

# Crypto-specific feeds
CRYPTO_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://coindesk.com/arc/outboundfeeds/rss/",
]


class MarketDataService:
    """Fetches and processes market data from multiple sources."""

    def __init__(self, news_api_key: Optional[str] = None):
        self.news_api_key = news_api_key

    def get_stock_data(self, symbol: str, period: str = "1mo") -> Optional[MarketData]:
        """Fetch stock data with technical indicators."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            if hist.empty:
                logger.warning(f"No data for {symbol}")
                return None

            info = ticker.info
            current = hist.iloc[-1]

            market_data = MarketData(
                symbol=symbol,
                asset_type=AssetType.STOCK,
                current_price=current["Close"],
                open_price=current["Open"],
                high_24h=current["High"],
                low_24h=current["Low"],
                volume=current["Volume"],
                change_pct=((current["Close"] - hist.iloc[-2]["Close"]) / hist.iloc[-2]["Close"] * 100)
                if len(hist) > 1 else 0.0,
            )

            self._add_technical_indicators(market_data, hist)
            return market_data

        except Exception as e:
            logger.error(f"Error fetching stock data for {symbol}: {e}")
            return None

    def get_crypto_data(self, symbol: str, period: str = "1mo") -> Optional[MarketData]:
        """Fetch crypto data. Symbol format: BTC-USD, ETH-USD, etc."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            if hist.empty:
                return None

            current = hist.iloc[-1]

            market_data = MarketData(
                symbol=symbol,
                asset_type=AssetType.CRYPTO,
                current_price=current["Close"],
                open_price=current["Open"],
                high_24h=current["High"],
                low_24h=current["Low"],
                volume=current["Volume"],
                change_pct=((current["Close"] - hist.iloc[-2]["Close"]) / hist.iloc[-2]["Close"] * 100)
                if len(hist) > 1 else 0.0,
            )

            self._add_technical_indicators(market_data, hist)
            return market_data

        except Exception as e:
            logger.error(f"Error fetching crypto data for {symbol}: {e}")
            return None

    def _add_technical_indicators(self, market_data: MarketData, hist: pd.DataFrame) -> None:
        """Compute and attach technical indicators to market data."""
        close = hist["Close"]

        # Simple Moving Averages
        if len(close) >= 20:
            market_data.sma_20 = close.rolling(window=20).mean().iloc[-1]
        if len(close) >= 50:
            market_data.sma_50 = close.rolling(window=50).mean().iloc[-1]

        # RSI (14-period)
        if len(close) >= 15:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            market_data.rsi = rsi.iloc[-1]

        # MACD
        if len(close) >= 26:
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9).mean()
            market_data.macd = macd.iloc[-1]
            market_data.macd_signal = signal.iloc[-1]

        # Bollinger Bands
        if len(close) >= 20:
            sma20 = close.rolling(window=20).mean()
            std20 = close.rolling(window=20).std()
            market_data.bollinger_upper = (sma20 + 2 * std20).iloc[-1]
            market_data.bollinger_lower = (sma20 - 2 * std20).iloc[-1]

    def get_news(self, symbols: list[str] = None) -> list[NewsItem]:
        """Fetch financial news from RSS feeds and NewsAPI."""
        news_items = []

        # RSS feeds
        feeds = NEWS_FEEDS + CRYPTO_FEEDS
        for feed_url in feeds:
            try:
                if "{symbol}" in feed_url and symbols:
                    for sym in symbols[:5]:  # limit to avoid rate limits
                        url = feed_url.format(symbol=sym)
                        news_items.extend(self._parse_feed(url, [sym]))
                elif "{symbol}" not in feed_url:
                    news_items.extend(self._parse_feed(feed_url))
            except Exception as e:
                logger.debug(f"Feed error for {feed_url}: {e}")

        # NewsAPI (if key provided)
        if self.news_api_key and symbols:
            news_items.extend(self._fetch_newsapi(symbols))

        # Deduplicate by title
        seen = set()
        unique = []
        for item in news_items:
            if item.title not in seen:
                seen.add(item.title)
                unique.append(item)

        # Sort by recency, limit to most recent
        unique.sort(key=lambda x: x.published, reverse=True)
        return unique[:50]

    def _parse_feed(self, url: str, symbols: list[str] = None) -> list[NewsItem]:
        """Parse an RSS feed into NewsItem objects."""
        items = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                published = datetime.now()
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])

                items.append(NewsItem(
                    title=entry.get("title", ""),
                    summary=entry.get("summary", entry.get("description", ""))[:500],
                    source=feed.feed.get("title", url),
                    url=entry.get("link", ""),
                    published=published,
                    symbols=symbols or [],
                ))
        except Exception as e:
            logger.debug(f"Error parsing feed {url}: {e}")
        return items

    def _fetch_newsapi(self, symbols: list[str]) -> list[NewsItem]:
        """Fetch news from NewsAPI.org."""
        items = []
        try:
            query = " OR ".join(symbols[:5])
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "sortBy": "publishedAt",
                    "pageSize": 20,
                    "apiKey": self.news_api_key,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                for article in resp.json().get("articles", []):
                    items.append(NewsItem(
                        title=article.get("title", ""),
                        summary=article.get("description", "")[:500],
                        source=article.get("source", {}).get("name", "NewsAPI"),
                        url=article.get("url", ""),
                        published=datetime.fromisoformat(
                            article["publishedAt"].replace("Z", "+00:00")
                        ) if article.get("publishedAt") else datetime.now(),
                        symbols=symbols,
                    ))
        except Exception as e:
            logger.debug(f"NewsAPI error: {e}")
        return items

    def get_market_overview(self) -> dict:
        """Get broad market indicators (S&P 500, VIX, DXY, BTC, etc.)."""
        overview = {}
        benchmarks = {
            "^GSPC": "S&P 500",
            "^VIX": "VIX (Fear Index)",
            "^DJI": "Dow Jones",
            "^IXIC": "NASDAQ",
            "BTC-USD": "Bitcoin",
            "ETH-USD": "Ethereum",
            "GC=F": "Gold",
            "CL=F": "Oil (WTI)",
            "^TNX": "10Y Treasury Yield",
            "DX-Y.NYB": "US Dollar Index",
        }
        for symbol, name in benchmarks.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                if not hist.empty:
                    current = hist.iloc[-1]["Close"]
                    prev = hist.iloc[-2]["Close"] if len(hist) > 1 else current
                    change_pct = (current - prev) / prev * 100
                    overview[name] = {
                        "price": round(current, 2),
                        "change_pct": round(change_pct, 2),
                    }
            except Exception:
                pass
        return overview

    def format_for_analysis(self, market_data: MarketData) -> str:
        """Format market data into a string for Claude analysis."""
        lines = [
            f"=== {market_data.symbol} ({market_data.asset_type.value}) ===",
            f"Price: ${market_data.current_price:.2f}",
            f"Open: ${market_data.open_price:.2f}",
            f"High: ${market_data.high_24h:.2f} | Low: ${market_data.low_24h:.2f}",
            f"Volume: {market_data.volume:,.0f}",
            f"Change: {market_data.change_pct:+.2f}%",
        ]
        if market_data.sma_20:
            lines.append(f"SMA20: ${market_data.sma_20:.2f} | SMA50: ${market_data.sma_50:.2f}" if market_data.sma_50 else f"SMA20: ${market_data.sma_20:.2f}")
        if market_data.rsi:
            lines.append(f"RSI(14): {market_data.rsi:.1f}")
        if market_data.macd is not None:
            lines.append(f"MACD: {market_data.macd:.4f} | Signal: {market_data.macd_signal:.4f}")
        if market_data.bollinger_upper:
            lines.append(f"Bollinger: [{market_data.bollinger_lower:.2f} - {market_data.bollinger_upper:.2f}]")
        return "\n".join(lines)
