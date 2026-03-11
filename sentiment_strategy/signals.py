"""
Signals Module - Chinese Stock Sentiment Trading System

Generates trading signals by combining sentiment and valuation data.
Implements contrarian strategy: buy on pessimism + undervaluation,
sell on euphoria + overvaluation.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from common.interfaces import DataProvider
from common.interfaces import SignalGenerator as BaseSignalGenerator
from common.types import Position, SignalType
from common.types import TradingSignal as CommonTradingSignal

from .sentiment import SentimentAnalyzer, SentimentResult
from .valuation import ValuationCalculator, ValuationScore


@dataclass
class SignalConfig:
    """Configuration for signal generation"""

    # Sentiment thresholds
    sentiment_threshold: float = 1.5  # |S| > 1.5 for signal
    roc_threshold: float = 1.0  # |S_roc| > 1.0 for rapid change signal
    min_deviation_std: float = 1.5  # Min std devs from 30-day mean

    # Valuation thresholds
    undervalued_threshold: float = 0.10  # V > 0.10 for undervalued
    overvalued_threshold: float = -0.10  # V < -0.10 for overvalued

    # Confirmation requirements
    confirmation_periods: int = 2  # Signal must persist for N periods

    # Exit conditions
    stop_loss_pct: float = 0.08  # 8% stop-loss
    take_profit_pct: float = 0.15  # 15% take-profit

    # Sentiment reversal thresholds
    sentiment_reversal_threshold: float = 1.0  # Exit if sentiment reverses this much
    valuation_reversal_threshold: float = 0.05  # Exit if valuation reverses this much

    # Position sizing
    base_position_size: float = 0.01  # 1% of portfolio
    max_position_size: float = 0.05  # 5% max per position

    # Signal strength calculation weights
    sentiment_weight: float = 0.5
    valuation_weight: float = 0.5


@dataclass
class InternalPosition:
    """
    Internal position tracking for the sentiment strategy.

    This is used internally by the strategy to track its own positions
    and is separate from common.types.Position which is used for
    broker/execution communication.
    """

    symbol: str
    entry_type: SignalType  # BUY or SELL
    entry_price: float
    entry_date: datetime
    quantity: float
    stop_loss: float
    take_profit: float
    original_signal_strength: float

    def to_common_position(self, current_price: float) -> Position:
        """Convert to common.types.Position for interoperability."""
        side = "long" if self.entry_type == SignalType.BUY else "short"
        unrealized_pnl = 0.0
        if side == "long":
            unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            unrealized_pnl = (self.entry_price - current_price) * abs(self.quantity)

        return Position(
            symbol=self.symbol,
            side=side,
            quantity=self.quantity,
            entry_price=self.entry_price,
            entry_time=self.entry_date,
            current_price=current_price,
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            unrealized_pnl=unrealized_pnl,
            source_signal="sentiment_strategy",
        )


class SignalGenerator(BaseSignalGenerator):
    """
    Generates trading signals by combining sentiment and valuation data.

    Strategy: Contrarian
    - BUY: Sentiment bearish + Fundamentals undervalued
    - SELL: Sentiment bullish + Fundamentals overvalued

    Implements common.interfaces.SignalGenerator for compatibility
    with the TradingSystem and backtest engine.
    """

    # =========================================================================
    # Signal Strength Calculation Constants
    # =========================================================================

    # Maximum sentiment score for strength calculation scaling.
    # The sentiment score ranges from -5 (extreme bearish) to +5 (extreme bullish).
    # Using 3.5 as the normalization factor means:
    # - A sentiment of -3.5 (bearish) contributes ~100% to buy strength
    # - A sentiment of +3.5 (bullish) contributes ~100% to sell strength
    # This threshold is slightly below the extreme threshold (3.0) to allow
    # strong signals before reaching extreme sentiment levels.
    SENTIMENT_MAX_SCALE: float = 3.5

    # Maximum valuation score cap for strength calculation.
    # Valuation scores typically range from -0.5 to +0.5 for most stocks.
    # Capping at 0.5 means:
    # - A valuation score >= 0.5 (strongly undervalued) contributes full weight
    # - A valuation score <= -0.5 (strongly overvalued) contributes full weight
    # This prevents outlier valuation scores from dominating the signal strength.
    VALUATION_MAX_CAP: float = 0.5

    def __init__(
        self,
        sentiment_analyzer: SentimentAnalyzer,
        valuation_calculator: ValuationCalculator,
        config: SignalConfig | None = None,
    ):
        """
        Initialize the signal generator.

        Args:
            sentiment_analyzer: SentimentAnalyzer instance
            valuation_calculator: ValuationCalculator instance
            config: Signal configuration (uses defaults if None)
        """
        self._sentiment_analyzer = sentiment_analyzer
        self._valuation_calculator = valuation_calculator
        self._config = config or SignalConfig()

        # Track signal history for confirmation
        self._signal_history: dict[str, list[CommonTradingSignal]] = {}
        # Track active positions (using internal position type)
        self._positions: dict[str, InternalPosition] = {}
        # Internal state for persistence
        self._internal_state: dict[str, Any] = {}

    # =========================================================================
    # BaseSignalGenerator Interface Implementation
    # =========================================================================

    @property
    def name(self) -> str:
        """Unique identifier for this strategy."""
        return "sentiment_strategy"

    @property
    def time_horizon(self) -> str:
        """Strategy time horizon: 'medium_term' for contrarian strategy."""
        return "medium_term"

    def generate_signals(
        self,
        symbols: list[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> list[CommonTradingSignal]:
        """
        Generate trading signals for given symbols.

        Implements common.interfaces.SignalGenerator.generate_signals()

        Args:
            symbols: List of stock symbols to analyze
            as_of: Current timestamp
            data_provider: Data source for fetching required data

        Returns:
            List of TradingSignal objects (from common.types)
        """
        signals = []

        # Get latest prices
        prices = data_provider.get_latest_prices(symbols)

        for symbol in symbols:
            current_price = prices.get(symbol)
            if current_price is None:
                continue

            # Get sentiment data
            sentiment_scores = data_provider.get_latest_sentiment([symbol])
            sentiment_result = sentiment_scores.get(symbol)
            if sentiment_result is None:
                continue

            # Convert SentimentScore to SentimentResult for internal processing
            sentiment = self._convert_sentiment_score(symbol, sentiment_result, as_of)

            # Get fundamentals
            fundamentals_list = data_provider.get_fundamentals([symbol], as_of)
            if not fundamentals_list:
                continue

            fundamentals = fundamentals_list[0]
            valuation = self._valuation_calculator.calculate_from_fundamentals(fundamentals)

            # Generate signal using existing logic
            signal = self._create_signal(
                symbol=symbol,
                current_price=current_price,
                sentiment=sentiment,
                valuation=valuation,
                timestamp=as_of,
            )

            if signal is not None:
                signals.append(signal)

        return signals

    def update(self, new_data: dict[str, Any]) -> None:
        """
        Update internal state with new data.

        Called when new data arrives (for real-time updates).

        Args:
            new_data: Dictionary of new data (format depends on strategy)
        """
        # Update internal state with new data
        # Can include: new sentiment scores, price updates, position changes
        if "sentiment_scores" in new_data:
            for symbol, score in new_data["sentiment_scores"].items():
                self._internal_state[f"sentiment_{symbol}"] = score

        if "positions" in new_data:
            for symbol, position_data in new_data["positions"].items():
                if position_data is None:
                    # Position closed
                    self._positions.pop(symbol, None)
                else:
                    # Position updated
                    self._positions[symbol] = position_data

    def get_state(self) -> dict[str, Any]:
        """
        Serialize internal state for persistence.

        Returns:
            Dictionary representing internal state
        """
        return {
            "config": {
                "sentiment_threshold": self._config.sentiment_threshold,
                "roc_threshold": self._config.roc_threshold,
                "min_deviation_std": self._config.min_deviation_std,
                "undervalued_threshold": self._config.undervalued_threshold,
                "overvalued_threshold": self._config.overvalued_threshold,
                "confirmation_periods": self._config.confirmation_periods,
                "stop_loss_pct": self._config.stop_loss_pct,
                "take_profit_pct": self._config.take_profit_pct,
                "sentiment_reversal_threshold": self._config.sentiment_reversal_threshold,
                "valuation_reversal_threshold": self._config.valuation_reversal_threshold,
                "base_position_size": self._config.base_position_size,
                "max_position_size": self._config.max_position_size,
                "sentiment_weight": self._config.sentiment_weight,
                "valuation_weight": self._config.valuation_weight,
            },
            "positions": {
                symbol: {
                    "entry_type": pos.entry_type.value,
                    "entry_price": pos.entry_price,
                    "entry_date": pos.entry_date.isoformat(),
                    "quantity": pos.quantity,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "original_signal_strength": pos.original_signal_strength,
                }
                for symbol, pos in self._positions.items()
            },
            "internal_state": self._internal_state.copy(),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """
        Restore internal state from serialized form.

        Args:
            state: Dictionary from get_state()
        """
        # Restore config
        if "config" in state:
            config_data = state["config"]
            self._config = SignalConfig(**config_data)

        # Restore positions
        if "positions" in state:
            self._positions = {}
            for symbol, pos_data in state["positions"].items():
                self._positions[symbol] = InternalPosition(
                    symbol=symbol,
                    entry_type=SignalType(pos_data["entry_type"]),
                    entry_price=pos_data["entry_price"],
                    entry_date=datetime.fromisoformat(pos_data["entry_date"]),
                    quantity=pos_data["quantity"],
                    stop_loss=pos_data["stop_loss"],
                    take_profit=pos_data["take_profit"],
                    original_signal_strength=pos_data["original_signal_strength"],
                )

        # Restore internal state
        if "internal_state" in state:
            self._internal_state = state["internal_state"].copy()

    def save_state(self, filepath: str) -> None:
        """
        Save the internal state to a JSON file.

        BUG-017: Persistence mechanism for state survival across restarts.

        Args:
            filepath: Path to the JSON file where state will be saved
        """
        state = self.get_state()
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)

    def load_state(self, filepath: str) -> None:
        """
        Load the internal state from a JSON file.

        BUG-017: Persistence mechanism for state survival across restarts.

        Args:
            filepath: Path to the JSON file containing saved state

        Raises:
            FileNotFoundError: If the state file does not exist
            json.JSONDecodeError: If the file is not valid JSON
        """
        with open(filepath) as f:
            state = json.load(f)
        self.set_state(state)

    def get_required_data(self) -> list[str]:
        """
        Get list of required data types for this strategy.

        Returns:
            List of data types: ["prices", "fundamentals", "sentiment"]
        """
        return ["prices", "fundamentals", "sentiment"]

    # =========================================================================
    # Internal Signal Generation Logic
    # =========================================================================

    def _convert_sentiment_score(
        self, symbol: str, sentiment_score: Any, timestamp: datetime
    ) -> SentimentResult:
        """
        Convert common.types.SentimentScore to internal SentimentResult.

        Args:
            symbol: Stock symbol
            sentiment_score: SentimentScore from data provider
            timestamp: Current timestamp

        Returns:
            SentimentResult for internal processing
        """
        from .sentiment import SentimentResult

        return SentimentResult(
            symbol=symbol,
            timestamp=timestamp,
            smoothed_score=sentiment_score.score * 3.0,  # Scale to match internal range
            roc=0.0,  # No ROC data available in snapshot
            sources={sentiment_score.source: sentiment_score.score},
            confidences={sentiment_score.source: sentiment_score.confidence},
        )

    def _create_signal(
        self,
        symbol: str,
        current_price: float,
        sentiment: SentimentResult,
        valuation: ValuationScore,
        timestamp: datetime,
        portfolio_value: float = 100000.0,
    ) -> CommonTradingSignal | None:
        """
        Create a trading signal using the strategy logic.

        Args:
            symbol: Stock symbol
            current_price: Current stock price
            sentiment: Sentiment analysis result
            valuation: Valuation score
            timestamp: Signal timestamp
            portfolio_value: Total portfolio value

        Returns:
            TradingSignal from common.types or None if no signal
        """
        # Check for exit on existing position
        if symbol in self._positions:
            exit_result = self._check_exit_conditions(
                self._positions[symbol], current_price, sentiment, valuation
            )
            if exit_result:
                exit_type, reasons = exit_result
                signal = CommonTradingSignal(
                    symbol=symbol,
                    signal_type=exit_type,
                    timestamp=timestamp,
                    source=self.name,
                    strength=100.0,  # Exit is always max strength
                    confidence=1.0,
                    entry_price=current_price,
                    stop_loss=None,
                    take_profit=None,
                    sentiment_score=sentiment.smoothed_score,
                    valuation_score=valuation.composite_score,
                    reasons=reasons,
                    metadata={"exit_reason": exit_type.value},
                )
                self._record_signal(signal)
                return signal

        # Check for new signals
        buy_signal, buy_reasons = self._check_buy_conditions(sentiment, valuation, current_price)
        sell_signal, sell_reasons = self._check_sell_conditions(sentiment, valuation, current_price)

        # Determine signal type
        if buy_signal and sell_signal:
            # Both conditions met - choose stronger
            buy_strength = self._calculate_buy_strength(
                sentiment.smoothed_score, valuation.composite_score
            )
            sell_strength = self._calculate_sell_strength(
                sentiment.smoothed_score, valuation.composite_score
            )
            if buy_strength >= sell_strength:
                signal_type = SignalType.BUY
                reasons = buy_reasons
                strength = buy_strength
            else:
                signal_type = SignalType.SELL
                reasons = sell_reasons
                strength = sell_strength
        elif buy_signal:
            signal_type = SignalType.BUY
            reasons = buy_reasons
            strength = self._calculate_buy_strength(
                sentiment.smoothed_score, valuation.composite_score
            )
        elif sell_signal:
            signal_type = SignalType.SELL
            reasons = sell_reasons
            strength = self._calculate_sell_strength(
                sentiment.smoothed_score, valuation.composite_score
            )
        else:
            signal_type = SignalType.HOLD
            reasons = ["No clear signal"]
            strength = 0.0

        # Calculate exit levels if entry signal
        stop_loss = None
        take_profit = None

        if signal_type == SignalType.BUY:
            stop_loss = current_price * (1 - self._config.stop_loss_pct)
            take_profit = current_price * (1 + self._config.take_profit_pct)
        elif signal_type == SignalType.SELL:
            stop_loss = current_price * (1 + self._config.stop_loss_pct)
            take_profit = current_price * (1 - self._config.take_profit_pct)

        # Calculate position size for entry signals
        quantity = None
        position_size = None
        if signal_type in [SignalType.BUY, SignalType.SELL] and strength > 20:
            quantity = self._calculate_position_size(strength, portfolio_value, current_price)
            position_size = (quantity * current_price) / portfolio_value

        # Calculate confidence (based on signal strength and source confidence)
        confidence = strength / 100.0
        if sentiment.confidences:
            avg_confidence = np.mean(list(sentiment.confidences.values()))
            confidence = (confidence + avg_confidence) / 2

        signal = CommonTradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            timestamp=timestamp,
            source=self.name,
            strength=strength,
            confidence=confidence,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            quantity=int(quantity) if quantity else None,
            sentiment_score=sentiment.smoothed_score,
            valuation_score=valuation.composite_score,
            reasons=reasons,
            metadata={},
        )

        # Record signal
        self._record_signal(signal)

        return signal

    def _calculate_buy_strength(self, sentiment_score: float, valuation_score: float) -> float:
        """
        Calculate buy signal strength (0-100).

        buy_strength = (
            (max(-S, 0) / SENTIMENT_MAX_SCALE) * sentiment_weight +
            (min(V, VALUATION_MAX_CAP) / VALUATION_MAX_CAP) * valuation_weight
        ) * 100

        Args:
            sentiment_score: Sentiment score (negative for bearish)
            valuation_score: Valuation score (positive for undervalued)

        Returns:
            Strength 0-100
        """
        # Sentiment contribution (more negative = stronger)
        sentiment_contrib = max(-sentiment_score, 0) / self.SENTIMENT_MAX_SCALE

        # Valuation contribution (more positive = stronger)
        valuation_contrib = min(valuation_score, self.VALUATION_MAX_CAP) / self.VALUATION_MAX_CAP

        # Combine with weights
        strength = (
            sentiment_contrib * self._config.sentiment_weight
            + valuation_contrib * self._config.valuation_weight
        ) * 100

        return float(np.clip(strength, 0, 100))

    def _calculate_sell_strength(self, sentiment_score: float, valuation_score: float) -> float:
        """
        Calculate sell signal strength (0-100).

        sell_strength = (
            (max(S, 0) / SENTIMENT_MAX_SCALE) * sentiment_weight +
            (min(-V, VALUATION_MAX_CAP) / VALUATION_MAX_CAP) * valuation_weight
        ) * 100

        Args:
            sentiment_score: Sentiment score (positive for bullish)
            valuation_score: Valuation score (negative for overvalued)

        Returns:
            Strength 0-100
        """
        # Sentiment contribution (more positive = stronger)
        sentiment_contrib = max(sentiment_score, 0) / self.SENTIMENT_MAX_SCALE

        # Valuation contribution (more negative = stronger)
        valuation_contrib = min(-valuation_score, self.VALUATION_MAX_CAP) / self.VALUATION_MAX_CAP

        # Combine with weights
        strength = (
            sentiment_contrib * self._config.sentiment_weight
            + valuation_contrib * self._config.valuation_weight
        ) * 100

        return float(np.clip(strength, 0, 100))

    def _check_buy_conditions(
        self, sentiment: SentimentResult, valuation: ValuationScore, current_price: float
    ) -> tuple[bool, list[str]]:
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
        if sentiment.smoothed_score < -self._config.sentiment_threshold:
            reasons.append(f"Sentiment bearish: {sentiment.smoothed_score:.2f}")
        elif sentiment.roc < -self._config.roc_threshold:
            reasons.append(f"Sentiment rapidly deteriorating: ROC {sentiment.roc:.2f}")
        else:
            is_signal = False
            reasons.append("Sentiment not bearish enough")

        # Condition 2: Fundamentals undervalued
        if valuation.composite_score > self._config.undervalued_threshold:
            reasons.append(
                f"Undervalued: V={valuation.composite_score:.3f} ({valuation.interpretation})"
            )
        elif valuation.composite_score > 0 and valuation.trend and valuation.trend > 0:
            reasons.append(
                f"Approaching undervaluation: V={valuation.composite_score:.3f}, "
                f"trend={valuation.trend:.3f}"
            )
        else:
            is_signal = False
            reasons.append("Not undervalued")

        # Condition 3: Minimum deviation from mean
        is_extreme, z_score = self._sentiment_analyzer.is_sentiment_extreme(
            sentiment.symbol, self._config.min_deviation_std
        )
        if is_extreme:
            reasons.append(f"Sentiment extreme: {z_score:.2f} std devs from mean")
        else:
            is_signal = False
            reasons.append(
                f"Sentiment not extreme enough: {z_score:.2f} < {self._config.min_deviation_std}"
            )

        return is_signal, reasons

    def _check_sell_conditions(
        self, sentiment: SentimentResult, valuation: ValuationScore, current_price: float
    ) -> tuple[bool, list[str]]:
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
        if sentiment.smoothed_score > self._config.sentiment_threshold:
            reasons.append(f"Sentiment bullish: {sentiment.smoothed_score:.2f}")
        elif sentiment.roc > self._config.roc_threshold:
            reasons.append(f"Sentiment rapidly improving: ROC {sentiment.roc:.2f}")
        else:
            is_signal = False
            reasons.append("Sentiment not bullish enough")

        # Condition 2: Fundamentals overvalued
        if valuation.composite_score < self._config.overvalued_threshold:
            reasons.append(
                f"Overvalued: V={valuation.composite_score:.3f} ({valuation.interpretation})"
            )
        elif valuation.composite_score < 0 and valuation.trend and valuation.trend < 0:
            reasons.append(
                f"Approaching overvaluation: V={valuation.composite_score:.3f}, "
                f"trend={valuation.trend:.3f}"
            )
        else:
            is_signal = False
            reasons.append("Not overvalued")

        # Condition 3: Minimum deviation from mean
        is_extreme, z_score = self._sentiment_analyzer.is_sentiment_extreme(
            sentiment.symbol, self._config.min_deviation_std
        )
        if is_extreme:
            reasons.append(f"Sentiment extreme: {z_score:.2f} std devs from mean")
        else:
            is_signal = False
            reasons.append(
                f"Sentiment not extreme enough: {z_score:.2f} < {self._config.min_deviation_std}"
            )

        return is_signal, reasons

    def _check_confirmation(self, symbol: str, signal_type: SignalType) -> bool:
        """
        Check if signal persists for required confirmation periods.

        Args:
            symbol: Stock symbol
            signal_type: BUY or SELL

        Returns:
            True if confirmed
        """
        if symbol not in self._signal_history:
            return False

        history = self._signal_history[symbol]
        required = self._config.confirmation_periods

        # Count recent signals of same type
        recent_signals = [s for s in history[-required:] if s.signal_type == signal_type]

        return len(recent_signals) >= required

    def _check_exit_conditions(
        self,
        position: InternalPosition,
        current_price: float,
        sentiment: SentimentResult | None = None,
        valuation: ValuationScore | None = None,
    ) -> tuple[SignalType, list[str]] | None:
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
        if position.entry_type == SignalType.BUY:
            if current_price <= position.stop_loss:
                reasons.append(f"Stop-loss hit: {current_price:.2f} <= {position.stop_loss:.2f}")
                return (SignalType.EXIT_LONG, reasons)
        else:  # SELL
            if current_price >= position.stop_loss:
                reasons.append(f"Stop-loss hit: {current_price:.2f} >= {position.stop_loss:.2f}")
                return (SignalType.EXIT_SHORT, reasons)

        # Take-profit
        if position.entry_type == SignalType.BUY:
            if current_price >= position.take_profit:
                reasons.append(
                    f"Take-profit hit: {current_price:.2f} >= {position.take_profit:.2f}"
                )
                return (SignalType.EXIT_LONG, reasons)
        else:  # SELL
            if current_price <= position.take_profit:
                reasons.append(
                    f"Take-profit hit: {current_price:.2f} <= {position.take_profit:.2f}"
                )
                return (SignalType.EXIT_SHORT, reasons)

        # Signal reversal
        if sentiment and valuation:
            if position.entry_type == SignalType.BUY:
                # Exit long if sentiment improved or valuation deteriorated
                if sentiment.smoothed_score > self._config.sentiment_reversal_threshold:
                    reasons.append(
                        f"Sentiment reversal: {sentiment.smoothed_score:.2f} > "
                        f"{self._config.sentiment_reversal_threshold}"
                    )
                    return (SignalType.EXIT_LONG, reasons)
                if valuation.composite_score < self._config.valuation_reversal_threshold:
                    reasons.append(
                        f"Valuation reversal: {valuation.composite_score:.3f} < "
                        f"{self._config.valuation_reversal_threshold}"
                    )
                    return (SignalType.EXIT_LONG, reasons)
            else:  # SELL
                # Exit short if sentiment deteriorated or valuation improved
                if sentiment.smoothed_score < -self._config.sentiment_reversal_threshold:
                    reasons.append(
                        f"Sentiment reversal: {sentiment.smoothed_score:.2f} < "
                        f"-{self._config.sentiment_reversal_threshold}"
                    )
                    return (SignalType.EXIT_SHORT, reasons)
                if valuation.composite_score > self._config.valuation_reversal_threshold:
                    reasons.append(
                        f"Valuation reversal: {valuation.composite_score:.3f} > "
                        f"{self._config.valuation_reversal_threshold}"
                    )
                    return (SignalType.EXIT_SHORT, reasons)

        return None

    def _calculate_position_size(
        self, signal_strength: float, portfolio_value: float, current_price: float
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
        base_value = portfolio_value * self._config.base_position_size

        # Adjust by strength (strength/50 = 0 to 2)
        strength_factor = signal_strength / 50.0

        adjusted_value = base_value * strength_factor

        # Convert to shares
        shares = adjusted_value / current_price

        # Clip to max position size
        max_value = portfolio_value * self._config.max_position_size
        max_shares = max_value / current_price

        shares = min(shares, max_shares)

        return round(shares, 2)

    def _record_signal(self, signal: CommonTradingSignal) -> None:
        """Record signal in history."""
        if signal.symbol not in self._signal_history:
            self._signal_history[signal.symbol] = []

        self._signal_history[signal.symbol].append(signal)

        # Keep only last 100 signals
        if len(self._signal_history[signal.symbol]) > 100:
            self._signal_history[signal.symbol] = self._signal_history[signal.symbol][-100:]

    # =========================================================================
    # Public Methods for Backward Compatibility
    # =========================================================================

    def generate_signal(
        self,
        symbol: str,
        current_price: float,
        sentiment: SentimentResult,
        valuation: ValuationScore,
        portfolio_value: float = 100000.0,
    ) -> CommonTradingSignal:
        """
        Generate a trading signal (backward compatible method).

        This method is kept for backward compatibility with existing code.
        New code should use generate_signals() from the interface.

        Args:
            symbol: Stock symbol
            current_price: Current stock price
            sentiment: Sentiment analysis result
            valuation: Valuation score
            portfolio_value: Total portfolio value (default 100k)

        Returns:
            TradingSignal from common.types
        """
        signal = self._create_signal(
            symbol=symbol,
            current_price=current_price,
            sentiment=sentiment,
            valuation=valuation,
            timestamp=datetime.now(),
            portfolio_value=portfolio_value,
        )
        # _create_signal returns None only for edge cases, but we need to return a signal
        if signal is None:
            # Return a HOLD signal if no signal generated
            signal = CommonTradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                timestamp=datetime.now(),
                source=self.name,
                strength=0.0,
                confidence=0.0,
                reasons=["No clear signal"],
            )
        return signal

    def add_position(self, position: InternalPosition) -> None:
        """Add a position to track."""
        self._positions[position.symbol] = position

    def remove_position(self, symbol: str) -> None:
        """Remove a position."""
        if symbol in self._positions:
            del self._positions[symbol]

    def get_positions(self) -> dict[str, InternalPosition]:
        """Get all active positions."""
        return self._positions.copy()

    def get_signal_history(
        self, symbol: str | None = None, limit: int = 10
    ) -> list[CommonTradingSignal]:
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

    # Expose config for backward compatibility
    @property
    def config(self) -> SignalConfig:
        """Get the signal configuration."""
        return self._config

    # Expose sentiment analyzer for backward compatibility
    @property
    def sentiment_analyzer(self) -> SentimentAnalyzer:
        """Get the sentiment analyzer."""
        return self._sentiment_analyzer

    # Expose valuation calculator for backward compatibility
    @property
    def valuation_calculator(self) -> ValuationCalculator:
        """Get the valuation calculator."""
        return self._valuation_calculator


def load_config(config_path: str) -> SignalConfig:
    """
    Load signal configuration from JSON file.

    The config file has a nested structure with signal settings under
    the "signal" key. This function parses the nested structure correctly.

    Expected config.json structure:
    {
        "signal": {
            "sentiment_threshold": 1.5,
            "roc_threshold": 1.0,
            "min_deviation_std": 1.5,
            "undervalued_threshold": 0.10,
            "overvalued_threshold": -0.10,
            "confirmation_periods": 2,
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.15,
            "sentiment_reversal_threshold": 1.0,
            "valuation_reversal_threshold": 0.05,
            "base_position_size": 0.01,
            "max_position_size": 0.05,
            "sentiment_weight": 0.5,
            "valuation_weight": 0.5
        }
    }

    Args:
        config_path: Path to config JSON file

    Returns:
        SignalConfig instance
    """
    with open(config_path) as f:
        config_dict = json.load(f)

    # Parse nested structure
    if "signal" in config_dict:
        signal_config = config_dict["signal"]
    else:
        # Fallback: assume flat structure for backward compatibility
        signal_config = config_dict

    return SignalConfig(
        sentiment_threshold=signal_config.get("sentiment_threshold", 1.5),
        roc_threshold=signal_config.get("roc_threshold", 1.0),
        min_deviation_std=signal_config.get("min_deviation_std", 1.5),
        undervalued_threshold=signal_config.get("undervalued_threshold", 0.10),
        overvalued_threshold=signal_config.get("overvalued_threshold", -0.10),
        confirmation_periods=signal_config.get("confirmation_periods", 2),
        stop_loss_pct=signal_config.get("stop_loss_pct", 0.08),
        take_profit_pct=signal_config.get("take_profit_pct", 0.15),
        sentiment_reversal_threshold=signal_config.get("sentiment_reversal_threshold", 1.0),
        valuation_reversal_threshold=signal_config.get("valuation_reversal_threshold", 0.05),
        base_position_size=signal_config.get("base_position_size", 0.01),
        max_position_size=signal_config.get("max_position_size", 0.05),
        sentiment_weight=signal_config.get("sentiment_weight", 0.5),
        valuation_weight=signal_config.get("valuation_weight", 0.5),
    )


# Example usage and testing
if __name__ == "__main__":
    # Initialize components
    from .sentiment import SentimentAnalyzer, SentimentSource
    from .valuation import SectorMetrics, ValuationCalculator, ValuationMetrics

    sentiment_analyzer = SentimentAnalyzer()
    valuation_calculator = ValuationCalculator()
    signal_generator = SignalGenerator(sentiment_analyzer, valuation_calculator)

    # Create example sentiment (bearish)
    bearish_sources = [
        SentimentSource("news", datetime.now(), -0.4, -0.4, 0.8, {}),
        SentimentSource("social", datetime.now(), -0.6, -0.6, 0.7, {}),
        SentimentSource("search", datetime.now(), -0.7, -0.7, 0.6, {}),
        SentimentSource("forum", datetime.now(), -0.5, -0.5, 0.5, {}),
    ]
    sentiment = sentiment_analyzer.calculate_sentiment("600519.SH", bearish_sources)

    # Create example valuation (undervalued)
    company = ValuationMetrics(
        pe_ratio=15.0,
        pb_ratio=2.5,
        dividend_yield=0.02,
        peg_ratio=1.2,
        eps=2.0,
        book_value_per_share=8.0,
        annual_dividend=0.4,
    )
    sector = SectorMetrics(pe_ratio=25.0, pb_ratio=2.5, dividend_yield=0.015, peg_ratio=1.8)
    valuation = valuation_calculator.calculate_valuation(company, sector)

    # Generate signal
    signal = signal_generator.generate_signal(
        symbol="600519.SH",
        current_price=100.0,
        sentiment=sentiment,
        valuation=valuation,
        portfolio_value=100000.0,
    )

    print("=== Trading Signal ===")
    print(f"Symbol: {signal.symbol}")
    print(f"Type: {signal.signal_type.value}")
    print(f"Strength: {signal.strength:.1f}")
    print(f"Confidence: {signal.confidence:.2f}")
    print(f"Entry Price: Y{signal.entry_price:.2f}" if signal.entry_price else "Entry Price: N/A")
    if signal.stop_loss is not None:
        print(f"Stop Loss: Y{signal.stop_loss:.2f}")
    if signal.take_profit is not None:
        print(f"Take Profit: Y{signal.take_profit:.2f}")
    if signal.quantity:
        print(f"Quantity: {signal.quantity} shares")
    print(f"\nSentiment Score: {signal.sentiment_score:.2f}")
    print(f"Valuation Score: {signal.valuation_score:.3f}")
    print("\nReasons:")
    for reason in signal.reasons:
        print(f"  - {reason}")
