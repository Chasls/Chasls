"""Data models for the trading bot."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AssetType(Enum):
    STOCK = "stock"
    CRYPTO = "crypto"


class TradeAction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    SHORT = "short"
    COVER = "cover"


class Signal(Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class MarketData:
    symbol: str
    asset_type: AssetType
    current_price: float
    open_price: float
    high_24h: float
    low_24h: float
    volume: float
    change_pct: float
    timestamp: datetime = field(default_factory=datetime.now)
    # Technical indicators
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None


@dataclass
class NewsItem:
    title: str
    summary: str
    source: str
    url: str
    published: datetime
    symbols: list[str] = field(default_factory=list)
    sentiment: Optional[str] = None


@dataclass
class AnalysisResult:
    symbol: str
    signal: Signal
    confidence: float  # 0.0 - 1.0
    reasoning: str
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_pct: float = 0.05  # % of portfolio
    catalysts: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    symbol: str
    asset_type: AssetType
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    opened_at: datetime


@dataclass
class Trade:
    symbol: str
    asset_type: AssetType
    action: TradeAction
    quantity: float
    price: float
    total_value: float
    reasoning: str
    timestamp: datetime = field(default_factory=datetime.now)
    order_id: Optional[str] = None
    status: str = "pending"


@dataclass
class Portfolio:
    cash: float
    total_value: float
    positions: list[Position] = field(default_factory=list)
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    daily_trades: int = 0
    max_drawdown: float = 0.0
    peak_value: float = 0.0
