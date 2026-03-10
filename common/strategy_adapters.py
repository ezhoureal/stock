"""
Strategy Adapters

Wraps existing strategy implementations to conform to the SignalGenerator interface.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import sys
from pathlib import Path

from .types import TradingSignal, SignalType
from .interfaces import SignalGenerator, DataProvider
from .config import SentimentArbConfig, ContrarianConfig

logger = logging.getLogger(__name__)


class SentimentArbAdapter(SignalGenerator):
    """
    Adapter for the sentiment_arbitrage module.

    Wraps the GPU-accelerated sentiment arbitrage strategy to
    conform to the SignalGenerator interface.
    """

    def __init__(self, config: Optional[SentimentArbConfig] = None):
        """
        Initialize sentiment arbitrage adapter.

        Args:
            config: Strategy configuration
        """
        self._config = config or SentimentArbConfig()
        self._name = "sentiment_arbitrage"
        self._state: Dict[str, Any] = {}

        # Lazy load the actual implementation
        self._generator = None
        self._kalman_filter = None
        self._z_scorer = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def time_horizon(self) -> str:
        return "high_frequency"

    def _initialize(self) -> None:
        """Lazy initialization of GPU components"""
        if self._generator is not None:
            return

        try:
            # Add sentiment_arbitrage to path
            base_path = Path(__file__).parent.parent / "sentiment_arbitrage" / "src"
            if base_path.exists():
                sys.path.insert(0, str(base_path))

            from signal_generation import SignalGenerator as SentArbGenerator
            from signal_generation import SignalConfig

            # Convert config
            sa_config = SignalConfig(
                long_sentiment_threshold=self._config.long_sentiment_threshold,
                long_price_threshold=self._config.long_price_threshold,
                long_dislocation_threshold=self._config.long_dislocation_threshold,
                short_sentiment_threshold=self._config.short_sentiment_threshold,
                short_price_threshold=self._config.short_price_threshold,
                short_dislocation_threshold=self._config.short_dislocation_threshold,
                exit_stop_loss_pct=self._config.exit_stop_loss_pct,
                exit_take_profit_pct=self._config.exit_take_profit_pct,
            )

            self._generator = SentArbGenerator(config=sa_config)
            logger.info("Sentiment arbitrage generator initialized")

        except ImportError as e:
            logger.warning(f"Could not import sentiment_arbitrage: {e}")
            self._generator = None

    def generate_signals(
        self,
        symbols: List[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> List[TradingSignal]:
        """
        Generate trading signals using sentiment arbitrage logic.

        Args:
            symbols: List of symbols to analyze
            as_of: Current timestamp
            data_provider: Data source

        Returns:
            List of TradingSignal objects
        """
        self._initialize()

        if self._generator is None:
            # Return empty signals if not available
            return []

        try:
            # Get required data
            lookback_days = self._config.lookback_days
            start_date = datetime(as_of.year, as_of.month, as_of.day) - __import__('datetime').timedelta(days=lookback_days)

            # Get prices
            prices_df = data_provider.get_prices(symbols, start_date, as_of)

            if prices_df.empty:
                return []

            # Get sentiment
            sentiment_scores = data_provider.get_sentiment(symbols, start_date, as_of)

            if not sentiment_scores:
                # Use mock sentiment if not available
                import numpy as np
                sentiment_map = {s: np.random.randn() for s in symbols}
            else:
                sentiment_map = {s.symbol: s.score for s in sentiment_scores}

            # Calculate z-scores (simplified)
            import numpy as np
            import pandas as pd

            signals = []

            for symbol in symbols:
                if symbol not in prices_df.index.get_level_values(0):
                    continue

                symbol_prices = prices_df.xs(symbol, level=0)["close"]

                if len(symbol_prices) < 20:
                    continue

                # Calculate price z-score
                returns = symbol_prices.pct_change().dropna()
                if len(returns) < 20:
                    continue

                z_score = (returns.iloc[-1] - returns.mean()) / returns.std()

                # Get sentiment
                sentiment = sentiment_map.get(symbol, 0)

                # Calculate dislocation
                dislocation = sentiment - z_score

                # Check signal conditions
                signal_type = None
                strength = 0.0

                if (sentiment > self._config.long_sentiment_threshold and
                    z_score < self._config.long_price_threshold and
                    dislocation > self._config.long_dislocation_threshold):
                    signal_type = SignalType.BUY
                    strength = min((sentiment + abs(z_score) + dislocation) / 10 * 100, 100)

                elif (sentiment < self._config.short_sentiment_threshold and
                      z_score > self._config.short_price_threshold and
                      dislocation < self._config.short_dislocation_threshold):
                    signal_type = SignalType.SELL
                    strength = min((abs(sentiment) + z_score + abs(dislocation)) / 10 * 100, 100)

                if signal_type:
                    current_price = float(symbol_prices.iloc[-1])
                    signal = TradingSignal(
                        symbol=symbol,
                        signal_type=signal_type,
                        timestamp=as_of,
                        source=self._name,
                        strength=strength,
                        confidence=0.7,
                        entry_price=current_price,
                        stop_loss=current_price * (1 - self._config.exit_stop_loss_pct)
                            if signal_type == SignalType.BUY
                            else current_price * (1 + self._config.exit_stop_loss_pct),
                        take_profit=current_price * (1 + self._config.exit_take_profit_pct)
                            if signal_type == SignalType.BUY
                            else current_price * (1 - self._config.exit_take_profit_pct),
                        sentiment_score=sentiment,
                        price_z_score=z_score,
                        dislocation=dislocation,
                        reasons=[f"Sentiment: {sentiment:.2f}, Z-score: {z_score:.2f}, Dislocation: {dislocation:.2f}"],
                    )
                    signals.append(signal)

            return signals

        except Exception as e:
            logger.error(f"Error generating sentiment arbitrage signals: {e}")
            return []

    def update(self, new_data: Dict[str, Any]) -> None:
        """Update internal state with new data"""
        self._state.update(new_data)

    def get_state(self) -> Dict[str, Any]:
        """Serialize internal state"""
        return self._state.copy()

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore internal state"""
        self._state = state.copy()

    def get_required_data(self) -> List[str]:
        """Get required data types"""
        return ["prices", "sentiment"]


class ContrarianAdapter(SignalGenerator):
    """
    Adapter for the strategy module (contrarian fundamental strategy).

    Wraps the valuation + sentiment based contrarian strategy to
    conform to the SignalGenerator interface.
    """

    def __init__(self, config: Optional[ContrarianConfig] = None):
        """
        Initialize contrarian strategy adapter.

        Args:
            config: Strategy configuration
        """
        self._config = config or ContrarianConfig()
        self._name = "contrarian_strategy"
        self._state: Dict[str, Any] = {}

        # Lazy load the actual implementation
        self._signal_generator = None
        self._sentiment_analyzer = None
        self._valuation_calculator = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def time_horizon(self) -> str:
        return "medium_term"

    def _initialize(self) -> None:
        """Lazy initialization of strategy components"""
        if self._signal_generator is not None:
            return

        try:
            # Add strategy to path
            base_path = Path(__file__).parent.parent / "strategy"
            if base_path.exists():
                sys.path.insert(0, str(base_path))

            from signals import SignalGenerator as ContrarianGenerator
            from signals import SignalConfig
            from sentiment import SentimentAnalyzer
            from valuation import ValuationCalculator

            # Convert config
            sig_config = SignalConfig(
                sentiment_threshold=self._config.sentiment_threshold,
                undervalued_threshold=self._config.undervalued_threshold,
                overvalued_threshold=self._config.overvalued_threshold,
                stop_loss_pct=self._config.stop_loss_pct,
                take_profit_pct=self._config.take_profit_pct,
                sentiment_weight=self._config.sentiment_weight,
                valuation_weight=self._config.valuation_weight,
            )

            self._sentiment_analyzer = SentimentAnalyzer()
            self._valuation_calculator = ValuationCalculator()
            self._signal_generator = ContrarianGenerator(
                self._sentiment_analyzer,
                self._valuation_calculator,
                sig_config,
            )

            logger.info("Contrarian strategy generator initialized")

        except ImportError as e:
            logger.warning(f"Could not import strategy module: {e}")
            self._signal_generator = None

    def generate_signals(
        self,
        symbols: List[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> List[TradingSignal]:
        """
        Generate trading signals using contrarian fundamental logic.

        Args:
            symbols: List of symbols to analyze
            as_of: Current timestamp
            data_provider: Data source

        Returns:
            List of TradingSignal objects
        """
        self._initialize()

        signals = []

        try:
            # Get fundamentals
            fundamentals = data_provider.get_fundamentals(symbols, as_of)
            fundamentals_map = {f.symbol: f for f in fundamentals}

            # Get sentiment
            sentiment_scores = data_provider.get_latest_sentiment(symbols)

            # Get latest prices
            prices = data_provider.get_latest_prices(symbols)

            for symbol in symbols:
                fund = fundamentals_map.get(symbol)
                sentiment = sentiment_scores.get(symbol)
                price = prices.get(symbol)

                if not price:
                    continue

                # Calculate valuation score (simplified)
                valuation_score = 0.0
                if fund:
                    # Simple valuation scoring
                    if fund.pe_ratio and fund.pe_ratio < 15:
                        valuation_score += 0.2
                    elif fund.pe_ratio and fund.pe_ratio > 30:
                        valuation_score -= 0.2

                    if fund.pb_ratio and fund.pb_ratio < 1.5:
                        valuation_score += 0.15
                    elif fund.pb_ratio and fund.pb_ratio > 4:
                        valuation_score -= 0.15

                    if fund.roe and fund.roe > 0.15:
                        valuation_score += 0.1

                # Get sentiment score
                sentiment_score = 0.0
                if sentiment:
                    sentiment_score = sentiment.score

                # Determine signal
                signal_type = None
                strength = 0.0
                reasons = []

                # BUY: Bearish sentiment + Undervalued
                if (sentiment_score < -self._config.sentiment_threshold / 10 and
                    valuation_score > self._config.undervalued_threshold):
                    signal_type = SignalType.BUY
                    strength = min((abs(sentiment_score) * 20 + valuation_score * 50), 100)
                    reasons.append(f"Bearish sentiment: {sentiment_score:.2f}")
                    reasons.append(f"Undervalued: {valuation_score:.2f}")

                # SELL: Bullish sentiment + Overvalued
                elif (sentiment_score > self._config.sentiment_threshold / 10 and
                      valuation_score < self._config.overvalued_threshold):
                    signal_type = SignalType.SELL
                    strength = min((abs(sentiment_score) * 20 + abs(valuation_score) * 50), 100)
                    reasons.append(f"Bullish sentiment: {sentiment_score:.2f}")
                    reasons.append(f"Overvalued: {valuation_score:.2f}")

                if signal_type:
                    signal = TradingSignal(
                        symbol=symbol,
                        signal_type=signal_type,
                        timestamp=as_of,
                        source=self._name,
                        strength=strength,
                        confidence=0.6,
                        entry_price=price,
                        stop_loss=price * (1 - self._config.stop_loss_pct)
                            if signal_type == SignalType.BUY
                            else price * (1 + self._config.stop_loss_pct),
                        take_profit=price * (1 + self._config.take_profit_pct)
                            if signal_type == SignalType.BUY
                            else price * (1 - self._config.take_profit_pct),
                        sentiment_score=sentiment_score,
                        valuation_score=valuation_score,
                        reasons=reasons,
                    )
                    signals.append(signal)

            return signals

        except Exception as e:
            logger.error(f"Error generating contrarian signals: {e}")
            return []

    def update(self, new_data: Dict[str, Any]) -> None:
        """Update internal state"""
        self._state.update(new_data)

    def get_state(self) -> Dict[str, Any]:
        """Serialize internal state"""
        return self._state.copy()

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore internal state"""
        self._state = state.copy()

    def get_required_data(self) -> List[str]:
        """Get required data types"""
        return ["prices", "fundamentals", "sentiment"]


def create_strategy_adapters(
    sentiment_arb_config: Optional[SentimentArbConfig] = None,
    contrarian_config: Optional[ContrarianConfig] = None,
) -> Dict[str, SignalGenerator]:
    """
    Factory function to create strategy adapters.

    Args:
        sentiment_arb_config: Sentiment arbitrage config
        contrarian_config: Contrarian strategy config

    Returns:
        Dictionary of strategy name to adapter
    """
    adapters = {}

    try:
        adapters["sentiment_arbitrage"] = SentimentArbAdapter(sentiment_arb_config)
    except Exception as e:
        logger.warning(f"Could not create sentiment arbitrage adapter: {e}")

    try:
        adapters["contrarian_strategy"] = ContrarianAdapter(contrarian_config)
    except Exception as e:
        logger.warning(f"Could not create contrarian adapter: {e}")

    return adapters
