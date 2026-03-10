#!/usr/bin/env python3
"""
Full System Integration Test

Demonstrates the complete trading system working together:
- Signal generation from strategies
- Signal aggregation via router
- Order execution through broker
- Position tracking
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "broker" / "python"))

from common import (
    TradingSignal,
    SignalType,
    DataProvider,
    SignalGenerator,
    SignalRouterImpl,
    RouterConfig,
    BacktestEngineImpl,
    BacktestConfig,
    BacktestResult,
    Bar,
    TimeFrame,
    Fundamentals,
    SentimentScore,
)

from broker.mock import MockBroker
from broker.base import Order, OrderSide, OrderType


class MockDataProvider(DataProvider):
    """Mock data provider with synthetic data"""

    def __init__(self, n_symbols: int = 20, n_days: int = 60):
        self.n_symbols = n_symbols
        self.n_days = n_days
        self.symbols = [f"600{str(i).zfill(3)}.SH" for i in range(1, n_symbols + 1)]

        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

        self.price_data = {}
        for symbol in self.symbols:
            returns = np.random.randn(n_days) * 0.02 + 0.0005
            prices = 100 * np.exp(np.cumsum(returns))
            prices = np.clip(prices, 10, 500)

            self.price_data[symbol] = pd.DataFrame({
                'timestamp': dates,
                'symbol': symbol,
                'open': prices * (1 + np.random.randn(n_days) * 0.005),
                'high': prices * (1 + np.abs(np.random.randn(n_days) * 0.01)),
                'low': prices * (1 - np.abs(np.random.randn(n_days) * 0.01)),
                'close': prices,
                'volume': np.random.randint(1000000, 10000000, n_days).astype(float),
            })

    def get_prices(self, symbols, start, end, timeframe=TimeFrame.DAY_1):
        dfs = []
        for symbol in symbols:
            if symbol in self.price_data:
                df = self.price_data[symbol].copy()
                df = df[(df['timestamp'] >= start) & (df['timestamp'] <= end)]
                dfs.append(df)
        if not dfs:
            return pd.DataFrame()
        result = pd.concat(dfs, ignore_index=True)
        result = result.set_index(['symbol', 'timestamp'])
        return result

    def get_latest_prices(self, symbols):
        result = {}
        for symbol in symbols:
            if symbol in self.price_data:
                result[symbol] = float(self.price_data[symbol]['close'].iloc[-1])
        return result

    def get_fundamentals(self, symbols, as_of=None):
        fundamentals = []
        for symbol in symbols:
            price = self.price_data[symbol]['close'].iloc[-1] if symbol in self.price_data else 100
            fundamentals.append(Fundamentals(
                symbol=symbol,
                timestamp=as_of or datetime.now(),
                pe_ratio=np.random.uniform(10, 40),
                pb_ratio=np.random.uniform(1, 5),
                roe=np.random.uniform(0.05, 0.25),
                eps=price / np.random.uniform(10, 30),
            ))
        return fundamentals

    def get_sentiment(self, symbols, start, end, source=None):
        return []

    def get_latest_sentiment(self, symbols):
        result = {}
        for symbol in symbols:
            result[symbol] = SentimentScore(
                symbol=symbol,
                timestamp=datetime.now(),
                score=np.random.randn() * 0.3,
                confidence=0.8,
                source='mock',
            )
        return result

    def get_universe(self, universe_name="csi300"):
        return self.symbols

    def get_bars(self, symbol, start, end, timeframe=TimeFrame.DAY_1):
        return []


class SimpleMomentumStrategy(SignalGenerator):
    """Simple momentum strategy"""

    @property
    def name(self) -> str:
        return "momentum"

    @property
    def time_horizon(self) -> str:
        return "medium_term"

    def generate_signals(self, symbols, as_of, data_provider):
        signals = []
        lookback = as_of - timedelta(days=30)
        prices = data_provider.get_prices(symbols, lookback, as_of)

        if prices.empty:
            return signals

        for symbol in symbols:
            try:
                symbol_prices = prices.xs(symbol, level=0)["close"]
                if len(symbol_prices) < 20:
                    continue

                returns = symbol_prices.pct_change().dropna()
                momentum = (returns.iloc[-5:].mean() - returns.iloc[-20:].mean())
                current_price = float(symbol_prices.iloc[-1])

                if momentum > 0.005:
                    signal = TradingSignal(
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        timestamp=as_of,
                        source=self.name,
                        strength=min(momentum * 5000, 100),
                        confidence=0.6,
                        entry_price=current_price,
                        stop_loss=current_price * 0.92,
                        take_profit=current_price * 1.15,
                        position_size=0.05,
                        reasons=[f"Positive momentum: {momentum:.4f}"],
                    )
                    signals.append(signal)
                elif momentum < -0.005:
                    signal = TradingSignal(
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        timestamp=as_of,
                        source=self.name,
                        strength=min(abs(momentum) * 5000, 100),
                        confidence=0.6,
                        entry_price=current_price,
                        stop_loss=current_price * 1.08,
                        take_profit=current_price * 0.85,
                        position_size=0.05,
                        reasons=[f"Negative momentum: {momentum:.4f}"],
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


def test_full_integration():
    """Test full system integration with broker"""
    print("=" * 60)
    print("Full System Integration Test")
    print("=" * 60)

    # 1. Create components
    print("\n1. Creating components...")
    data_provider = MockDataProvider(n_symbols=20, n_days=60)
    strategy = SimpleMomentumStrategy()
    broker = MockBroker(initial_cash=1_000_000.0)

    # 2. Connect broker
    print("\n2. Connecting to broker...")
    broker.connect()

    # 3. Generate signals
    print("\n3. Generating signals...")
    symbols = data_provider.get_universe()
    as_of = datetime.now()

    signals = strategy.generate_signals(symbols, as_of, data_provider)
    print(f"   Generated {len(signals)} signals")

    # 4. Execute signals through broker
    print("\n4. Executing signals through broker...")
    prices = data_provider.get_latest_prices(symbols)

    executed = 0
    for signal in signals[:5]:  # Execute top 5 signals
        if signal.signal_type == SignalType.BUY:
            # Set market price
            if signal.symbol in prices:
                broker.set_market_price(signal.symbol, prices[signal.symbol])

            # Calculate quantity
            quantity = int(broker.cash * 0.05 / prices[signal.symbol])

            # Create order
            order = Order(
                symbol=signal.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=quantity,
                source_signal=signal.source,
            )

            result = broker.place_order(order)
            if result.status.name == "FILLED":
                executed += 1
                print(f"   BUY {signal.symbol}: {quantity} shares @ ¥{result.avg_fill_price:.2f}")

    # 5. Check positions
    print("\n5. Current positions:")
    positions = broker.get_positions()
    for pos in positions:
        print(f"   {pos.symbol}: {pos.quantity} shares @ ¥{pos.avg_cost:.2f}")
        print(f"      Market Value: ¥{pos.market_value:,.2f}")
        print(f"      Unrealized P&L: ¥{pos.unrealized_pnl:,.2f}")

    # 6. Account summary
    print("\n6. Account summary:")
    print(f"   Cash: ¥{broker.cash:,.2f}")
    print(f"   Total Equity: ¥{broker.get_total_equity():,.2f}")

    # 7. Simulate price movement and update positions
    print("\n7. Simulating price movement...")
    for pos in positions:
        # Simulate 5% price increase
        new_price = pos.current_price * 1.05
        broker.set_market_price(pos.symbol, new_price)
        print(f"   {pos.symbol}: Price updated to ¥{new_price:.2f}")

    # 8. Check updated positions
    print("\n8. Updated positions:")
    positions = broker.get_positions()
    for pos in positions:
        print(f"   {pos.symbol}: Unrealized P&L: ¥{pos.unrealized_pnl:,.2f} ({pos.return_pct:.2%})")

    # 9. Close positions
    print("\n9. Closing positions...")
    for pos in positions:
        # Create sell order
        order = Order(
            symbol=pos.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=pos.quantity,
            source_signal="exit",
        )
        result = broker.place_order(order)
        print(f"   SELL {pos.symbol}: {pos.quantity} shares @ ¥{result.avg_fill_price:.2f}")

    # 10. Final summary
    print("\n10. Final account summary:")
    print(f"   Cash: ¥{broker.cash:,.2f}")
    print(f"   Total Equity: ¥{broker.get_total_equity():,.2f}")
    print(f"   Positions: {len(broker.get_positions())}")

    # Calculate realized P&L
    total_realized = sum(p.realized_pnl for p in broker.get_positions())
    final_pnl = broker.cash - broker.initial_cash
    print(f"   Realized P&L: ¥{final_pnl:,.2f}")

    # Disconnect
    broker.disconnect()

    print("\n" + "=" * 60)
    print("Integration test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    test_full_integration()
