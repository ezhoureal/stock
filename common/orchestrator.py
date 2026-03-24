"""
Trading System Orchestrator

Main entry point for running the trading system. Coordinates all components:
- Data providers
- Signal generators (strategies)
- Signal routing/aggregation
- Execution (broker)
- Backtesting
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .config import SystemConfig
from .interfaces import (
    BacktestResult,
    DataProvider,
    ExecutionClient,
    SignalGenerator,
)
from .signal_router import SignalRouterImpl
from .strategy_adapters import (
    create_strategy_adapters,
)
from .types import PortfolioSignal, SignalType, TradingSignal

logger = logging.getLogger(__name__)


@dataclass
class SystemState:
    """Current state of the trading system"""

    last_run: datetime | None = None
    active_positions: dict[str, Any] | None = None
    pending_orders: dict[str, Any] | None = None
    daily_pnl: float = 0.0
    total_equity: float = 0.0


class TradingSystem:
    """
    Main trading system orchestrator.

    Coordinates all components and provides a unified interface for:
    - Running live trading
    - Running backtests
    - Managing strategies
    - Monitoring system state
    """

    def __init__(
        self,
        config: SystemConfig | None = None,
        config_path: str | None = None,
    ):
        """
        Initialize trading system.

        Args:
            config: System configuration
            config_path: Path to config file (overrides config param)
        """
        if config_path:
            self.config = SystemConfig.from_file(config_path)
        else:
            self.config = config or SystemConfig()

        # Initialize components
        self._data_provider: DataProvider | None = None
        self._strategies: dict[str, SignalGenerator] = {}
        self._router: SignalRouterImpl | None = None
        self._execution_client: ExecutionClient | None = None
        self._state = SystemState()

        self._initialized = False

    def initialize(self, data_provider: DataProvider | None = None) -> None:
        """
        Initialize all system components.

        This method must be called before running the system.

        Args:
            data_provider: Optional DataProvider instance. If None, one must be
                set via set_data_provider() before running.
        """
        logger.info("Initializing trading system...")

        # Initialize data provider if provided
        if data_provider is not None:
            self._data_provider = data_provider
            logger.info("Data provider initialized")

        # Initialize strategies
        self._strategies = create_strategy_adapters(
            self.config.sentiment_arb,
            self.config.contrarian,
        )
        logger.info(f"Strategies initialized: {list(self._strategies.keys())}")

        # Initialize signal router
        self._router = SignalRouterImpl(self.config.router)
        for strategy in self._strategies.values():
            self._router.add_strategy(strategy)
        logger.info("Signal router initialized")

        self._initialized = True
        logger.info("Trading system initialized successfully")

    def run_once(
        self,
        symbols: list[str] | None = None,
        as_of: datetime | None = None,
    ) -> PortfolioSignal:
        """
        Run one iteration of signal generation.

        Args:
            symbols: List of symbols to analyze (uses universe if None)
            as_of: Current timestamp (uses now if None)

        Returns:
            PortfolioSignal with aggregated signals
        """
        if not self._initialized:
            self.initialize()

        as_of = as_of or datetime.now()

        # Get universe if no symbols specified
        if symbols is None:
            if self._data_provider is None:
                raise RuntimeError("Data provider not initialized")
            symbols = self._data_provider.get_universe(self.config.data.default_universe)

        if not symbols:
            logger.warning("No symbols to analyze")
            return PortfolioSignal(signals=[], timestamp=as_of)

        # Generate and aggregate signals
        if self._router is None:
            raise RuntimeError("Signal router not initialized")
        if self._data_provider is None:
            raise RuntimeError("Data provider not initialized")
        portfolio = self._router.aggregate_signals(
            symbols,
            as_of,
            self._data_provider,
        )

        # Update state
        self._state.last_run = as_of

        logger.info(
            f"Generated {portfolio.signal_count} signals: "
            f"{portfolio.long_count} long, {portfolio.short_count} short"
        )

        return portfolio

    def run_backtest(
        self,
        strategy_name: str | None = None,
        symbols: list[str] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        initial_capital: float | None = None,
    ) -> BacktestResult:
        """
        Run backtest for a strategy.

        Args:
            strategy_name: Strategy to test (tests all if None)
            symbols: Symbols to trade
            start_date: Start date
            end_date: End date
            initial_capital: Starting capital

        Returns:
            BacktestResult
        """
        if not self._initialized:
            self.initialize()

        # Set defaults
        end_date = end_date or datetime.now()
        start_date = start_date or (end_date - timedelta(days=365))
        initial_capital = initial_capital or self.config.backtest.initial_capital

        # Get universe
        if symbols is None:
            if self._data_provider is None:
                raise RuntimeError("Data provider not initialized")
            symbols = self._data_provider.get_universe(self.config.data.default_universe)

        # Get strategy
        if strategy_name:
            if strategy_name not in self._strategies:
                raise ValueError(f"Unknown strategy: {strategy_name}")
            strategy = self._strategies[strategy_name]
        else:
            # Use combined router as strategy
            if self._router is None:
                raise RuntimeError("Signal router not initialized")
            strategy = CombinedStrategy(self._router, self._strategies)

        # Run backtest
        if self._data_provider is None:
            raise RuntimeError("Data provider not initialized")
        # Lazy import to avoid circular dependency
        from backtest.engine import BacktestEngineImpl

        engine = BacktestEngineImpl(self._data_provider, self.config.backtest)
        result = engine.run(
            strategy,
            symbols,
            start_date,
            end_date,
            initial_capital,
        )

        return result

    def connect_broker(self, broker: ExecutionClient) -> None:
        """
        Connect to a broker for live trading.

        Args:
            broker: Broker implementation
        """
        self._execution_client = broker
        success = broker.connect()
        if success:
            logger.info("Connected to broker")
        else:
            logger.error("Failed to connect to broker")
            raise ConnectionError("Failed to connect to broker")

    def execute_signals(
        self,
        portfolio: PortfolioSignal,
        dry_run: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Execute signals through the broker.

        Args:
            portfolio: PortfolioSignal to execute
            dry_run: If True, don't actually submit orders

        Returns:
            List of execution results
        """
        if self._execution_client is None and not dry_run:
            raise RuntimeError("No broker connected")

        results = []

        for signal in portfolio.signals:
            if not signal.is_entry:
                continue

            result = {
                "symbol": signal.symbol,
                "signal_type": signal.signal_type.value,
                "quantity": signal.quantity,
                "status": "pending",
            }

            if dry_run:
                result["status"] = "dry_run"
                result["message"] = "Order not submitted (dry run)"
            else:
                try:
                    from .types import Order

                    order = Order(
                        order_id=f"ORD_{signal.symbol}_{signal.timestamp.strftime('%Y%m%d%H%M%S')}",
                        symbol=signal.symbol,
                        side="BUY" if signal.signal_type == SignalType.BUY else "SELL",
                        quantity=signal.quantity or 100,
                        order_type="MARKET",
                        source_signal=signal.source,
                    )

                    # Type narrowing: we know _execution_client is not None here
                    assert self._execution_client is not None
                    submitted = self._execution_client.submit_order(order)
                    result["status"] = "submitted"
                    result["order_id"] = submitted.order_id

                except Exception as e:
                    result["status"] = "error"
                    result["message"] = str(e)

            results.append(result)

        return results

    def get_system_status(self) -> dict[str, Any]:
        """
        Get current system status.

        Returns:
            Dictionary with system status information
        """
        status = {
            "initialized": self._initialized,
            "strategies": list(self._strategies.keys()),
            "last_run": self._state.last_run.isoformat() if self._state.last_run else None,
            "broker_connected": (
                self._execution_client.is_connected() if self._execution_client else False
            ),
        }

        if self._execution_client and self._execution_client.is_connected():
            try:
                status["account_balance"] = self._execution_client.get_account_balance()
                status["total_equity"] = self._execution_client.get_total_equity()
                status["positions"] = len(self._execution_client.get_positions())
            except Exception as e:
                status["broker_error"] = str(e)

        return status

    def add_strategy(self, strategy: SignalGenerator) -> None:
        """Add a custom strategy"""
        if not self._initialized:
            self.initialize()

        self._strategies[strategy.name] = strategy
        if self._router is None:
            raise RuntimeError("Signal router not initialized")
        self._router.add_strategy(strategy)
        logger.info(f"Added strategy: {strategy.name}")

    def remove_strategy(self, strategy_name: str) -> None:
        """Remove a strategy"""
        if strategy_name in self._strategies:
            del self._strategies[strategy_name]
            if self._router is None:
                raise RuntimeError("Signal router not initialized")
            self._router.remove_strategy(strategy_name)
            logger.info(f"Removed strategy: {strategy_name}")

    def set_data_provider(self, data_provider: DataProvider) -> None:
        """
        Set or replace the data provider.

        Args:
            data_provider: DataProvider instance to use
        """
        self._data_provider = data_provider
        logger.info("Data provider set")

    def shutdown(self) -> None:
        """Shutdown the system gracefully"""
        logger.info("Shutting down trading system...")

        # Close data provider (if it has a close method)
        if self._data_provider is not None:
            close_method = getattr(self._data_provider, "close", None)
            if callable(close_method):
                close_method()  # type: ignore[call-arg]

        # Disconnect broker
        if self._execution_client is not None:
            self._execution_client.disconnect()

        self._initialized = False
        logger.info("Trading system shutdown complete")


class CombinedStrategy(SignalGenerator):
    """
    Wrapper that uses the router to combine multiple strategies.
    Used for backtesting the combined signal generation.
    """

    def __init__(
        self,
        router: SignalRouterImpl,
        strategies: dict[str, SignalGenerator],
    ):
        self._router = router
        self._strategies = strategies

    @property
    def name(self) -> str:
        return "combined"

    @property
    def time_horizon(self) -> str:
        return "multi"

    def generate_signals(
        self,
        symbols: list[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> list[TradingSignal]:
        """Generate signals using the router"""
        portfolio = self._router.aggregate_signals(symbols, as_of, data_provider)
        return portfolio.signals

    def update(self, new_data: dict[str, Any]) -> None:
        pass

    def get_state(self) -> dict[str, Any]:
        return {}

    def set_state(self, state: dict[str, Any]) -> None:
        pass

    def get_required_data(self) -> list[str]:
        return ["prices", "fundamentals", "sentiment"]


# Convenience functions


def create_system(config_path: str | None = None) -> TradingSystem:
    """
    Create and initialize a trading system.

    Args:
        config_path: Path to configuration file

    Returns:
        Initialized TradingSystem
    """
    system = TradingSystem(config_path=config_path)
    system.initialize()
    return system


def quick_backtest(
    strategy_name: str = "sentiment_arbitrage",
    symbols: list[str] | None = None,
    days: int = 365,
    initial_capital: float = 1000000.0,
) -> BacktestResult:
    """
    Run a quick backtest with sensible defaults.

    Args:
        strategy_name: Strategy to test
        symbols: Symbols to trade (uses CSI 300 if None)
        days: Number of days to backtest
        initial_capital: Starting capital

    Returns:
        BacktestResult
    """
    system = create_system()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    return system.run_backtest(
        strategy_name=strategy_name,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
    )
