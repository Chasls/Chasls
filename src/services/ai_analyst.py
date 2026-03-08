"""Claude AI market analyst - the brain of the trading bot."""

import json
import logging
from datetime import datetime
from typing import Optional

import anthropic

from src.models.schemas import (
    AnalysisResult,
    MarketData,
    NewsItem,
    Portfolio,
    Signal,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an elite quantitative trading analyst and portfolio manager with deep expertise in:
- Technical analysis (chart patterns, indicators, momentum)
- Fundamental analysis (earnings, valuations, macro economics)
- Sentiment analysis (news, social media, market psychology)
- Risk management (position sizing, stop losses, portfolio correlation)
- Both stock and cryptocurrency markets

Your job is to analyze market data, news, and portfolio state to make profitable trading decisions.

CRITICAL RULES:
1. Always think about RISK FIRST. Protect capital above all.
2. Consider macro environment (interest rates, inflation, geopolitics).
3. Look for asymmetric opportunities (limited downside, large upside).
4. Be aware of market manipulation, pump-and-dump schemes, and hype cycles.
5. Factor in correlation - don't overload on correlated positions.
6. Recognize when to sit in cash. Not trading IS a valid strategy.
7. Watch for catalysts: earnings, FDA approvals, halvings, regulatory news, Fed meetings.
8. Consider market hours, liquidity, and timing of trades.
9. Scale positions based on conviction level.
10. Always provide clear reasoning for every recommendation.

RESPONSE FORMAT: You must respond with valid JSON only."""

ANALYSIS_PROMPT = """Analyze the following market data, news, and portfolio state. Provide your trading recommendations.

## Current Portfolio
{portfolio}

## Market Overview
{market_overview}

## Asset Data
{asset_data}

## Recent News & Events
{news}

## Current Positions
{positions}

Based on ALL the above information, provide your analysis as a JSON array of recommendations.
Each recommendation should be:
{{
    "symbol": "TICKER",
    "signal": "strong_buy|buy|hold|sell|strong_sell",
    "confidence": 0.0-1.0,
    "reasoning": "Detailed explanation of why",
    "target_price": null or float,
    "stop_loss": null or float,
    "take_profit": null or float,
    "position_size_pct": 0.01-0.10,
    "catalysts": ["list", "of", "catalysts"],
    "risks": ["list", "of", "risks"]
}}

Rules:
- Only recommend trades with confidence >= 0.6
- Position size should scale with confidence (higher confidence = larger position)
- Always include stop_loss for buy/sell recommendations
- Consider existing positions before recommending
- If market conditions are uncertain, recommend HOLD with smaller positions
- Include at least 2 risks for every trade
- Factor in the current macro environment

Respond with ONLY the JSON array, no other text."""

REBALANCE_PROMPT = """Review the current portfolio and recommend rebalancing actions.

## Portfolio
{portfolio}

## Positions
{positions}

## Market Overview
{market_overview}

Analyze:
1. Are any positions too large (>10% of portfolio)?
2. Are there highly correlated positions increasing risk?
3. Should we take profits on winners or cut losses?
4. Is our cash allocation appropriate given market conditions?

Respond with a JSON array of rebalancing recommendations using the same format as trade recommendations."""


class AIAnalyst:
    """Uses Claude to analyze markets and generate trading signals."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-20250918"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze_markets(
        self,
        market_data: list[MarketData],
        news: list[NewsItem],
        portfolio: Portfolio,
        market_overview: dict,
    ) -> list[AnalysisResult]:
        """Run full market analysis through Claude and return trade signals."""

        # Format all data for the prompt
        asset_data_str = "\n\n".join(
            self._format_market_data(md) for md in market_data
        )

        news_str = "\n".join(
            f"- [{n.published.strftime('%m/%d %H:%M')}] {n.title} ({n.source})\n  {n.summary[:200]}"
            for n in news[:30]
        )

        positions_str = self._format_positions(portfolio)
        portfolio_str = self._format_portfolio(portfolio)
        overview_str = self._format_overview(market_overview)

        prompt = ANALYSIS_PROMPT.format(
            portfolio=portfolio_str,
            market_overview=overview_str,
            asset_data=asset_data_str,
            news=news_str if news_str else "No recent news available.",
            positions=positions_str,
        )

        return self._call_claude(prompt)

    def rebalance_check(
        self,
        portfolio: Portfolio,
        market_overview: dict,
    ) -> list[AnalysisResult]:
        """Ask Claude if the portfolio needs rebalancing."""
        positions_str = self._format_positions(portfolio)
        portfolio_str = self._format_portfolio(portfolio)
        overview_str = self._format_overview(market_overview)

        prompt = REBALANCE_PROMPT.format(
            portfolio=portfolio_str,
            positions=positions_str,
            market_overview=overview_str,
        )

        return self._call_claude(prompt)

    def _call_claude(self, prompt: str) -> list[AnalysisResult]:
        """Send analysis request to Claude and parse response."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text.strip()

            # Clean up response - extract JSON array
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            recommendations = json.loads(content)

            results = []
            for rec in recommendations:
                try:
                    results.append(AnalysisResult(
                        symbol=rec["symbol"],
                        signal=Signal(rec["signal"]),
                        confidence=float(rec["confidence"]),
                        reasoning=rec["reasoning"],
                        target_price=rec.get("target_price"),
                        stop_loss=rec.get("stop_loss"),
                        take_profit=rec.get("take_profit"),
                        position_size_pct=float(rec.get("position_size_pct", 0.05)),
                        catalysts=rec.get("catalysts", []),
                        risks=rec.get("risks", []),
                    ))
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping malformed recommendation: {e}")

            logger.info(f"Claude returned {len(results)} recommendations")
            return results

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            return []

    def _format_market_data(self, md: MarketData) -> str:
        """Format a single MarketData object for the prompt."""
        lines = [
            f"### {md.symbol} ({md.asset_type.value})",
            f"Price: ${md.current_price:.2f} ({md.change_pct:+.2f}%)",
            f"Range: ${md.low_24h:.2f} - ${md.high_24h:.2f}",
            f"Volume: {md.volume:,.0f}",
        ]
        if md.rsi:
            lines.append(f"RSI: {md.rsi:.1f}")
        if md.sma_20:
            above_below = "above" if md.current_price > md.sma_20 else "below"
            lines.append(f"Price is {above_below} SMA20 (${md.sma_20:.2f})")
        if md.sma_50:
            above_below = "above" if md.current_price > md.sma_50 else "below"
            lines.append(f"Price is {above_below} SMA50 (${md.sma_50:.2f})")
        if md.macd is not None:
            crossover = "bullish" if md.macd > md.macd_signal else "bearish"
            lines.append(f"MACD: {md.macd:.4f} (signal: {md.macd_signal:.4f}, {crossover})")
        if md.bollinger_upper:
            if md.current_price > md.bollinger_upper:
                lines.append(f"Price ABOVE upper Bollinger Band (${md.bollinger_upper:.2f}) - overbought")
            elif md.current_price < md.bollinger_lower:
                lines.append(f"Price BELOW lower Bollinger Band (${md.bollinger_lower:.2f}) - oversold")
        return "\n".join(lines)

    def _format_positions(self, portfolio: Portfolio) -> str:
        if not portfolio.positions:
            return "No open positions."
        lines = []
        for p in portfolio.positions:
            lines.append(
                f"- {p.symbol}: {p.quantity} shares @ ${p.entry_price:.2f} "
                f"(now ${p.current_price:.2f}, P&L: {p.unrealized_pnl_pct:+.2f}%)"
            )
        return "\n".join(lines)

    def _format_portfolio(self, portfolio: Portfolio) -> str:
        return (
            f"Cash: ${portfolio.cash:,.2f}\n"
            f"Total Value: ${portfolio.total_value:,.2f}\n"
            f"Daily P&L: ${portfolio.daily_pnl:,.2f}\n"
            f"Total P&L: ${portfolio.total_pnl:,.2f}\n"
            f"Trades Today: {portfolio.daily_trades}\n"
            f"Max Drawdown: {portfolio.max_drawdown:.2f}%"
        )

    def _format_overview(self, overview: dict) -> str:
        if not overview:
            return "Market overview unavailable."
        lines = []
        for name, data in overview.items():
            lines.append(f"- {name}: {data['price']} ({data['change_pct']:+.2f}%)")
        return "\n".join(lines)
