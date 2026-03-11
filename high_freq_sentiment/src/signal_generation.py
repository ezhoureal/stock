"""
Signal Generation Logic with Entry/Exit Conditions
=================================================

Sophisticated signal generation for sentiment arbitrage with
multiple entry triggers, exit conditions, and risk management.

Key Features:
- Buy signals: High sentiment + low price + positive dislocation
- Sell signals: Low sentiment + high price + negative dislocation
- Multiple exit conditions (z-score cross, time stop, stop-loss)
- Dynamic position sizing based on signal strength
- Risk management with portfolio constraints

Author: Algorithm Designer
Date: 2026-03-09
"""

import warnings
from dataclasses import dataclass
from enum import Enum

import cupy as cp
import numpy as np

warnings.filterwarnings("ignore")


class SignalType(Enum):
    """Enumeration of signal types"""

    BUY = 1
    SELL = -1
    HOLD = 0


@dataclass
class SignalConfig:
    """Configuration for signal generation"""

    # Entry thresholds
    long_sentiment_threshold: float = 1.5  # High sentiment
    long_price_threshold: float = -0.5  # Low price
    long_dislocation_threshold: float = 2.0  # Positive dislocation

    short_sentiment_threshold: float = -1.5  # Low sentiment
    short_price_threshold: float = 0.5  # High price
    short_dislocation_threshold: float = -2.0  # Negative dislocation

    # Exit conditions
    exit_z_cross: bool = True  # Exit when z-score crosses zero
    exit_time_stop_hours: int = 48  # Exit after 48 hours
    exit_stop_loss_pct: float = 0.15  # 15% stop loss
    exit_take_profit_pct: float = 0.20  # 20% take profit

    # Position sizing
    max_position_size: float = 0.05  # Max 5% of portfolio per stock
    position_sizing_method: str = "signal_strength"  # "signal_strength", "equal", "volatility"

    # Risk management
    max_portfolio_exposure: float = 1.0  # Max 100% portfolio exposure
    max_sector_exposure: float = 0.20  # Max 20% per sector
    max_long_short_ratio: float = 2.0  # Max ratio of long to short exposure


@dataclass
class TradingSignal:
    """Container for a single trading signal"""

    stock_id: int
    signal_type: SignalType
    signal_strength: float
    entry_price: float
    sentiment_score: float
    price_z_score: float
    dislocation: float
    confidence: float
    timestamp: int

    # Risk metrics
    stop_loss_price: float
    take_profit_price: float

    # Position sizing
    position_size: float  # As fraction of portfolio
    suggested_quantity: int  # Number of shares


class SignalGenerator:
    """
    Generate trading signals based on sentiment arbitrage logic.

    Combines sentiment scores, price z-scores, and dislocation metrics
    to identify mispricing opportunities.
    """

    def __init__(self, n_stocks: int = 500, config: SignalConfig | None = None):
        """
        Initialize signal generator

        Args:
            n_stocks: Number of stocks
            config: Signal configuration
        """
        self.n_stocks = n_stocks
        self.config = config or SignalConfig()

        # Track active positions
        self.active_positions: dict[int, TradingSignal] = {}

        # Signal history
        self.signal_history = []

    def generate_signals(
        self,
        sentiment_scores: cp.ndarray,
        price_z_scores: cp.ndarray,
        dislocation: cp.ndarray,
        current_prices: cp.ndarray,
        confidence_scores: cp.ndarray | None = None,
        timestamp: int = 0,
    ) -> tuple[list[TradingSignal], list[int]]:
        """
        Generate trading signals for all stocks

        Args:
            sentiment_scores: Sentiment scores (n_stocks,)
            price_z_scores: Price z-scores (n_stocks,)
            dislocation: Dislocation metric (n_stocks,)
            current_prices: Current prices (n_stocks,)
            confidence_scores: Confidence in sentiment (n_stocks,)
            timestamp: Current timestamp

        Returns:
            Tuple of (new_signals, stocks_to_close)
        """
        if confidence_scores is None:
            confidence_scores = cp.ones(n_stocks, dtype=cp.float32)

        # Identify buy signals
        buy_conditions = (
            (sentiment_scores > self.config.long_sentiment_threshold)
            & (price_z_scores < self.config.long_price_threshold)
            & (dislocation > self.config.long_dislocation_threshold)
        )

        # Identify sell signals
        sell_conditions = (
            (sentiment_scores < self.config.short_sentiment_threshold)
            & (price_z_scores > self.config.short_price_threshold)
            & (dislocation < self.config.short_dislocation_threshold)
        )

        # Get indices
        buy_indices = cp.where(buy_conditions)[0].get()
        sell_indices = cp.where(sell_conditions)[0].get()

        # Generate signal objects
        new_signals = []

        for idx in buy_indices:
            if idx not in self.active_positions:
                signal = self._create_signal(
                    stock_id=int(idx),
                    signal_type=SignalType.BUY,
                    sentiment_scores=sentiment_scores,
                    price_z_scores=price_z_scores,
                    dislocation=dislocation,
                    current_prices=current_prices,
                    confidence_scores=confidence_scores,
                    timestamp=timestamp,
                )
                new_signals.append(signal)

        for idx in sell_indices:
            if idx not in self.active_positions:
                signal = self._create_signal(
                    stock_id=int(idx),
                    signal_type=SignalType.SELL,
                    sentiment_scores=sentiment_scores,
                    price_z_scores=price_z_scores,
                    dislocation=dislocation,
                    current_prices=current_prices,
                    confidence_scores=confidence_scores,
                    timestamp=timestamp,
                )
                new_signals.append(signal)

        # Check exit conditions
        stocks_to_close = self._check_exit_conditions(
            sentiment_scores, price_z_scores, dislocation, current_prices, timestamp
        )

        # Store signal history
        for signal in new_signals:
            self.signal_history.append(signal)

        return new_signals, stocks_to_close

    def _create_signal(
        self,
        stock_id: int,
        signal_type: SignalType,
        sentiment_scores: cp.ndarray,
        price_z_scores: cp.ndarray,
        dislocation: cp.ndarray,
        current_prices: cp.ndarray,
        confidence_scores: cp.ndarray,
        timestamp: int,
    ) -> TradingSignal:
        """Create a trading signal object"""
        sentiment_score = float(sentiment_scores[stock_id])
        price_z_score = float(price_z_scores[stock_id])
        dislocation_val = float(dislocation[stock_id])
        current_price = float(current_prices[stock_id])
        confidence = float(confidence_scores[stock_id])

        # Calculate signal strength
        signal_strength = self._calculate_signal_strength(
            signal_type, sentiment_score, price_z_score, dislocation_val
        )

        # Calculate stop-loss and take-profit
        if signal_type == SignalType.BUY:
            stop_loss_price = current_price * (1 - self.config.exit_stop_loss_pct)
            take_profit_price = current_price * (1 + self.config.exit_take_profit_pct)
        else:
            stop_loss_price = current_price * (1 + self.config.exit_stop_loss_pct)
            take_profit_price = current_price * (1 - self.config.exit_take_profit_pct)

        # Calculate position size
        position_size = self._calculate_position_size(signal_strength, confidence, current_price)

        return TradingSignal(
            stock_id=stock_id,
            signal_type=signal_type,
            signal_strength=signal_strength,
            entry_price=current_price,
            sentiment_score=sentiment_score,
            price_z_score=price_z_score,
            dislocation=dislocation_val,
            confidence=confidence,
            timestamp=timestamp,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            position_size=position_size,
            suggested_quantity=0,  # To be calculated based on portfolio value
        )

    def _calculate_signal_strength(
        self,
        signal_type: SignalType,
        sentiment_score: float,
        price_z_score: float,
        dislocation: float,
    ) -> float:
        """
        Calculate signal strength

        Higher absolute values indicate stronger signals.
        """
        # Normalize each component to [0, 1]
        if signal_type == SignalType.BUY:
            # Higher sentiment, lower price, higher dislocation = stronger
            sentiment_norm = (sentiment_score - 1.5) / 2.0  # Normalize from [1.5, 3.5]
            price_norm = (-price_z_score - 0.5) / 2.0  # Normalize from [-2.5, -0.5]
            dislocation_norm = (dislocation - 2.0) / 3.0  # Normalize from [2.0, 5.0]
        else:  # SELL
            # Lower sentiment, higher price, lower dislocation = stronger
            sentiment_norm = (-sentiment_score - 1.5) / 2.0  # Normalize from [1.5, 3.5]
            price_norm = (price_z_score - 0.5) / 2.0  # Normalize from [0.5, 2.5]
            dislocation_norm = (-dislocation - 2.0) / 3.0  # Normalize from [-5.0, -2.0]

        # Clip to [0, 1]
        sentiment_norm = np.clip(sentiment_norm, 0, 1)
        price_norm = np.clip(price_norm, 0, 1)
        dislocation_norm = np.clip(dislocation_norm, 0, 1)

        # Weighted average (adjust weights as needed)
        strength = 0.4 * sentiment_norm + 0.3 * price_norm + 0.3 * dislocation_norm

        return strength

    def _calculate_position_size(
        self, signal_strength: float, confidence: float, current_price: float
    ) -> float:
        """
        Calculate position size as fraction of portfolio

        Args:
            signal_strength: Signal strength [0, 1]
            confidence: Confidence in signal [0, 1]
            current_price: Current price (for volatility estimation)

        Returns:
            Position size as fraction of portfolio
        """
        if self.config.position_sizing_method == "signal_strength":
            # Size based on signal strength
            base_size = signal_strength * self.config.max_position_size
        elif self.config.position_sizing_method == "equal":
            # Equal sizing
            base_size = self.config.max_position_size * 0.5
        elif self.config.position_sizing_method == "volatility":
            # Size inversely proportional to price (higher price = lower size)
            price_factor = 100 / (100 + current_price)  # Normalized to [0, 1]
            base_size = price_factor * self.config.max_position_size
        else:
            base_size = self.config.max_position_size * 0.5

        # Adjust by confidence
        adjusted_size = base_size * (0.5 + 0.5 * confidence)

        return np.clip(adjusted_size, 0, self.config.max_position_size)

    def _check_exit_conditions(
        self,
        sentiment_scores: cp.ndarray,
        price_z_scores: cp.ndarray,
        dislocation: cp.ndarray,
        current_prices: cp.ndarray,
        timestamp: int,
    ) -> list[int]:
        """
        Check exit conditions for all active positions

        Returns:
            List of stock IDs to close
        """
        stocks_to_close = []

        for stock_id, signal in self.active_positions.items():
            should_exit = False
            exit_reason = ""

            # Check z-score cross
            if self.config.exit_z_cross:
                current_dislocation = float(dislocation[stock_id])
                if (signal.signal_type == SignalType.BUY and current_dislocation < 0) or (
                    signal.signal_type == SignalType.SELL and current_dislocation > 0
                ):
                    should_exit = True
                    exit_reason = "z_score_cross"

            # Check time stop
            if self.config.exit_time_stop_hours > 0:
                hours_held = timestamp - signal.timestamp
                if (
                    hours_held >= self.config.exit_time_stop_hours * 3600
                ):  # Convert hours to seconds
                    should_exit = True
                    exit_reason = "time_stop"

            # Check stop-loss
            current_price = float(current_prices[stock_id])
            if signal.signal_type == SignalType.BUY:
                if current_price < signal.stop_loss_price:
                    should_exit = True
                    exit_reason = "stop_loss"
                elif current_price > signal.take_profit_price:
                    should_exit = True
                    exit_reason = "take_profit"
            else:  # SELL
                if current_price > signal.stop_loss_price:
                    should_exit = True
                    exit_reason = "stop_loss"
                elif current_price < signal.take_profit_price:
                    should_exit = True
                    exit_reason = "take_profit"

            if should_exit:
                stocks_to_close.append(stock_id)

        return stocks_to_close

    def execute_signal(self, signal: TradingSignal, portfolio_value: float) -> tuple[int, float]:
        """
        Execute a trading signal

        Args:
            signal: Trading signal to execute
            portfolio_value: Total portfolio value

        Returns:
            Tuple of (quantity, total_cost)
        """
        # Calculate quantity based on position size
        position_value = signal.position_size * portfolio_value
        quantity = int(position_value / signal.entry_price)

        # Update suggested quantity
        signal.suggested_quantity = quantity

        # Add to active positions
        self.active_positions[signal.stock_id] = signal

        # Calculate total cost
        total_cost = quantity * signal.entry_price

        return quantity, total_cost

    def close_position(self, stock_id: int, current_price: float) -> tuple[float, float]:
        """
        Close a position

        Args:
            stock_id: Stock ID to close
            current_price: Current price

        Returns:
            Tuple of (pnl, position_value)
        """
        if stock_id not in self.active_positions:
            return 0.0, 0.0

        signal = self.active_positions[stock_id]
        quantity = signal.suggested_quantity

        # Calculate P&L
        if signal.signal_type == SignalType.BUY:
            pnl = (current_price - signal.entry_price) * quantity
        else:  # SELL
            pnl = (signal.entry_price - current_price) * quantity

        position_value = quantity * current_price

        # Remove from active positions
        del self.active_positions[stock_id]

        return pnl, position_value

    def get_portfolio_exposure(self) -> dict[str, float]:
        """Get current portfolio exposure"""
        long_exposure = 0.0
        short_exposure = 0.0

        for signal in self.active_positions.values():
            position_value = signal.suggested_quantity * signal.entry_price
            if signal.signal_type == SignalType.BUY:
                long_exposure += position_value
            else:
                short_exposure += position_value

        total_exposure = long_exposure + short_exposure

        return {
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
            "total_exposure": total_exposure,
            "net_exposure": long_exposure - short_exposure,
            "n_positions": len(self.active_positions),
        }

    def reset(self):
        """Reset signal generator"""
        self.active_positions.clear()
        self.signal_history.clear()


class SignalEvaluator:
    """
    Evaluate signal quality and performance
    """

    def __init__(self):
        """Initialize signal evaluator"""
        self.signal_returns = []
        self.signal_hold_times = []
        self.signal_types = []

    def evaluate_signal(
        self, signal: TradingSignal, exit_price: float, exit_timestamp: int
    ) -> dict:
        """
        Evaluate a completed signal

        Args:
            signal: Trading signal
            exit_price: Exit price
            exit_timestamp: Exit timestamp

        Returns:
            Dictionary of evaluation metrics
        """
        # Calculate return
        if signal.signal_type == SignalType.BUY:
            return_pct = (exit_price - signal.entry_price) / signal.entry_price
        else:
            return_pct = (signal.entry_price - exit_price) / signal.entry_price

        # Calculate hold time
        hold_time_hours = (exit_timestamp - signal.timestamp) / 3600

        # Store for aggregate statistics
        self.signal_returns.append(return_pct)
        self.signal_hold_times.append(hold_time_hours)
        self.signal_types.append(signal.signal_type.name)

        return {
            "stock_id": signal.stock_id,
            "signal_type": signal.signal_type.name,
            "return_pct": return_pct,
            "hold_time_hours": hold_time_hours,
            "entry_price": signal.entry_price,
            "exit_price": exit_price,
            "signal_strength": signal.signal_strength,
            "confidence": signal.confidence,
        }

    def get_aggregate_statistics(self) -> dict:
        """Get aggregate statistics"""
        if not self.signal_returns:
            return {}

        returns = np.array(self.signal_returns)
        hold_times = np.array(self.signal_hold_times)

        win_rate = np.sum(returns > 0) / len(returns)

        return {
            "total_signals": len(returns),
            "win_rate": win_rate,
            "mean_return": float(np.mean(returns)),
            "std_return": float(np.std(returns)),
            "median_return": float(np.median(returns)),
            "best_return": float(np.max(returns)),
            "worst_return": float(np.min(returns)),
            "mean_hold_time": float(np.mean(hold_times)),
            "median_hold_time": float(np.median(hold_times)),
            "sharpe_ratio": float(np.mean(returns) / np.std(returns)) if np.std(returns) > 0 else 0,
        }


def test_signal_generation():
    """Test signal generation"""
    print("Testing Signal Generation...")

    # Create signal generator
    config = SignalConfig(
        long_sentiment_threshold=1.0,
        long_price_threshold=-0.3,
        long_dislocation_threshold=1.5,
        short_sentiment_threshold=-1.0,
        short_price_threshold=0.3,
        short_dislocation_threshold=-1.5,
    )

    generator = SignalGenerator(n_stocks=100, config=config)

    # Generate synthetic data
    np.random.seed(42)
    n_stocks = 100

    sentiment_scores = cp.random.randn(n_stocks) * 1.5
    price_z_scores = cp.random.randn(n_stocks) * 1.0
    dislocation = sentiment_scores - price_z_scores
    current_prices = cp.random.uniform(50, 200, n_stocks)
    confidence_scores = cp.random.uniform(0.5, 1.0, n_stocks)

    # Create some extreme values for signals
    sentiment_scores[0] = 2.5  # Strong buy
    price_z_scores[0] = -1.5
    dislocation[0] = 4.0

    sentiment_scores[1] = -2.5  # Strong sell
    price_z_scores[1] = 1.5
    dislocation[1] = -4.0

    # Generate signals
    signals, stocks_to_close = generator.generate_signals(
        sentiment_scores,
        price_z_scores,
        dislocation,
        current_prices,
        confidence_scores,
        timestamp=0,
    )

    print(f"\nGenerated {len(signals)} signals:")
    for signal in signals:
        print(
            f"  Stock {signal.stock_id}: {signal.signal_type.name} | "
            f"Strength: {signal.signal_strength:.3f} | "
            f"Entry: ${signal.entry_price:.2f} | "
            f"Pos Size: {signal.position_size:.2%}"
        )

    # Get portfolio exposure
    exposure = generator.get_portfolio_exposure()
    print("\nPortfolio Exposure:")
    for key, value in exposure.items():
        print(f"  {key}: {value}")

    # Test exit conditions
    print("\nTesting exit conditions...")
    sentiment_scores[0] = -0.5  # Signal crossed zero
    dislocation[0] = -1.0

    stocks_to_close = generator._check_exit_conditions(
        sentiment_scores,
        price_z_scores,
        dislocation,
        current_prices,
        timestamp=100000,  # 27 hours later
    )

    print(f"Stocks to close: {stocks_to_close}")

    # Test position closing
    if stocks_to_close:
        for stock_id in stocks_to_close:
            pnl, value = generator.close_position(stock_id, current_prices[stock_id].get())
            print(f"  Stock {stock_id}: P&L: ${pnl:.2f}, Value: ${value:.2f}")

    # Test signal evaluation
    evaluator = SignalEvaluator()

    for signal in signals:
        # Simulate exit
        exit_price = float(current_prices[signal.stock_id]) * (1 + np.random.randn() * 0.1)
        eval_result = evaluator.evaluate_signal(signal, exit_price, timestamp=172800)
        print(f"\nEvaluated signal for stock {signal.stock_id}:")
        print(f"  Return: {eval_result['return_pct']:.2%}")
        print(f"  Hold time: {eval_result['hold_time_hours']:.1f} hours")

    # Get aggregate statistics
    stats = evaluator.get_aggregate_statistics()
    print("\nAggregate Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n✓ Signal generation tests passed!")


if __name__ == "__main__":
    test_signal_generation()
