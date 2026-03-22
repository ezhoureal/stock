"""
Signal Router Implementation

Aggregates signals from multiple strategies and produces unified portfolio signals.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from .config import RouterConfig
from .interfaces import DataProvider, SignalGenerator
from .interfaces import SignalRouter as SignalRouterInterface
from .types import (
    PortfolioSignal,
    SignalType,
    TradingSignal,
)

logger = logging.getLogger(__name__)


@dataclass
class SignalConflict:
    """Represents a conflict between signals"""

    symbol: str
    signals: list[TradingSignal]
    resolution: str  # "weighted", "strongest", "consensus", "dropped"


class SignalRouterImpl(SignalRouterInterface):
    """
    Implementation of signal aggregation and routing.

    Collects signals from multiple strategies, resolves conflicts,
    and produces unified portfolio signals with risk controls.
    """

    def __init__(self, config: RouterConfig | None = None):
        """
        Initialize signal router.

        Args:
            config: Router configuration
        """
        self.config = config or RouterConfig()
        self._strategies: dict[str, SignalGenerator] = {}
        self._weights: dict[str, float] = {}
        self._signal_history: list[TradingSignal] = []
        self._last_signal_time: dict[str, datetime] = {}  # symbol -> last signal time

    def add_strategy(self, strategy: SignalGenerator) -> None:
        """Add a signal-generating strategy"""
        self._strategies[strategy.name] = strategy

        # Set default weight based on strategy type
        if "sentiment_arb" in strategy.name:
            self._weights[strategy.name] = self.config.sentiment_arb_weight
        elif "contrarian" in strategy.name or "strategy" in strategy.name:
            self._weights[strategy.name] = self.config.strategy_weight
        else:
            self._weights[strategy.name] = 1.0 / (len(self._strategies))

        logger.info(
            f"Added strategy: {strategy.name} with weight {self._weights[strategy.name]:.2f}"
        )

    def remove_strategy(self, strategy_name: str) -> None:
        """Remove a strategy"""
        if strategy_name in self._strategies:
            del self._strategies[strategy_name]
            del self._weights[strategy_name]
            logger.info(f"Removed strategy: {strategy_name}")

    def set_weights(self, weights: dict[str, float]) -> None:
        """Set strategy weights"""
        # Normalize weights
        total = sum(weights.values())
        if total > 0:
            self._weights = {k: v / total for k, v in weights.items()}
        logger.info(f"Updated weights: {self._weights}")

    def aggregate_signals(
        self,
        symbols: list[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> PortfolioSignal:
        """
        Collect and aggregate signals from all strategies.

        Process:
        1. Collect signals from all strategies
        2. Filter by minimum conviction and strength
        3. Group by symbol
        4. Resolve conflicts
        5. Apply position sizing
        6. Apply risk limits
        """
        # Step 1: Collect signals from all strategies
        all_signals = []
        for name, strategy in self._strategies.items():
            try:
                signals = strategy.generate_signals(symbols, as_of, data_provider)
                for signal in signals:
                    signal.source = name  # Ensure source is set
                all_signals.extend(signals)
                logger.debug(f"Collected {len(signals)} signals from {name}")
            except Exception as e:
                logger.error(f"Error generating signals from {name}: {e}")

        # Step 2: Filter signals
        filtered_signals = self._filter_signals(all_signals)
        logger.debug(f"Filtered to {len(filtered_signals)} signals")

        # Step 3: Group by symbol
        signals_by_symbol = defaultdict(list)
        for signal in filtered_signals:
            signals_by_symbol[signal.symbol].append(signal)

        # Step 4: Resolve conflicts
        resolved_signals = []
        conflicts = []
        for _symbol, sigs in signals_by_symbol.items():
            if len(sigs) == 1:
                resolved_signals.append(sigs[0])
            else:
                resolved, conflict = self._resolve_conflict(sigs)
                resolved_signals.append(resolved)
                conflicts.append(conflict)

        # Step 5: Apply position sizing
        sized_signals = self._apply_position_sizing(resolved_signals)

        # Step 6: Apply risk limits
        final_signals = self._apply_risk_limits(sized_signals)

        # Store history
        self._signal_history.extend(final_signals)

        # Build portfolio signal
        portfolio = self._build_portfolio_signal(final_signals, as_of)

        if conflicts:
            logger.info(f"Resolved {len(conflicts)} signal conflicts")

        return portfolio

    def _filter_signals(self, signals: list[TradingSignal]) -> list[TradingSignal]:
        """Filter signals by minimum criteria"""
        filtered = []

        for signal in signals:
            # Filter by conviction
            if signal.confidence < self.config.min_conviction:
                logger.debug(
                    f"Dropping signal for {signal.symbol}: "
                    f"confidence {signal.confidence:.2f} < {self.config.min_conviction}"
                )
                continue

            # Filter by strength
            if signal.strength < self.config.min_strength:
                logger.debug(
                    f"Dropping signal for {signal.symbol}: "
                    f"strength {signal.strength:.1f} < {self.config.min_strength}"
                )
                continue

            # Filter by cooldown
            if signal.symbol in self._last_signal_time:
                last_time = self._last_signal_time[signal.symbol]
                cooldown_seconds = self.config.signal_cooldown_minutes * 60
                if (signal.timestamp - last_time).total_seconds() < cooldown_seconds:
                    logger.debug(
                        f"Dropping signal for {signal.symbol}: cooldown period not elapsed"
                    )
                    continue

            filtered.append(signal)

        return filtered

    def _resolve_conflict(
        self,
        signals: list[TradingSignal],
    ) -> tuple[TradingSignal, SignalConflict]:
        """
        Resolve conflicting signals for the same symbol.

        Resolution methods:
        1. If all agree -> weighted average
        2. If mixed but one is much stronger -> use strongest
        3. If require_agreement and mixed -> drop
        4. Otherwise -> weighted vote
        """
        assert len(signals) > 1

        # Check if all signals agree on direction
        buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in signals if s.signal_type == SignalType.SELL]
        exit_signals = [s for s in signals if s.is_exit]

        # Exit signals take priority
        if exit_signals:
            resolved = max(exit_signals, key=lambda s: s.strength)
            return resolved, SignalConflict(
                symbol=signals[0].symbol,
                signals=signals,
                resolution="exit_priority",
            )

        # If mixed directions
        if buy_signals and sell_signals:
            if self.config.require_agreement:
                # Drop conflicting signals
                return TradingSignal(
                    symbol=signals[0].symbol,
                    signal_type=SignalType.HOLD,
                    timestamp=signals[0].timestamp,
                    source="router",
                    strength=0.0,
                    confidence=0.0,
                    reasons=["Conflicting signals dropped due to require_agreement"],
                ), SignalConflict(
                    symbol=signals[0].symbol,
                    signals=signals,
                    resolution="dropped",
                )

            # Weighted vote based on strategy weights and signal strength
            buy_score = sum(
                self._weights.get(s.source, 1.0) * s.strength * s.confidence for s in buy_signals
            )
            sell_score = sum(
                self._weights.get(s.source, 1.0) * s.strength * s.confidence for s in sell_signals
            )

            if buy_score > sell_score:
                winner_signals = buy_signals
                resolution = "weighted"
            else:
                winner_signals = sell_signals
                resolution = "weighted"

            # Merge winning signals
            resolved = self._merge_signals(winner_signals)
            return resolved, SignalConflict(
                symbol=signals[0].symbol,
                signals=signals,
                resolution=resolution,
            )

        # All same direction - weighted merge
        if buy_signals:
            resolved = self._merge_signals(buy_signals)
        else:
            resolved = self._merge_signals(sell_signals)

        return resolved, SignalConflict(
            symbol=signals[0].symbol,
            signals=signals,
            resolution="consensus",
        )

    def _merge_signals(self, signals: list[TradingSignal]) -> TradingSignal:
        """Merge multiple signals of the same direction"""
        if len(signals) == 1:
            return signals[0]

        # Calculate weighted averages
        total_weight = sum(self._weights.get(s.source, 1.0) * s.confidence for s in signals)

        def weighted_avg(attr: str) -> float | None:
            values = [getattr(s, attr) for s in signals if getattr(s, attr) is not None]
            if not values:
                return None
            weights = [
                self._weights.get(s.source, 1.0) * s.confidence
                for s in signals
                if getattr(s, attr) is not None
            ]
            return sum(v * w for v, w in zip(values, weights, strict=False)) / sum(weights)

        merged = TradingSignal(
            symbol=signals[0].symbol,
            signal_type=signals[0].signal_type,
            timestamp=max(s.timestamp for s in signals),
            source="router",
            strength=weighted_avg("strength") or 0.0,
            confidence=total_weight / len(signals),
            entry_price=weighted_avg("entry_price"),
            stop_loss=weighted_avg("stop_loss"),
            take_profit=weighted_avg("take_profit"),
            sentiment_score=weighted_avg("sentiment_score"),
            valuation_score=weighted_avg("valuation_score"),
            reasons=list(set(r for s in signals for r in s.reasons)),
            metadata={"merged_from": [s.source for s in signals]},
        )

        return merged

    def _apply_position_sizing(
        self,
        signals: list[TradingSignal],
    ) -> list[TradingSignal]:
        """Apply position sizing to signals"""
        for signal in signals:
            if signal.position_size is None:
                if self.config.position_sizing_method == "signal_strength":
                    # Size proportional to signal strength
                    signal.position_size = (
                        self.config.base_position_size
                        * (signal.strength / 50.0)
                        * signal.confidence
                    )
                elif self.config.position_sizing_method == "equal":
                    signal.position_size = self.config.base_position_size
                elif self.config.position_sizing_method == "risk_parity":
                    # Simple risk parity - inverse of stop loss distance
                    if signal.entry_price and signal.stop_loss:
                        risk = abs(signal.entry_price - signal.stop_loss) / signal.entry_price
                        signal.position_size = self.config.base_position_size / max(risk, 0.01)
                    else:
                        signal.position_size = self.config.base_position_size
                else:
                    signal.position_size = self.config.base_position_size

            # Cap at max position size
            signal.position_size = min(signal.position_size, self.config.max_position_pct)

        return signals

    def _apply_risk_limits(
        self,
        signals: list[TradingSignal],
    ) -> list[TradingSignal]:
        """Apply risk limits to portfolio"""
        if not signals:
            return signals

        # Sort by strength (strongest first)
        signals.sort(key=lambda s: s.strength * s.confidence, reverse=True)

        # Limit number of signals
        signals = signals[: self.config.max_signals_per_run]

        # Check total exposure
        total_exposure = sum(s.position_size or 0 for s in signals if s.is_entry)

        if total_exposure > self.config.max_total_exposure:
            # Scale down proportionally
            scale_factor = self.config.max_total_exposure / total_exposure
            for signal in signals:
                if signal.is_entry and signal.position_size:
                    signal.position_size *= scale_factor
            logger.info(f"Scaled down positions by {scale_factor:.2%} to meet exposure limit")

        return signals

    def _build_portfolio_signal(
        self,
        signals: list[TradingSignal],
        timestamp: datetime,
    ) -> PortfolioSignal:
        """Build final portfolio signal"""
        long_signals = [s for s in signals if s.signal_type == SignalType.BUY]
        short_signals = [s for s in signals if s.signal_type == SignalType.SELL]

        long_exposure = sum(s.position_size or 0 for s in long_signals)
        short_exposure = sum(s.position_size or 0 for s in short_signals)

        # Check long/short ratio
        if short_exposure > 0 and long_exposure / short_exposure > self.config.max_long_short_ratio:
            logger.warning(
                f"Long/short ratio {long_exposure / short_exposure:.2f} "
                f"exceeds limit {self.config.max_long_short_ratio}"
            )

        return PortfolioSignal(
            signals=signals,
            timestamp=timestamp,
            long_count=len(long_signals),
            short_count=len(short_signals),
            total_exposure=long_exposure + short_exposure,
            net_exposure=long_exposure - short_exposure,
            max_single_position=max(s.position_size or 0 for s in signals) if signals else 0,
        )

    def get_signal_history(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[TradingSignal]:
        """Get signal history"""
        history = self._signal_history

        if symbol:
            history = [s for s in history if s.symbol == symbol]

        return history[-limit:]
