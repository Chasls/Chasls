"""Trade execution service - handles stock and crypto order execution."""

import logging
from datetime import datetime
from typing import Optional

from src.models.schemas import AssetType, Portfolio, Position, Trade, TradeAction

logger = logging.getLogger(__name__)


class StockExecutor:
    """Execute stock trades via Alpaca API."""

    def __init__(self, api_key: str, secret_key: str, base_url: str):
        import alpaca_trade_api as tradeapi
        self.api = tradeapi.REST(api_key, secret_key, base_url, api_version="v2")

    def execute(self, trade: Trade) -> Trade:
        """Submit a stock order to Alpaca."""
        try:
            side = "buy" if trade.action in (TradeAction.BUY,) else "sell"
            order = self.api.submit_order(
                symbol=trade.symbol,
                qty=trade.quantity,
                side=side,
                type="market",
                time_in_force="day",
            )
            trade.order_id = order.id
            trade.status = "submitted"
            logger.info(f"Stock order submitted: {side} {trade.quantity} {trade.symbol} (order: {order.id})")
        except Exception as e:
            trade.status = f"failed: {e}"
            logger.error(f"Stock order failed: {e}")
        return trade

    def get_portfolio(self) -> Portfolio:
        """Get current portfolio state from Alpaca."""
        account = self.api.get_account()
        positions = self.api.list_positions()

        pos_list = []
        for p in positions:
            pos_list.append(Position(
                symbol=p.symbol,
                asset_type=AssetType.STOCK,
                quantity=float(p.qty),
                entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                unrealized_pnl=float(p.unrealized_pl),
                unrealized_pnl_pct=float(p.unrealized_plpc) * 100,
                opened_at=datetime.now(),
            ))

        portfolio = Portfolio(
            cash=float(account.cash),
            total_value=float(account.portfolio_value),
            positions=pos_list,
            daily_pnl=float(account.portfolio_value) - float(account.last_equity),
        )
        portfolio.peak_value = max(portfolio.total_value, portfolio.peak_value)
        if portfolio.peak_value > 0:
            portfolio.max_drawdown = (
                (portfolio.peak_value - portfolio.total_value) / portfolio.peak_value * 100
            )
        return portfolio


class CryptoExecutor:
    """Execute crypto trades via CCXT (supports many exchanges)."""

    def __init__(self, exchange_id: str, api_key: str, secret: str, password: str = None):
        import ccxt
        exchange_class = getattr(ccxt, exchange_id)
        config = {"apiKey": api_key, "secret": secret}
        if password:
            config["password"] = password
        self.exchange = exchange_class(config)
        self.exchange.load_markets()

    def execute(self, trade: Trade) -> Trade:
        """Submit a crypto order."""
        try:
            side = "buy" if trade.action == TradeAction.BUY else "sell"
            # Convert symbol format: BTC-USD -> BTC/USD
            symbol = trade.symbol.replace("-", "/")
            order = self.exchange.create_market_order(symbol, side, trade.quantity)
            trade.order_id = order.get("id", "")
            trade.status = "submitted"
            logger.info(f"Crypto order submitted: {side} {trade.quantity} {symbol} (order: {trade.order_id})")
        except Exception as e:
            trade.status = f"failed: {e}"
            logger.error(f"Crypto order failed: {e}")
        return trade

    def get_balances(self) -> dict:
        """Get exchange balances."""
        balance = self.exchange.fetch_balance()
        return {k: v for k, v in balance.get("total", {}).items() if v and v > 0}


class PaperExecutor:
    """Simulated trading for testing - no real money at risk."""

    def __init__(self, starting_cash: float = 100_000.0):
        self.cash = starting_cash
        self.positions: dict[str, Position] = {}
        self.trade_history: list[Trade] = []
        self.peak_value = starting_cash

    def execute(self, trade: Trade) -> Trade:
        """Simulate a trade."""
        if trade.action == TradeAction.BUY:
            cost = trade.quantity * trade.price
            if cost > self.cash:
                trade.status = "failed: insufficient funds"
                logger.warning(f"Paper trade failed: need ${cost:.2f} but only have ${self.cash:.2f}")
                return trade

            self.cash -= cost
            if trade.symbol in self.positions:
                pos = self.positions[trade.symbol]
                total_qty = pos.quantity + trade.quantity
                pos.entry_price = (
                    (pos.entry_price * pos.quantity + trade.price * trade.quantity) / total_qty
                )
                pos.quantity = total_qty
            else:
                self.positions[trade.symbol] = Position(
                    symbol=trade.symbol,
                    asset_type=trade.asset_type,
                    quantity=trade.quantity,
                    entry_price=trade.price,
                    current_price=trade.price,
                    unrealized_pnl=0,
                    unrealized_pnl_pct=0,
                    opened_at=datetime.now(),
                )
            trade.status = "filled"
            trade.order_id = f"paper-{len(self.trade_history)}"

        elif trade.action == TradeAction.SELL:
            if trade.symbol not in self.positions:
                trade.status = "failed: no position"
                return trade
            pos = self.positions[trade.symbol]
            if trade.quantity > pos.quantity:
                trade.status = "failed: insufficient shares"
                return trade

            self.cash += trade.quantity * trade.price
            pos.quantity -= trade.quantity
            if pos.quantity <= 0.0001:  # effectively zero
                del self.positions[trade.symbol]
            trade.status = "filled"
            trade.order_id = f"paper-{len(self.trade_history)}"

        self.trade_history.append(trade)
        logger.info(
            f"Paper trade: {trade.action.value} {trade.quantity} {trade.symbol} "
            f"@ ${trade.price:.2f} (cash: ${self.cash:,.2f})"
        )
        return trade

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update current prices for positions."""
        for symbol, price in prices.items():
            if symbol in self.positions:
                pos = self.positions[symbol]
                pos.current_price = price
                pos.unrealized_pnl = (price - pos.entry_price) * pos.quantity
                pos.unrealized_pnl_pct = (price - pos.entry_price) / pos.entry_price * 100

    def get_portfolio(self) -> Portfolio:
        """Get paper trading portfolio state."""
        positions_value = sum(
            p.current_price * p.quantity for p in self.positions.values()
        )
        total_value = self.cash + positions_value
        self.peak_value = max(self.peak_value, total_value)

        return Portfolio(
            cash=self.cash,
            total_value=total_value,
            positions=list(self.positions.values()),
            total_pnl=total_value - 100_000.0,
            peak_value=self.peak_value,
            max_drawdown=(
                (self.peak_value - total_value) / self.peak_value * 100
                if self.peak_value > 0 else 0
            ),
        )
