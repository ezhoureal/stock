"""
Trading System Orchestrator

Main entry point for running the trading system. Coordinates all components:
- Data providers
- Signal generators (strategies)
- Signal routing/aggregation
- Execution (broker)
- Backtesting
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import logging
from pathlib import Path

from .types import TradingSignal, PortfolioSignal, SignalType
from .interfaces import (
    DataProvider,
    SignalGenerator,
    ExecutionClient,
    BacktestResult,
)
from .config import SystemConfig, BacktestConfig
from .signal_router import SignalRouterImpl
from backtest.engine import BacktestEngineImpl
from data.providers.duckdb_provider import DuckDBDataProvider
from .strategy_adapters import (
    SentimentArbAdapter,
    ContrarianAdapter,
    create_strategy_adapters,
)

logger = logging.getLogger(__name__)


@dataclass
class SystemState:
    """Current state of the trading system"""
    last_run: Optional[datetime] = None
    active_positions: Dict[str, Any] = None
    pending_orders: Dict[str, Any] = None
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
        config: Optional[SystemConfig] = None,
        config_path: Optional[str] = None,
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
        self._data_provider: Optional[DataProvider] = None
        self._strategies: Dict[str, SignalGenerator] = {}
        self._router: Optional[SignalRouterImpl] = None
        self._execution_client: Optional[ExecutionClient] = None
        self._state = SystemState()

        self._initialized = False

    def initialize(self) -> None:
        """
        Initialize all system components.

        This method must be called before running the system.
        """
        logger.info("Initializing trading system...")

        # Initialize data provider
        self._data_provider = DuckDBDataProvider(self.config.data)
        logger.info("Data provider initialized")

        # Initialize strategies
        self._strategies = create_strategy_adapters(
            self.config.sentiment_arb,
            self.config.contrarian,
        )
        logger.info(f"Strategies initialized: {list(self._strategies.keys())}")

        # Initialize signal router
        self._router = SignalRouterImpl(self.config.router)
        for name, strategy in self._strategies.items():
            self._router.add_strategy(strategy)
        logger.info("Signal router initialized")

        self._initialized = True
        logger.info("Trading system initialized successfully")

    def run_once(
        self,
        symbols: Optional[List[str]] = None,
        as_of: Optional[datetime] = None,
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
            symbols = self._data_provider.get_universe(
                self.config.data.default_universe
            )

        if not symbols:
            logger.warning("No symbols to analyze")
            return PortfolioSignal(signals=[], timestamp=as_of)

        # Generate and aggregate signals
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
        strategy_name: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        initial_capital: Optional[float] = None,
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
            symbols = self._data_provider.get_universe(
                self.config.data.default_universe
            )

        # Get strategy
        if strategy_name:
            if strategy_name not in self._strategies:
                raise ValueError(f"Unknown strategy: {strategy_name}")
            strategy = self._strategies[strategy_name]
        else:
            # Use combined router as strategy
            strategy = CombinedStrategy(self._router, self._strategies)

        # Run backtest
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
    ) -> List[Dict[str, Any]]:
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

                    submitted = self._execution_client.submit_order(order)
                    result["status"] = "submitted"
                    result["order_id"] = submitted.order_id

                except Exception as e:
                    result["status"] = "error"
                    result["message"] = str(e)

            results.append(result)

        return results

    def get_system_status(self) -> Dict[str, Any]:
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
                self._execution_client.is_connected()
                if self._execution_client else False
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
        self._router.add_strategy(strategy)
        logger.info(f"Added strategy: {strategy.name}")

    def remove_strategy(self, strategy_name: str) -> None:
        """Remove a strategy"""
        if strategy_name in self._strategies:
            del self._strategies[strategy_name]
            self._router.remove_strategy(strategy_name)
            logger.info(f"Removed strategy: {strategy_name}")

    def shutdown(self) -> None:
        """Shutdown the system gracefully"""
        logger.info("Shutting down trading system...")

        # Close data provider
        if self._data_provider:
            if hasattr(self._data_provider, 'close'):
                self._data_provider.close()

        # Disconnect broker
        if self._execution_client:
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
        strategies: Dict[str, SignalGenerator],
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
        symbols: List[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> List[TradingSignal]:
        """Generate signals using the router"""
        portfolio = self._router.aggregate_signals(symbols, as_of, data_provider)
        return portfolio.signals

    def update(self, new_data: Dict[str, Any]) -> None:
        pass

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_state(self, state: Dict[str, Any]) -> None:
        pass

    def get_required_data(self) -> List[str]:
        return ["prices", "fundamentals", "sentiment"]


# Convenience functions

def create_system(config_path: Optional[str] = None) -> TradingSystem:
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
    symbols: Optional[List[str]] = None,
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
