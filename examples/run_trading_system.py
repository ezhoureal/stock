#!/usr/bin/env python3
"""
Trading System Example

Demonstrates how to use the unified trading system interfaces.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import (
    BacktestConfig,
    TradingSystem,
    create_system,
    quick_backtest,
)


def example_signal_generation():
    """Example: Generate signals from all strategies"""
    print("=" * 60)
    print("Example 1: Signal Generation")
    print("=" * 60)

    # Create system with default config
    system = TradingSystem()
    system.initialize()

    # Run signal generation for a subset of symbols
    symbols = ["600519.SH", "000858.SZ", "601318.SH"]  # Kweichow Moutai, Wuliangye, Ping An

    portfolio = system.run_once(symbols=symbols)

    print(f"\nGenerated {portfolio.signal_count} signals:")
    print(f"  Long signals: {portfolio.long_count}")
    print(f"  Short signals: {portfolio.short_count}")
    print(f"  Total exposure: {portfolio.total_exposure:.2%}")
    print(f"  Net exposure: {portfolio.net_exposure:.2%}")

    for signal in portfolio.signals:
        print(f"\n  {signal.symbol}: {signal.signal_type.value}")
        print(f"    Source: {signal.source}")
        print(f"    Strength: {signal.strength:.1f}")
        print(f"    Confidence: {signal.confidence:.2f}")
        if signal.entry_price:
            print(f"    Entry: ¥{signal.entry_price:.2f}")
        if signal.reasons:
            print(f"    Reasons: {', '.join(signal.reasons)}")

    system.shutdown()


def example_backtest():
    """Example: Run a backtest"""
    print("\n" + "=" * 60)
    print("Example 2: Backtesting")
    print("=" * 60)

    # Create system
    system = create_system()

    # Configure backtest
    BacktestConfig(
        initial_capital=1_000_000.0,
        commission_rate=0.0003,
        slippage_rate=0.001,
        stamp_duty=0.001,
        save_trades=True,
        save_equity_curve=True,
    )

    # Run backtest for sentiment arbitrage strategy
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)  # 6 months

    print(f"\nRunning backtest from {start_date.date()} to {end_date.date()}...")

    result = system.run_backtest(
        strategy_name="sentiment_arbitrage",
        start_date=start_date,
        end_date=end_date,
        initial_capital=1_000_000.0,
    )

    print(result.summary())

    system.shutdown()


def example_quick_backtest():
    """Example: Quick backtest with defaults"""
    print("\n" + "=" * 60)
    print("Example 3: Quick Backtest")
    print("=" * 60)

    # Run a quick 1-year backtest
    result = quick_backtest(
        strategy_name="sentiment_arbitrage",
        days=365,
        initial_capital=500_000.0,
    )

    print(result.summary())


def example_custom_strategy():
    """Example: Add a custom strategy"""
    print("\n" + "=" * 60)
    print("Example 4: Custom Strategy")
    print("=" * 60)

    from common import SignalGenerator, SignalType, TradingSignal

    class SimpleMomentumStrategy(SignalGenerator):
        """Simple momentum strategy example"""

        @property
        def name(self) -> str:
            return "simple_momentum"

        @property
        def time_horizon(self) -> str:
            return "medium_term"

        def generate_signals(self, symbols, as_of, data_provider):
            signals = []

            # Get price data
            lookback = as_of - timedelta(days=30)
            prices = data_provider.get_prices(symbols, lookback, as_of)

            if prices.empty:
                return signals

            for symbol in symbols:
                try:
                    symbol_prices: pd.Series = pd.Series(prices.xs(symbol, level=0)["close"])

                    if len(symbol_prices) < 20:
                        continue

                    # Simple momentum: buy if price > 20-day MA
                    rolling_mean: Any = symbol_prices.rolling(20).mean()
                    ma20: float = float(rolling_mean.iloc[-1])
                    current_price: float = float(symbol_prices.iloc[-1])

                    if current_price > ma20 * 1.02:  # 2% above MA
                        signal = TradingSignal(
                            symbol=symbol,
                            signal_type=SignalType.BUY,
                            timestamp=as_of,
                            source=self.name,
                            strength=50.0,
                            confidence=0.5,
                            entry_price=float(current_price),
                            reasons=[f"Price {current_price:.2f} > MA20 {ma20:.2f}"],
                        )
                        signals.append(signal)

                except Exception:
                    continue

            return signals

        def update(self, new_data):
            pass

        def get_state(self):
            return {}

        def set_state(self, state):
            pass

        def get_required_data(self):
            return ["prices"]

    # Create system and add custom strategy
    system = create_system()

    custom_strategy = SimpleMomentumStrategy()
    system.add_strategy(custom_strategy)

    # Run with custom strategy
    symbols = ["600519.SH", "000858.SZ", "601318.SH"]
    portfolio = system.run_once(symbols=symbols)

    print("\nSignals from custom strategy:")
    for signal in portfolio.signals:
        if signal.source == "simple_momentum":
            print(f"  {signal.symbol}: {signal.signal_type.value}")
            print(f"    {', '.join(signal.reasons)}")

    system.shutdown()


def example_data_provider():
    """Example: Using the data provider directly"""
    # This example requires a DataProvider implementation.
    # Create your own provider by implementing the DataProvider interface,
    # or use one of the existing providers from the data module.
    print("\n" + "=" * 60)
    print("Example 5: Data Provider")
    print("=" * 60)
    print("\nTo use a data provider, implement the DataProvider interface")
    print("and set it on the trading system using system.set_data_provider().")
    print("\nAvailable providers from the data module:")
    print("  - SentimentStorage: Sentiment data from DuckDB")
    print("  - ValuationDataProvider: Valuation metrics from AKShare")
    # Uncomment when you have a DataProvider implementation:
    #
    # from common import DataProvider
    # from my_provider import MyDataProvider
    #
    # provider = MyDataProvider()
    # system = create_system()
    # system.set_data_provider(provider)
    #
    # # Get universe
    # universe = provider.get_universe("csi300")
    # print(f"\nCSI 300 universe: {len(universe)} stocks")


def main():
    """Run all examples"""
    print("\n" + "#" * 60)
    print("# Chinese Stock Trading System - Examples")
    print("#" * 60)

    # Run examples (comment out any you don't want to run)
    try:
        example_signal_generation()
    except Exception as e:
        print(f"Signal generation example failed: {e}")

    try:
        example_data_provider()
    except Exception as e:
        print(f"Data provider example failed: {e}")

    # These require historical data in the database
    # try:
    #     example_backtest()
    # except Exception as e:
    #     print(f"Backtest example failed: {e}")

    # try:
    #     example_custom_strategy()
    # except Exception as e:
    #     print(f"Custom strategy example failed: {e}")


if __name__ == "__main__":
    main()
