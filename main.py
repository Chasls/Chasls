#!/usr/bin/env python3
"""
Chasls AI Trading Bot
=====================
An AI-powered trading bot that uses Claude to analyze markets
and execute stock/crypto trades.

Usage:
    python main.py                  # Run once
    python main.py --loop           # Run continuously
    python main.py --status         # Show portfolio status
    python main.py --backtest       # Review recent trade history
"""

import argparse
import logging
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.bot import TradingBot
from src.config import load_config

console = Console()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/bot.log", mode="a"),
        ],
    )


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]Chasls AI Trading Bot[/bold cyan]\n"
        "[dim]Powered by Claude Opus - AI-Driven Market Analysis[/dim]\n"
        "[yellow]Always start with paper trading![/yellow]",
        border_style="cyan",
    ))


def print_portfolio(portfolio: dict):
    """Display portfolio status."""
    table = Table(title="Portfolio Status", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Cash", f"${portfolio['cash']:,.2f}")
    table.add_row("Total Value", f"${portfolio['total_value']:,.2f}")
    table.add_row("Open Positions", str(portfolio['positions']))
    pnl_color = "green" if portfolio['total_pnl'] >= 0 else "red"
    table.add_row("Total P&L", f"[{pnl_color}]${portfolio['total_pnl']:,.2f}[/{pnl_color}]")
    table.add_row("Max Drawdown", f"{portfolio['max_drawdown']:.2f}%")

    console.print(table)


def print_trades(trades: list[dict]):
    """Display executed trades."""
    if not trades:
        console.print("[dim]No trades executed this cycle.[/dim]")
        return

    table = Table(title="Trades Executed", show_header=True, header_style="bold green")
    table.add_column("Symbol", style="cyan")
    table.add_column("Action")
    table.add_column("Quantity", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Status")
    table.add_column("Reasoning", max_width=50)

    for t in trades:
        action_color = "green" if t["action"] == "buy" else "red"
        status_color = "green" if t["status"] == "filled" else "yellow"
        table.add_row(
            t["symbol"],
            f"[{action_color}]{t['action'].upper()}[/{action_color}]",
            f"{t['quantity']:.4f}",
            f"${t['price']:.2f}",
            f"[{status_color}]{t['status']}[/{status_color}]",
            t["reasoning"][:50] + "..." if len(t["reasoning"]) > 50 else t["reasoning"],
        )

    console.print(table)


def run_once(bot: TradingBot):
    """Run a single analysis and trading cycle."""
    console.print("\n[bold]Running analysis cycle...[/bold]")
    results = bot.run_cycle()

    console.print(f"\n[dim]Data: {results['market_data_count']} assets, {results['news_count']} news items[/dim]")
    console.print(f"[dim]AI Recommendations: {results['recommendations']}[/dim]")

    if results.get("trades"):
        print_trades(results["trades"])

    if results.get("portfolio"):
        print_portfolio(results["portfolio"])

    if results.get("error"):
        console.print(f"[red]Error: {results['error']}[/red]")

    return results


def run_loop(bot: TradingBot, interval_min: int = 15):
    """Run continuously with specified interval."""
    console.print(f"[bold]Starting continuous trading loop (every {interval_min} min)[/bold]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    cycle = 0
    while True:
        try:
            cycle += 1
            console.print(f"\n[bold cyan]--- Cycle {cycle} @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---[/bold cyan]")
            run_once(bot)

            console.print(f"\n[dim]Next cycle in {interval_min} minutes...[/dim]")
            time.sleep(interval_min * 60)

        except KeyboardInterrupt:
            console.print("\n[yellow]Bot stopped by user.[/yellow]")
            break


def show_status(bot: TradingBot):
    """Show current portfolio status without trading."""
    console.print("\n[bold]Current Portfolio Status[/bold]")
    portfolio = bot._get_portfolio()
    if hasattr(bot.stock_executor, "get_portfolio"):
        portfolio = bot.stock_executor.get_portfolio()

    print_portfolio({
        "cash": portfolio.cash,
        "total_value": portfolio.total_value,
        "positions": len(portfolio.positions),
        "total_pnl": portfolio.total_pnl,
        "max_drawdown": portfolio.max_drawdown,
    })

    if portfolio.positions:
        table = Table(title="Open Positions", show_header=True, header_style="bold blue")
        table.add_column("Symbol", style="cyan")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("P&L %", justify="right")

        for pos in portfolio.positions:
            pnl_color = "green" if pos.unrealized_pnl >= 0 else "red"
            table.add_row(
                pos.symbol,
                f"{pos.quantity:.4f}",
                f"${pos.entry_price:.2f}",
                f"${pos.current_price:.2f}",
                f"[{pnl_color}]${pos.unrealized_pnl:,.2f}[/{pnl_color}]",
                f"[{pnl_color}]{pos.unrealized_pnl_pct:+.2f}%[/{pnl_color}]",
            )
        console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Chasls AI Trading Bot")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--status", action="store_true", help="Show portfolio status")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--mode", choices=["paper", "live"], default=None,
                        help="Override trading mode")
    parser.add_argument("--interval", type=int, default=None,
                        help="Analysis interval in minutes (default: 15)")
    args = parser.parse_args()

    # Setup
    import os
    os.makedirs("logs", exist_ok=True)
    setup_logging(args.verbose)
    print_banner()

    # Load config
    config = load_config()

    if not config["anthropic_api_key"]:
        console.print("[red]ERROR: ANTHROPIC_API_KEY not set![/red]")
        console.print("Copy .env.example to .env and add your API key.")
        sys.exit(1)

    if args.mode:
        config["trading_mode"] = args.mode

    # Safety warning for live trading
    if config["trading_mode"] == "live":
        console.print(Panel(
            "[bold red]WARNING: LIVE TRADING MODE[/bold red]\n"
            "Real money will be used. Ensure you understand the risks.\n"
            "The bot makes autonomous decisions - monitor closely.",
            border_style="red",
        ))
        response = input("Type 'I UNDERSTAND THE RISKS' to continue: ")
        if response != "I UNDERSTAND THE RISKS":
            console.print("[yellow]Switching to paper trading mode.[/yellow]")
            config["trading_mode"] = "paper"

    console.print(f"[dim]Mode: {config['trading_mode'].upper()}[/dim]")
    console.print(f"[dim]Claude Model: {config['claude_model']}[/dim]")
    console.print(f"[dim]Stocks: {', '.join(config['stock_watchlist'])}[/dim]")
    console.print(f"[dim]Crypto: {', '.join(config['crypto_watchlist'])}[/dim]")

    # Initialize bot
    bot = TradingBot(config)

    # Run
    if args.status:
        show_status(bot)
    elif args.loop:
        interval = args.interval or config["analysis_interval_min"]
        run_loop(bot, interval)
    else:
        run_once(bot)


if __name__ == "__main__":
    main()
