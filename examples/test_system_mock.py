#!/usr/bin/env python3
"""
Test Trading System with Mock Data

Demonstrates the full system working with synthetic data.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import (
    TradingSignal,
    SignalType,
    DataProvider,
    SignalGenerator,
    SignalRouterImpl,
    RouterConfig,
    BacktestConfig,
    BacktestResult,
    Bar,
    TimeFrame,
    Fundamentals,
    SentimentScore,
)
from backtest import BacktestEngineImpl


class MockDataProvider(DataProvider):
    """Mock data provider with synthetic data"""

    def __init__(self, n_symbols: int = 50, n_days: int = 252):
        self.n_symbols = n_symbols
        self.n_days = n_days
        self.symbols = [f"600{str(i).zfill(3)}.SH" for i in range(1, n_symbols + 1)]

        # Generate synthetic price data
        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')

        self.price_data = {}
        for symbol in self.symbols:
            # Random walk with drift
            returns = np.random.randn(n_days) * 0.02 + 0.0005
            prices = 100 * np.exp(np.cumsum(returns))
            prices = np.clip(prices, 10, 500)  # Keep prices reasonable

            self.price_data[symbol] = pd.DataFrame({
                'timestamp': dates,
                'symbol': symbol,
                'open': prices * (1 + np.random.randn(n_days) * 0.005),
                'high': prices * (1 + np.abs(np.random.randn(n_days) * 0.01)),
                'low': prices * (1 - np.abs(np.random.randn(n_days) * 0.01)),
                'close': prices,
                'volume': np.random.randint(1000000, 10000000, n_days).astype(float),
            })

        # Generate sentiment data
        self.sentiment_data = {}
        for symbol in self.symbols:
            scores = np.random.randn(n_days) * 0.5  # Random sentiment
            self.sentiment_data[symbol] = pd.DataFrame({
                'timestamp': dates,
                'symbol': symbol,
                'score': scores,
            })

    def get_prices(
        self,
        symbols: List[str],
        start: datetime,
        end: datetime,
        timeframe: TimeFrame = TimeFrame.DAY_1,
    ) -> pd.DataFrame:
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

    def get_latest_prices(self, symbols: List[str]) -> Dict[str, float]:
        result = {}
        for symbol in symbols:
            if symbol in self.price_data:
                result[symbol] = float(self.price_data[symbol]['close'].iloc[-1])
        return result

    def get_fundamentals(
        self,
        symbols: List[str],
        as_of: Optional[datetime] = None,
    ) -> List[Fundamentals]:
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
                sector=np.random.choice(['Technology', 'Finance', 'Consumer', 'Healthcare']),
            ))
        return fundamentals

    def get_sentiment(
        self,
        symbols: List[str],
        start: datetime,
        end: datetime,
        source: Optional[str] = None,
    ) -> List[SentimentScore]:
        scores = []
        for symbol in symbols:
            if symbol in self.sentiment_data:
                df = self.sentiment_data[symbol]
                df = df[(df['timestamp'] >= start) & (df['timestamp'] <= end)]
                for _, row in df.iterrows():
                    scores.append(SentimentScore(
                        symbol=symbol,
                        timestamp=row['timestamp'],
                        score=row['score'],
                        confidence=0.8,
                        source='mock',
                    ))
        return scores

    def get_latest_sentiment(self, symbols: List[str]) -> Dict[str, SentimentScore]:
        result = {}
        for symbol in symbols:
            if symbol in self.sentiment_data:
                last = self.sentiment_data[symbol].iloc[-1]
                result[symbol] = SentimentScore(
                    symbol=symbol,
                    timestamp=last['timestamp'],
                    score=last['score'],
                    confidence=0.8,
                    source='mock',
                )
        return result

    def get_universe(self, universe_name: str = "csi300") -> List[str]:
        return self.symbols

    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: TimeFrame = TimeFrame.DAY_1,
    ) -> List[Bar]:
        if symbol not in self.price_data:
            return []

        df = self.price_data[symbol]
        df = df[(df['timestamp'] >= start) & (df['timestamp'] <= end)]

        bars = []
        for _, row in df.iterrows():
            bars.append(Bar(
                symbol=symbol,
                timestamp=row['timestamp'],
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row['volume'],
            ))
        return bars


class SimpleMomentumStrategy(SignalGenerator):
    """Simple momentum strategy for testing"""

    @property
    def name(self) -> str:
        return "momentum"

    @property
    def time_horizon(self) -> str:
        return "medium_term"

    def generate_signals(
        self,
        symbols: List[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> List[TradingSignal]:
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

                # Calculate momentum
                returns = symbol_prices.pct_change().dropna()
                momentum = (returns.iloc[-5:].mean() - returns.iloc[-20:].mean())

                current_price = float(symbol_prices.iloc[-1])

                if momentum > 0.005:  # Positive momentum
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
                        reasons=[f"Positive momentum: {momentum:.4f}"],
                    )
                    signals.append(signal)
                elif momentum < -0.005:  # Negative momentum
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
                        reasons=[f"Negative momentum: {momentum:.4f}"],
                    )
                    signals.append(signal)

            except Exception:
                continue

        return signals

    def update(self, new_data: Dict[str, Any]) -> None:
        pass

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_state(self, state: Dict[str, Any]) -> None:
        pass

    def get_required_data(self) -> List[str]:
        return ["prices"]


class SentimentStrategy(SignalGenerator):
    """Sentiment-based strategy for testing"""

    @property
    def name(self) -> str:
        return "sentiment"

    @property
    def time_horizon(self) -> str:
        return "short_term"

    def generate_signals(
        self,
        symbols: List[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> List[TradingSignal]:
        signals = []

        # Get sentiment
        lookback = as_of - timedelta(days=5)
        sentiment = data_provider.get_sentiment(symbols, lookback, as_of)

        if not sentiment:
            return signals

        # Aggregate sentiment by symbol
        sentiment_map = {}
        for s in sentiment:
            if s.symbol not in sentiment_map:
                sentiment_map[s.symbol] = []
            sentiment_map[s.symbol].append(s.score)

        # Get latest prices
        prices = data_provider.get_latest_prices(symbols)

        for symbol, scores in sentiment_map.items():
            avg_sentiment = np.mean(scores)
            current_price = prices.get(symbol)

            if not current_price:
                continue

            if avg_sentiment > 0.5:  # Bullish sentiment
                signal = TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    timestamp=as_of,
                    source=self.name,
                    strength=min(avg_sentiment * 50, 100),
                    confidence=0.7,
                    entry_price=current_price,
                    sentiment_score=avg_sentiment,
                    reasons=[f"Bullish sentiment: {avg_sentiment:.2f}"],
                )
                signals.append(signal)
            elif avg_sentiment < -0.5:  # Bearish sentiment
                signal = TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    timestamp=as_of,
                    source=self.name,
                    strength=min(abs(avg_sentiment) * 50, 100),
                    confidence=0.7,
                    entry_price=current_price,
                    sentiment_score=avg_sentiment,
                    reasons=[f"Bearish sentiment: {avg_sentiment:.2f}"],
                )
                signals.append(signal)

        return signals

    def update(self, new_data: Dict[str, Any]) -> None:
        pass

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_state(self, state: Dict[str, Any]) -> None:
        pass

    def get_required_data(self) -> List[str]:
        return ["prices", "sentiment"]


def test_signal_generation():
    """Test signal generation with mock data"""
    print("=" * 60)
    print("Test 1: Signal Generation")
    print("=" * 60)

    # Create mock data provider
    data_provider = MockDataProvider(n_symbols=50, n_days=252)

    # Create strategies
    momentum_strategy = SimpleMomentumStrategy()
    sentiment_strategy = SentimentStrategy()

    # Create router
    config = RouterConfig(
        sentiment_arb_weight=0.5,
        strategy_weight=0.5,
        min_conviction=0.3,
        min_strength=20.0,
    )
    router = SignalRouterImpl(config)
    router.add_strategy(momentum_strategy)
    router.add_strategy(sentiment_strategy)

    # Generate signals
    symbols = data_provider.get_universe()[:30]  # Test with 30 symbols
    as_of = datetime.now()

    portfolio = router.aggregate_signals(symbols, as_of, data_provider)

    print(f"\nGenerated {portfolio.signal_count} signals:")
    print(f"  Long: {portfolio.long_count}")
    print(f"  Short: {portfolio.short_count}")
    print(f"  Total Exposure: {portfolio.total_exposure:.2%}")
    print(f"  Net Exposure: {portfolio.net_exposure:.2%}")

    print("\nTop 10 signals by strength:")
    sorted_signals = sorted(portfolio.signals, key=lambda s: s.strength, reverse=True)[:10]
    for signal in sorted_signals:
        print(f"  {signal.symbol}: {signal.signal_type.value:6} | "
              f"Strength: {signal.strength:5.1f} | "
              f"Source: {signal.source:10} | "
              f"Price: ¥{signal.entry_price:.2f}")


def test_backtest():
    """Test backtesting with mock data"""
    print("\n" + "=" * 60)
    print("Test 2: Backtesting")
    print("=" * 60)

    # Create mock data provider
    data_provider = MockDataProvider(n_symbols=30, n_days=252)

    # Create strategy
    strategy = SimpleMomentumStrategy()

    # Configure backtest
    config = BacktestConfig(
        initial_capital=1_000_000.0,
        commission_rate=0.0003,
        min_commission=5.0,
        slippage_rate=0.001,
        stamp_duty=0.001,
        max_position_pct=0.10,
    )

    # Run backtest
    engine = BacktestEngineImpl(data_provider, config)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)

    print(f"\nRunning backtest from {start_date.date()} to {end_date.date()}...")
    print(f"Initial capital: ¥{config.initial_capital:,.2f}")

    result = engine.run(
        strategy=strategy,
        symbols=data_provider.get_universe(),
        start=start_date,
        end=end_date,
        initial_capital=config.initial_capital,
    )

    print(result.summary())

    print(f"\nTrades breakdown:")
    if result.trades:
        buy_trades = [t for t in result.trades if t.side == "BUY"]
        sell_trades = [t for t in result.trades if t.side == "SELL"]
        print(f"  Total trades: {len(result.trades)}")
        print(f"  Buys: {len(buy_trades)}, Sells: {len(sell_trades)}")
        print(f"  Total commission: ¥{sum(t.commission for t in result.trades):,.2f}")


def test_data_provider():
    """Test data provider functionality"""
    print("\n" + "=" * 60)
    print("Test 3: Data Provider")
    print("=" * 60)

    data_provider = MockDataProvider(n_symbols=50, n_days=252)

    # Test universe
    universe = data_provider.get_universe()
    print(f"\nUniverse size: {len(universe)} stocks")

    # Test prices
    symbols = universe[:5]
    end = datetime.now()
    start = end - timedelta(days=30)

    prices = data_provider.get_prices(symbols, start, end)
    print(f"\nPrice data shape: {prices.shape}")
    print(f"Date range: {prices.index.get_level_values(1).min().date()} to {prices.index.get_level_values(1).max().date()}")

    # Test latest prices
    latest = data_provider.get_latest_prices(symbols)
    print(f"\nLatest prices:")
    for symbol, price in latest.items():
        print(f"  {symbol}: ¥{price:.2f}")

    # Test sentiment
    sentiment = data_provider.get_latest_sentiment(symbols)
    print(f"\nLatest sentiment:")
    for symbol, sent in sentiment.items():
        print(f"  {symbol}: {sent.score:.2f}")


def main():
    print("\n" + "#" * 60)
    print("# Trading System Tests with Mock Data")
    print("#" * 60)

    test_data_provider()
    test_signal_generation()
    test_backtest()

    print("\n" + "#" * 60)
    print("# All tests completed!")
    print("#" * 60)


if __name__ == "__main__":
    main()
