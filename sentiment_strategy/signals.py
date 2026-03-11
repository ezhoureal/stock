"""
Signals Module - Chinese Stock Sentiment Trading System

Generates trading signals by combining sentiment and valuation data.
Implements contrarian strategy: buy on pessimism + undervaluation,
sell on euphoria + overvaluation.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Literal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json

from valuation import ValuationCalculator, ValuationScore, ValuationConfig
from sentiment import SentimentAnalyzer, SentimentResult, SentimentConfig


@dataclass
class SignalConfig:
    """Configuration for signal generation"""
    # Sentiment thresholds
    sentiment_threshold: float = 1.5        # |S| > 1.5 for signal
    roc_threshold: float = 1.0             # |S_roc| > 1.0 for rapid change signal
    min_deviation_std: float = 1.5         # Min std devs from 30-day mean

    # Valuation thresholds
    undervalued_threshold: float = 0.10    # V > 0.10 for undervalued
    overvalued_threshold: float = -0.10    # V < -0.10 for overvalued

    # Confirmation requirements
    confirmation_periods: int = 2          # Signal must persist for N periods

    # Exit conditions
    stop_loss_pct: float = 0.08           # 8% stop-loss
    take_profit_pct: float = 0.15         # 15% take-profit

    # Sentiment reversal thresholds
    sentiment_reversal_threshold: float = 1.0  # Exit if sentiment reverses this much
    valuation_reversal_threshold: float = 0.05  # Exit if valuation reverses this much

    # Position sizing
    base_position_size: float = 0.01      # 1% of portfolio
    max_position_size: float = 0.05        # 5% max per position

    # Signal strength calculation weights
    sentiment_weight: float = 0.5
    valuation_weight: float = 0.5


@dataclass
class TradingSignal:
    """A trading signal for a stock"""
    symbol: str
    timestamp: datetime
    signal_type: Literal['BUY', 'SELL', 'HOLD', 'EXIT_LONG', 'EXIT_SHORT']
    strength: float              # 0-100
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 0.0       # Overall confidence [0, 1]
    sentiment_score: float = 0.0
    valuation_score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class Position:
    """Active position tracking"""
    symbol: str
    entry_type: Literal['BUY', 'SELL']
    entry_price: float
    entry_date: datetime
    quantity: float
    stop_loss: float
    take_profit: float
    original_signal_strength: float


class SignalGenerator:
    """
    Generates trading signals by combining sentiment and valuation data.

    Strategy: Contrarian
    - BUY: Sentiment bearish + Fundamentals undervalued
    - SELL: Sentiment bullish + Fundamentals overvalued
    """

    def __init__(
        self,
        sentiment_analyzer: SentimentAnalyzer,
        valuation_calculator: ValuationCalculator,
        config: Optional[SignalConfig] = None
    ):
        """
        Initialize the signal generator.

        Args:
            sentiment_analyzer: SentimentAnalyzer instance
            valuation_calculator: ValuationCalculator instance
            config: Signal configuration (uses defaults if None)
        """
        self.sentiment_analyzer = sentiment_analyzer
        self.valuation_calculator = valuation_calculator
        self.config = config or SignalConfig()

        # Track signal history for confirmation
        self._signal_history: Dict[str, List[TradingSignal]] = {}
        # Track active positions
        self._positions: Dict[str, Position] = {}

    def calculate_buy_strength(
        self,
        sentiment_score: float,
        valuation_score: float
    ) -> float:
        """
        Calculate buy signal strength (0-100).

        buy_strength = (
            (max(-S, 0) / 3.5) * sentiment_weight +
            (min(V, 0.5) / 0.5) * valuation_weight
        ) * 100

        Args:
            sentiment_score: Sentiment score (negative for bearish)
            valuation_score: Valuation score (positive for undervalued)

        Returns:
            Strength 0-100
        """
        # Sentiment contribution (more negative = stronger)
        sentiment_contrib = max(-sentiment_score, 0) / 3.5

        # Valuation contribution (more positive = stronger)
        valuation_contrib = min(valuation_score, 0.5) / 0.5

        # Combine with weights
        strength = (
            sentiment_contrib * self.config.sentiment_weight +
            valuation_contrib * self.config.valuation_weight
        ) * 100

        return np.clip(strength, 0, 100)

    def calculate_sell_strength(
        self,
        sentiment_score: float,
        valuation_score: float
    ) -> float:
        """
        Calculate sell signal strength (0-100).

        sell_strength = (
            (max(S, 0) / 3.5) * sentiment_weight +
            (min(-V, 0.5) / 0.5) * valuation_weight
        ) * 100

        Args:
            sentiment_score: Sentiment score (positive for bullish)
            valuation_score: Valuation score (negative for overvalued)

        Returns:
            Strength 0-100
        """
        # Sentiment contribution (more positive = stronger)
        sentiment_contrib = max(sentiment_score, 0) / 3.5

        # Valuation contribution (more negative = stronger)
        valuation_contrib = min(-valuation_score, 0.5) / 0.5

        # Combine with weights
        strength = (
            sentiment_contrib * self.config.sentiment_weight +
            valuation_contrib * self.config.valuation_weight
        ) * 100

        return np.clip(strength, 0, 100)

    def check_buy_conditions(
        self,
        sentiment: SentimentResult,
        valuation: ValuationScore,
        current_price: float
    ) -> Tuple[bool, List[str]]:
        """
        Check if buy conditions are met.

        Conditions (ALL must be true):
        1. Sentiment is bearish or rapidly deteriorating
        2. Fundamentals are undervalued
        3. Minimum deviation thresholds met

        Args:
            sentiment: Sentiment analysis result
            valuation: Valuation score
            current_price: Current stock price

        Returns:
            (is_signal, list of reasons)
        """
        reasons = []
        is_signal = True

        # Condition 1: Sentiment bearish or rapidly deteriorating
        if sentiment.smoothed_score < -self.config.sentiment_threshold:
            reasons.append(f"Sentiment bearish: {sentiment.smoothed_score:.2f}")
        elif sentiment.roc < -self.config.roc_threshold:
            reasons.append(f"Sentiment rapidly deteriorating: ROC {sentiment.roc:.2f}")
        else:
            is_signal = False
            reasons.append("Sentiment not bearish enough")

        # Condition 2: Fundamentals undervalued
        if valuation.composite_score > self.config.undervalued_threshold:
            reasons.append(f"Undervalued: V={valuation.composite_score:.3f} ({valuation.interpretation})")
        elif valuation.composite_score > 0 and valuation.trend and valuation.trend > 0:
            reasons.append(f"Approaching undervaluation: V={valuation.composite_score:.3f}, trend={valuation.trend:.3f}")
        else:
            is_signal = False
            reasons.append("Not undervalued")

        # Condition 3: Minimum deviation from mean
        is_extreme, z_score = self.sentiment_analyzer.is_sentiment_extreme(
            sentiment.symbol,
            self.config.min_deviation_std
        )
        if is_extreme:
            reasons.append(f"Sentiment extreme: {z_score:.2f} std devs from mean")
        else:
            is_signal = False
            reasons.append(f"Sentiment not extreme enough: {z_score:.2f} < {self.config.min_deviation_std}")

        return is_signal, reasons

    def check_sell_conditions(
        self,
        sentiment: SentimentResult,
        valuation: ValuationScore,
        current_price: float
    ) -> Tuple[bool, List[str]]:
        """
        Check if sell conditions are met.

        Conditions (ALL must be true):
        1. Sentiment is bullish or rapidly improving
        2. Fundamentals are overvalued
        3. Minimum deviation thresholds met

        Args:
            sentiment: Sentiment analysis result
            valuation: Valuation score
            current_price: Current stock price

        Returns:
            (is_signal, list of reasons)
        """
        reasons = []
        is_signal = True

        # Condition 1: Sentiment bullish or rapidly improving
        if sentiment.smoothed_score > self.config.sentiment_threshold:
            reasons.append(f"Sentiment bullish: {sentiment.smoothed_score:.2f}")
        elif sentiment.roc > self.config.roc_threshold:
            reasons.append(f"Sentiment rapidly improving: ROC {sentiment.roc:.2f}")
        else:
            is_signal = False
            reasons.append("Sentiment not bullish enough")

        # Condition 2: Fundamentals overvalued
        if valuation.composite_score < self.config.overvalued_threshold:
            reasons.append(f"Overvalued: V={valuation.composite_score:.3f} ({valuation.interpretation})")
        elif valuation.composite_score < 0 and valuation.trend and valuation.trend < 0:
            reasons.append(f"Approaching overvaluation: V={valuation.composite_score:.3f}, trend={valuation.trend:.3f}")
        else:
            is_signal = False
            reasons.append("Not overvalued")

        # Condition 3: Minimum deviation from mean
        is_extreme, z_score = self.sentiment_analyzer.is_sentiment_extreme(
            sentiment.symbol,
            self.config.min_deviation_std
        )
        if is_extreme:
            reasons.append(f"Sentiment extreme: {z_score:.2f} std devs from mean")
        else:
            is_signal = False
            reasons.append(f"Sentiment not extreme enough: {z_score:.2f} < {self.config.min_deviation_std}")

        return is_signal, reasons

    def check_confirmation(self, symbol: str, signal_type: str) -> bool:
        """
        Check if signal persists for required confirmation periods.

        Args:
            symbol: Stock symbol
            signal_type: 'BUY' or 'SELL'

        Returns:
            True if confirmed
        """
        if symbol not in self._signal_history:
            return False

        history = self._signal_history[symbol]
        required = self.config.confirmation_periods

        # Count recent signals of same type
        recent_signals = [s for s in history[-required:] if s.signal_type == signal_type]

        return len(recent_signals) >= required

    def check_exit_conditions(
        self,
        position: Position,
        current_price: float,
        sentiment: Optional[SentimentResult] = None,
        valuation: Optional[ValuationScore] = None
    ) -> Optional[Tuple[str, List[str]]]:
        """
        Check if an active position should be exited.

        Exit conditions:
        1. Stop-loss hit
        2. Take-profit hit
        3. Signal reversal (sentiment/valuation changed)

        Args:
            position: Active position
            current_price: Current stock price
            sentiment: Current sentiment (for reversal check)
            valuation: Current valuation (for reversal check)

        Returns:
            None or (exit_type, list of reasons)
        """
        reasons = []

        # Stop-loss
        if position.entry_type == 'BUY':
            if current_price <= position.stop_loss:
                reasons.append(f"Stop-loss hit: {current_price:.2f} <= {position.stop_loss:.2f}")
                return ('EXIT_LONG', reasons)
        else:  # SELL
            if current_price >= position.stop_loss:
                reasons.append(f"Stop-loss hit: {current_price:.2f} >= {position.stop_loss:.2f}")
                return ('EXIT_SHORT', reasons)

        # Take-profit
        if position.entry_type == 'BUY':
            if current_price >= position.take_profit:
                reasons.append(f"Take-profit hit: {current_price:.2f} >= {position.take_profit:.2f}")
                return ('EXIT_LONG', reasons)
        else:  # SELL
            if current_price <= position.take_profit:
                reasons.append(f"Take-profit hit: {current_price:.2f} <= {position.take_profit:.2f}")
                return ('EXIT_SHORT', reasons)

        # Signal reversal
        if sentiment and valuation:
            if position.entry_type == 'BUY':
                # Exit long if sentiment improved or valuation deteriorated
                if sentiment.smoothed_score > self.config.sentiment_reversal_threshold:
                    reasons.append(f"Sentiment reversal: {sentiment.smoothed_score:.2f} > {self.config.sentiment_reversal_threshold}")
                    return ('EXIT_LONG', reasons)
                if valuation.composite_score < self.config.valuation_reversal_threshold:
                    reasons.append(f"Valuation reversal: {valuation.composite_score:.3f} < {self.config.valuation_reversal_threshold}")
                    return ('EXIT_LONG', reasons)
            else:  # SELL
                # Exit short if sentiment deteriorated or valuation improved
                if sentiment.smoothed_score < -self.config.sentiment_reversal_threshold:
                    reasons.append(f"Sentiment reversal: {sentiment.smoothed_score:.2f} < -{self.config.sentiment_reversal_threshold}")
                    return ('EXIT_SHORT', reasons)
                if valuation.composite_score > self.config.valuation_reversal_threshold:
                    reasons.append(f"Valuation reversal: {valuation.composite_score:.3f} > {self.config.valuation_reversal_threshold}")
                    return ('EXIT_SHORT', reasons)

        return None

    def calculate_position_size(
        self,
        signal_strength: float,
        portfolio_value: float,
        current_price: float
    ) -> float:
        """
        Calculate position size based on signal strength.

        size = base_size * (strength / 50) * (1 + strength_factor)
        Then clip to max_position_size

        Args:
            signal_strength: Signal strength 0-100
            portfolio_value: Total portfolio value
            current_price: Current stock price

        Returns:
            Number of shares
        """
        # Base position as fraction of portfolio
        base_value = portfolio_value * self.config.base_position_size

        # Adjust by strength (strength/50 = 0 to 2)
        strength_factor = signal_strength / 50.0

        adjusted_value = base_value * strength_factor

        # Convert to shares
        shares = adjusted_value / current_price

        # Clip to max position size
        max_value = portfolio_value * self.config.max_position_size
        max_shares = max_value / current_price

        shares = min(shares, max_shares)

        return round(shares, 2)

    def generate_signal(
        self,
        symbol: str,
        current_price: float,
        sentiment: SentimentResult,
        valuation: ValuationScore,
        portfolio_value: float = 100000.0
    ) -> TradingSignal:
        """
        Generate a trading signal.

        Args:
            symbol: Stock symbol
            current_price: Current stock price
            sentiment: Sentiment analysis result
            valuation: Valuation score
            portfolio_value: Total portfolio value (default 100k)

        Returns:
            TradingSignal
        """
        timestamp = datetime.now()

        # Check for exit on existing position
        if symbol in self._positions:
            exit_result = self.check_exit_conditions(
                self._positions[symbol],
                current_price,
                sentiment,
                valuation
            )
            if exit_result:
                exit_type, reasons = exit_result
                signal = TradingSignal(
                    symbol=symbol,
                    timestamp=timestamp,
                    signal_type=exit_type,
                    strength=100.0,  # Exit is always max strength
                    entry_price=current_price,
                    stop_loss=None,
                    take_profit=None,
                    confidence=1.0,
                    sentiment_score=sentiment.smoothed_score,
                    valuation_score=valuation.composite_score,
                    reasons=reasons,
                    metadata={'exit_reason': exit_type}
                )
                self._record_signal(signal)
                return signal

        # Check for new signals
        buy_signal, buy_reasons = self.check_buy_conditions(
            sentiment, valuation, current_price
        )
        sell_signal, sell_reasons = self.check_sell_conditions(
            sentiment, valuation, current_price
        )

        # Determine signal type
        if buy_signal and sell_signal:
            # Both conditions met - choose stronger
            buy_strength = self.calculate_buy_strength(
                sentiment.smoothed_score, valuation.composite_score
            )
            sell_strength = self.calculate_sell_strength(
                sentiment.smoothed_score, valuation.composite_score
            )
            if buy_strength >= sell_strength:
                signal_type = 'BUY'
                reasons = buy_reasons
                strength = buy_strength
            else:
                signal_type = 'SELL'
                reasons = sell_reasons
                strength = sell_strength
        elif buy_signal:
            signal_type = 'BUY'
            reasons = buy_reasons
            strength = self.calculate_buy_strength(
                sentiment.smoothed_score, valuation.composite_score
            )
        elif sell_signal:
            signal_type = 'SELL'
            reasons = sell_reasons
            strength = self.calculate_sell_strength(
                sentiment.smoothed_score, valuation.composite_score
            )
        else:
            signal_type = 'HOLD'
            reasons = ["No clear signal"]
            strength = 0.0

        # Calculate exit levels if entry signal
        stop_loss = None
        take_profit = None

        if signal_type == 'BUY':
            stop_loss = current_price * (1 - self.config.stop_loss_pct)
            take_profit = current_price * (1 + self.config.take_profit_pct)
        elif signal_type == 'SELL':
            stop_loss = current_price * (1 + self.config.stop_loss_pct)
            take_profit = current_price * (1 - self.config.take_profit_pct)

        # Calculate position size for entry signals
        quantity = None
        if signal_type in ['BUY', 'SELL'] and strength > 20:
            quantity = self.calculate_position_size(strength, portfolio_value, current_price)

        # Calculate confidence (based on signal strength and source confidence)
        confidence = strength / 100.0
        if sentiment.confidences:
            avg_confidence = np.mean(list(sentiment.confidences.values()))
            confidence = (confidence + avg_confidence) / 2

        signal = TradingSignal(
            symbol=symbol,
            timestamp=timestamp,
            signal_type=signal_type,
            strength=strength,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            sentiment_score=sentiment.smoothed_score,
            valuation_score=valuation.composite_score,
            reasons=reasons,
            metadata={'quantity': quantity}
        )

        # Record signal
        self._record_signal(signal)

        return signal

    def _record_signal(self, signal: TradingSignal):
        """Record signal in history."""
        if signal.symbol not in self._signal_history:
            self._signal_history[signal.symbol] = []

        self._signal_history[signal.symbol].append(signal)

        # Keep only last 100 signals
        if len(self._signal_history[signal.symbol]) > 100:
            self._signal_history[signal.symbol] = self._signal_history[signal.symbol][-100:]

    def add_position(self, position: Position):
        """Add a position to track."""
        self._positions[position.symbol] = position

    def remove_position(self, symbol: str):
        """Remove a position."""
        if symbol in self._positions:
            del self._positions[symbol]

    def get_positions(self) -> Dict[str, Position]:
        """Get all active positions."""
        return self._positions.copy()

    def get_signal_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 10
    ) -> List[TradingSignal]:
        """Get signal history."""
        if symbol:
            history = self._signal_history.get(symbol, [])
        else:
            # Flatten all signals
            history = []
            for sig_list in self._signal_history.values():
                history.extend(sig_list)

        # Sort by timestamp (most recent first)
        history = sorted(history, key=lambda x: x.timestamp, reverse=True)

        return history[:limit]


def load_config(config_path: str) -> SignalConfig:
    """
    Load signal configuration from JSON file.

    Args:
        config_path: Path to config JSON file

    Returns:
        SignalConfig instance
    """
    with open(config_path, 'r') as f:
        config_dict = json.load(f)

    return SignalConfig(**config_dict)


# Example usage and testing
if __name__ == "__main__":
    # Initialize components
    from sentiment import SentimentAnalyzer, SentimentSource
    from valuation import ValuationCalculator, ValuationMetrics, SectorMetrics

    sentiment_analyzer = SentimentAnalyzer()
    valuation_calculator = ValuationCalculator()
    signal_generator = SignalGenerator(sentiment_analyzer, valuation_calculator)

    # Create example sentiment (bearish)
    bearish_sources = [
        SentimentSource('news', datetime.now(), -0.4, -0.4, 0.8, {}),
        SentimentSource('social', datetime.now(), -0.6, -0.6, 0.7, {}),
        SentimentSource('search', datetime.now(), -0.7, -0.7, 0.6, {}),
        SentimentSource('forum', datetime.now(), -0.5, -0.5, 0.5, {}),
    ]
    sentiment = sentiment_analyzer.calculate_sentiment("600519.SH", bearish_sources)

    # Create example valuation (undervalued)
    company = ValuationMetrics(
        pe_ratio=15.0, pb_ratio=2.5, dividend_yield=0.02, peg_ratio=1.2,
        eps=2.0, book_value_per_share=8.0, annual_dividend=0.4
    )
    sector = SectorMetrics(pe_ratio=25.0, pb_ratio=2.5, dividend_yield=0.015, peg_ratio=1.8)
    valuation = valuation_calculator.calculate_valuation(company, sector)

    # Generate signal
    signal = signal_generator.generate_signal(
        symbol="600519.SH",
        current_price=100.0,
        sentiment=sentiment,
        valuation=valuation,
        portfolio_value=100000.0
    )

    print("=== Trading Signal ===")
    print(f"Symbol: {signal.symbol}")
    print(f"Type: {signal.signal_type}")
    print(f"Strength: {signal.strength:.1f}")
    print(f"Confidence: {signal.confidence:.2f}")
    print(f"Entry Price: ¥{signal.entry_price:.2f}")
    print(f"Stop Loss: ¥{signal.stop_loss:.2f}")
    print(f"Take Profit: ¥{signal.take_profit:.2f}")
    if signal.metadata.get('quantity'):
        print(f"Quantity: {signal.metadata['quantity']} shares")
    print(f"\nSentiment Score: {signal.sentiment_score:.2f}")
    print(f"Valuation Score: {signal.valuation_score:.3f}")
    print(f"\nReasons:")
    for reason in signal.reasons:
        print(f"  - {reason}")
