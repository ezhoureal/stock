"""
Common module for Chinese Stock Trading System

Provides shared interfaces, types, and utilities for all components.

Usage:
    from common import TradingSystem, quick_backtest

    # Create and run the system
    system = TradingSystem()
    system.initialize()
    portfolio = system.run_once()

    # Run a quick backtest
    result = quick_backtest(strategy_name="sentiment_arbitrage", days=365)
    print(result.summary())
"""

from backtest.engine import BacktestEngineImpl, run_backtest
from data.providers.duckdb_provider import DuckDBDataProvider

from .config import (
    BacktestConfig,
    ContrarianConfig,
    DataConfig,
    ExecutionConfig,
    RouterConfig,
    SentimentArbConfig,
    StrategyConfig,
    SystemConfig,
)
from .interfaces import (
    BacktestEngine,
    BacktestResult,
    DataProvider,
    ExecutionClient,
    SignalGenerator,
    SignalRouter,
)
from .orchestrator import (
    TradingSystem,
    create_system,
    quick_backtest,
)
from .signal_router import SignalRouterImpl
from .strategy_adapters import (
    ContrarianAdapter,
    SentimentArbAdapter,
    create_strategy_adapters,
)
from .types import (
    Bar,
    Fundamentals,
    MarketData,
    Order,
    PortfolioSignal,
    Position,
    SentimentScore,
    SignalStrength,
    SignalType,
    TimeFrame,
    Trade,
    TradingSignal,
)

__all__ = [
    # Types
    "SignalType",
    "SignalStrength",
    "TradingSignal",
    "PortfolioSignal",
    "MarketData",
    "Fundamentals",
    "SentimentScore",
    "Bar",
    "TimeFrame",
    "Position",
    "Order",
    "Trade",
    # Interfaces
    "DataProvider",
    "SignalGenerator",
    "ExecutionClient",
    "SignalRouter",
    "BacktestEngine",
    "BacktestResult",
    # Config
    "RouterConfig",
    "BacktestConfig",
    "SystemConfig",
    "DataConfig",
    "ExecutionConfig",
    "StrategyConfig",
    "SentimentArbConfig",
    "ContrarianConfig",
    # Implementations
    "SignalRouterImpl",
    "SentimentArbAdapter",
    "ContrarianAdapter",
    "create_strategy_adapters",
    # Orchestrator
    "TradingSystem",
    "create_system",
    "quick_backtest",
    # Backtest (moved to backtest module)
    "BacktestEngineImpl",
    "run_backtest",
    # Data Provider (moved to data.providers module)
    "DuckDBDataProvider",
]
