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

from .types import (
    SignalType,
    SignalStrength,
    TradingSignal,
    PortfolioSignal,
    MarketData,
    Fundamentals,
    SentimentScore,
    Bar,
    TimeFrame,
    Position,
    Order,
    Trade,
)
from .interfaces import (
    DataProvider,
    SignalGenerator,
    ExecutionClient,
    SignalRouter,
    BacktestEngine,
    BacktestResult,
)
from .config import (
    RouterConfig,
    BacktestConfig,
    SystemConfig,
    DataConfig,
    ExecutionConfig,
    StrategyConfig,
    SentimentArbConfig,
    ContrarianConfig,
)
from .signal_router import SignalRouterImpl
from .strategy_adapters import (
    SentimentArbAdapter,
    ContrarianAdapter,
    create_strategy_adapters,
)
from .orchestrator import (
    TradingSystem,
    create_system,
    quick_backtest,
)
from backtest.engine import BacktestEngineImpl, run_backtest
from data.providers.duckdb_provider import DuckDBDataProvider

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
