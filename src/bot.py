"""Main trading bot orchestrator - ties everything together."""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from src.models.schemas import (
    AnalysisResult,
    AssetType,
    Portfolio,
    Signal,
    Trade,
    TradeAction,
)
from src.services.ai_analyst import AIAnalyst
from src.services.market_data import MarketDataService
from src.services.trade_executor import CryptoExecutor, PaperExecutor, StockExecutor
from src.strategies.risk_manager import RiskConfig, RiskManager

logger = logging.getLogger(__name__)


class TradingBot:
    """AI-powered trading bot that uses Claude to analyze and trade markets."""

    def __init__(self, config: dict):
        self.config = config
        self.trading_mode = config.get("trading_mode", "paper")

        # Initialize services
        self.market_data = MarketDataService(
            news_api_key=config.get("news_api_key"),
        )
        self.analyst = AIAnalyst(
            api_key=config["anthropic_api_key"],
            model=config.get("claude_model", "claude-opus-4-20250918"),
        )
        self.risk_manager = RiskManager(RiskConfig(
            max_position_pct=float(config.get("max_position_pct", 0.10)),
            max_daily_trades=int(config.get("max_daily_trades", 20)),
            stop_loss_pct=float(config.get("stop_loss_pct", 0.05)),
            take_profit_pct=float(config.get("take_profit_pct", 0.15)),
            max_portfolio_risk=float(config.get("max_portfolio_risk", 0.02)),
            max_drawdown_pct=float(config.get("max_drawdown_pct", 0.10)),
        ))

        # Initialize executors based on mode
        if self.trading_mode == "paper":
            self.stock_executor = PaperExecutor(
                starting_cash=float(config.get("starting_cash", 100_000))
            )
            self.crypto_executor = self.stock_executor  # Share paper executor
            logger.info("Running in PAPER TRADING mode (no real money)")
        else:
            if config.get("alpaca_api_key"):
                self.stock_executor = StockExecutor(
                    api_key=config["alpaca_api_key"],
                    secret_key=config["alpaca_secret_key"],
                    base_url=config.get("alpaca_base_url", "https://paper-api.alpaca.markets"),
                )
            else:
                self.stock_executor = None

            if config.get("crypto_api_key"):
                self.crypto_executor = CryptoExecutor(
                    exchange_id=config.get("crypto_exchange", "coinbasepro"),
                    api_key=config["crypto_api_key"],
                    secret=config["crypto_secret"],
                    password=config.get("crypto_password"),
                )
            else:
                self.crypto_executor = None

        # Watchlists
        self.stock_watchlist = config.get("stock_watchlist", [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            "JPM", "V", "JNJ", "SPY", "QQQ",
        ])
        self.crypto_watchlist = config.get("crypto_watchlist", [
            "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD",
        ])

        # Trade log
        self.trade_log: list[dict] = []
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

    def run_cycle(self) -> dict:
        """Run one full analysis and trading cycle."""
        cycle_start = datetime.now()
        logger.info(f"=== Trading cycle started at {cycle_start} ===")

        results = {
            "timestamp": cycle_start.isoformat(),
            "market_data_count": 0,
            "news_count": 0,
            "recommendations": 0,
            "trades_executed": 0,
            "trades": [],
            "portfolio": None,
        }

        try:
            # Step 1: Fetch market overview
            logger.info("Fetching market overview...")
            market_overview = self.market_data.get_market_overview()

            # Step 2: Fetch data for watchlist
            logger.info("Fetching stock data...")
            all_market_data = []
            for symbol in self.stock_watchlist:
                data = self.market_data.get_stock_data(symbol)
                if data:
                    all_market_data.append(data)

            logger.info("Fetching crypto data...")
            for symbol in self.crypto_watchlist:
                data = self.market_data.get_crypto_data(symbol)
                if data:
                    all_market_data.append(data)

            results["market_data_count"] = len(all_market_data)

            # Step 3: Fetch news
            logger.info("Fetching news...")
            all_symbols = self.stock_watchlist + self.crypto_watchlist
            news = self.market_data.get_news(all_symbols)
            results["news_count"] = len(news)

            # Step 4: Get current portfolio
            portfolio = self._get_portfolio()
            if isinstance(self.stock_executor, PaperExecutor):
                # Update paper positions with latest prices
                prices = {md.symbol: md.current_price for md in all_market_data}
                self.stock_executor.update_prices(prices)
                portfolio = self.stock_executor.get_portfolio()

            # Step 5: Check stop losses / take profits
            triggers = self.risk_manager.check_stop_loss(portfolio)
            for trigger in triggers:
                logger.warning(f"Risk trigger: {trigger['reason']}")
                self._execute_risk_trigger(trigger, portfolio)

            # Step 6: Run AI analysis
            logger.info(f"Sending {len(all_market_data)} assets to Claude for analysis...")
            recommendations = self.analyst.analyze_markets(
                market_data=all_market_data,
                news=news,
                portfolio=portfolio,
                market_overview=market_overview,
            )
            results["recommendations"] = len(recommendations)

            # Step 7: Execute approved trades
            for rec in recommendations:
                trade = self._process_recommendation(rec, portfolio)
                if trade:
                    results["trades"].append({
                        "symbol": trade.symbol,
                        "action": trade.action.value,
                        "quantity": trade.quantity,
                        "price": trade.price,
                        "status": trade.status,
                        "reasoning": trade.reasoning,
                    })
                    results["trades_executed"] += 1

            # Step 8: Get updated portfolio
            portfolio = self._get_portfolio()
            if isinstance(self.stock_executor, PaperExecutor):
                portfolio = self.stock_executor.get_portfolio()

            results["portfolio"] = {
                "cash": portfolio.cash,
                "total_value": portfolio.total_value,
                "positions": len(portfolio.positions),
                "total_pnl": portfolio.total_pnl,
                "max_drawdown": portfolio.max_drawdown,
            }

            # Save cycle results
            self._save_log(results)

            duration = (datetime.now() - cycle_start).total_seconds()
            logger.info(
                f"=== Cycle complete in {duration:.1f}s: "
                f"{results['trades_executed']} trades executed ==="
            )

        except Exception as e:
            logger.error(f"Cycle error: {e}", exc_info=True)
            results["error"] = str(e)

        return results

    def _process_recommendation(self, rec: AnalysisResult, portfolio: Portfolio) -> Trade | None:
        """Process a single AI recommendation through risk checks and execution."""
        # Risk evaluation
        risk_check = self.risk_manager.evaluate(rec, portfolio)
        if not risk_check["approved"]:
            logger.info(
                f"Trade REJECTED for {rec.symbol}: {', '.join(risk_check['reasons'])}"
            )
            return None

        # Determine action and quantity
        if rec.signal in (Signal.STRONG_BUY, Signal.BUY):
            action = TradeAction.BUY
            # Calculate shares from dollar value
            price = self._get_latest_price(rec.symbol)
            if not price or price <= 0:
                return None
            dollar_value = risk_check["adjusted_quantity"]
            quantity = dollar_value / price
            # Round stocks to whole shares, crypto to 6 decimals
            asset_type = self._get_asset_type(rec.symbol)
            if asset_type == AssetType.STOCK:
                quantity = int(quantity)
            else:
                quantity = round(quantity, 6)
            if quantity <= 0:
                return None

        elif rec.signal in (Signal.STRONG_SELL, Signal.SELL):
            action = TradeAction.SELL
            # Find position to sell
            position = None
            for pos in portfolio.positions:
                if pos.symbol == rec.symbol:
                    position = pos
                    break
            if not position:
                logger.info(f"No position in {rec.symbol} to sell")
                return None
            quantity = position.quantity
            price = position.current_price
            asset_type = position.asset_type
        else:
            return None

        # Create and execute trade
        price = price or self._get_latest_price(rec.symbol)
        trade = Trade(
            symbol=rec.symbol,
            asset_type=self._get_asset_type(rec.symbol),
            action=action,
            quantity=quantity,
            price=price,
            total_value=quantity * price,
            reasoning=rec.reasoning,
        )

        # Execute
        executor = self._get_executor(trade.asset_type)
        if executor:
            trade = executor.execute(trade)
        else:
            trade.status = "failed: no executor configured"
            logger.error(f"No executor for {trade.asset_type.value}")

        return trade

    def _execute_risk_trigger(self, trigger: dict, portfolio: Portfolio) -> None:
        """Execute a stop loss or take profit order."""
        for pos in portfolio.positions:
            if pos.symbol == trigger["symbol"]:
                trade = Trade(
                    symbol=pos.symbol,
                    asset_type=pos.asset_type,
                    action=TradeAction.SELL,
                    quantity=pos.quantity,
                    price=pos.current_price,
                    total_value=pos.quantity * pos.current_price,
                    reasoning=trigger["reason"],
                )
                executor = self._get_executor(pos.asset_type)
                if executor:
                    executor.execute(trade)
                break

    def _get_portfolio(self) -> Portfolio:
        """Get combined portfolio from all executors."""
        if isinstance(self.stock_executor, PaperExecutor):
            return self.stock_executor.get_portfolio()
        # In live mode, combine stock and crypto portfolios
        portfolio = Portfolio(cash=0, total_value=0)
        if self.stock_executor and hasattr(self.stock_executor, "get_portfolio"):
            stock_portfolio = self.stock_executor.get_portfolio()
            portfolio.cash += stock_portfolio.cash
            portfolio.total_value += stock_portfolio.total_value
            portfolio.positions.extend(stock_portfolio.positions)
        return portfolio

    def _get_executor(self, asset_type: AssetType):
        if asset_type == AssetType.CRYPTO:
            return self.crypto_executor
        return self.stock_executor

    def _get_asset_type(self, symbol: str) -> AssetType:
        if symbol in self.crypto_watchlist or symbol.endswith("-USD"):
            return AssetType.CRYPTO
        return AssetType.STOCK

    def _get_latest_price(self, symbol: str) -> float | None:
        """Quick price lookup."""
        asset_type = self._get_asset_type(symbol)
        if asset_type == AssetType.CRYPTO:
            data = self.market_data.get_crypto_data(symbol, period="1d")
        else:
            data = self.market_data.get_stock_data(symbol, period="1d")
        return data.current_price if data else None

    def _save_log(self, results: dict) -> None:
        """Save cycle results to log file."""
        log_file = self.log_dir / f"trades_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(results, default=str) + "\n")
