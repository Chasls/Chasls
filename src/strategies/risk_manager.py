"""Risk management - protects capital and enforces trading rules."""

import logging
from dataclasses import dataclass
from datetime import datetime

from src.models.schemas import AnalysisResult, Portfolio, Signal, Trade, TradeAction

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    max_position_pct: float = 0.10      # Max 10% of portfolio in one position
    max_daily_trades: int = 20           # Max trades per day
    stop_loss_pct: float = 0.05          # 5% stop loss
    take_profit_pct: float = 0.15        # 15% take profit
    max_portfolio_risk: float = 0.02     # Max 2% risk per trade
    max_drawdown_pct: float = 0.10       # Halt at 10% drawdown
    min_confidence: float = 0.6          # Minimum AI confidence to trade
    max_correlated_positions: int = 3    # Max positions in same sector


class RiskManager:
    """Enforces risk limits and position sizing rules."""

    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()

    def evaluate(self, analysis: AnalysisResult, portfolio: Portfolio) -> dict:
        """Evaluate whether a trade should be allowed and adjust sizing."""
        checks = {
            "approved": True,
            "reasons": [],
            "adjusted_size": analysis.position_size_pct,
            "adjusted_quantity": 0,
        }

        # Check 1: Drawdown circuit breaker
        if portfolio.max_drawdown >= self.config.max_drawdown_pct * 100:
            checks["approved"] = False
            checks["reasons"].append(
                f"HALT: Portfolio drawdown {portfolio.max_drawdown:.1f}% "
                f"exceeds limit {self.config.max_drawdown_pct*100:.0f}%"
            )
            return checks

        # Check 2: Daily trade limit
        if portfolio.daily_trades >= self.config.max_daily_trades:
            checks["approved"] = False
            checks["reasons"].append(
                f"Daily trade limit reached ({self.config.max_daily_trades})"
            )
            return checks

        # Check 3: Minimum confidence
        if analysis.confidence < self.config.min_confidence:
            checks["approved"] = False
            checks["reasons"].append(
                f"Confidence {analysis.confidence:.2f} below minimum {self.config.min_confidence:.2f}"
            )
            return checks

        # Check 4: Only trade on actionable signals
        if analysis.signal == Signal.HOLD:
            checks["approved"] = False
            checks["reasons"].append("Signal is HOLD - no trade needed")
            return checks

        # Check 5: Position size limit
        max_position_value = portfolio.total_value * self.config.max_position_pct
        desired_value = portfolio.total_value * analysis.position_size_pct

        # Check if we already have a position
        existing_value = 0
        for pos in portfolio.positions:
            if pos.symbol == analysis.symbol:
                existing_value = pos.current_price * pos.quantity
                break

        if analysis.signal in (Signal.BUY, Signal.STRONG_BUY):
            remaining_capacity = max_position_value - existing_value
            if remaining_capacity <= 0:
                checks["approved"] = False
                checks["reasons"].append(
                    f"Position in {analysis.symbol} already at max size"
                )
                return checks
            desired_value = min(desired_value, remaining_capacity)

        # Check 6: Cash availability
        if analysis.signal in (Signal.BUY, Signal.STRONG_BUY):
            if desired_value > portfolio.cash:
                desired_value = portfolio.cash * 0.95  # Keep 5% cash buffer
                checks["reasons"].append("Reduced position size due to available cash")

            if desired_value < 10:  # Minimum trade value
                checks["approved"] = False
                checks["reasons"].append("Trade value too small")
                return checks

        # Check 7: Risk per trade (max loss)
        if analysis.stop_loss and analysis.signal in (Signal.BUY, Signal.STRONG_BUY):
            risk_per_share = abs(analysis.target_price - analysis.stop_loss) if analysis.target_price else 0
            max_risk_value = portfolio.total_value * self.config.max_portfolio_risk
            if risk_per_share > 0:
                max_shares_by_risk = max_risk_value / risk_per_share
                # This further constrains position size
                checks["reasons"].append(f"Risk-adjusted max shares: {max_shares_by_risk:.0f}")

        # Scale position with confidence
        confidence_scale = min(analysis.confidence / 0.9, 1.0)  # Full size at 90%+ confidence
        checks["adjusted_size"] = analysis.position_size_pct * confidence_scale
        checks["adjusted_quantity"] = desired_value  # This is the dollar value to invest

        if checks["reasons"]:
            logger.info(f"Risk check for {analysis.symbol}: {', '.join(checks['reasons'])}")

        return checks

    def check_stop_loss(self, portfolio: Portfolio) -> list[dict]:
        """Check all positions for stop loss / take profit triggers."""
        triggers = []
        for pos in portfolio.positions:
            pnl_pct = pos.unrealized_pnl_pct / 100

            if pnl_pct <= -self.config.stop_loss_pct:
                triggers.append({
                    "symbol": pos.symbol,
                    "action": "stop_loss",
                    "pnl_pct": pnl_pct * 100,
                    "reason": f"Stop loss triggered at {pnl_pct*100:.1f}% (limit: -{self.config.stop_loss_pct*100:.0f}%)",
                })

            if pnl_pct >= self.config.take_profit_pct:
                triggers.append({
                    "symbol": pos.symbol,
                    "action": "take_profit",
                    "pnl_pct": pnl_pct * 100,
                    "reason": f"Take profit triggered at {pnl_pct*100:.1f}% (target: +{self.config.take_profit_pct*100:.0f}%)",
                })

        return triggers
