"""
Abstract Interfaces for Trading System Components

Defines the contracts that each component must implement.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pandas as pd

from .types import (
    Bar,
    Fundamentals,
    Order,
    PortfolioSignal,
    Position,
    SentimentScore,
    TimeFrame,
    Trade,
    TradingSignal,
)


class DataProvider(ABC):
    """
    Abstract interface for data access.

    All data sources (DuckDB, API, file-based) must implement this interface.
    """

    @abstractmethod
    def get_prices(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: TimeFrame = TimeFrame.DAY_1,
    ) -> pd.DataFrame:
        """
        Get price data for symbols.

        Args:
            symbols: List of stock symbols
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe

        Returns:
            DataFrame with MultiIndex (symbol, timestamp) and columns:
            open, high, low, close, volume, amount
        """
        pass

    @abstractmethod
    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """
        Get latest prices for symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to latest price
        """
        pass

    @abstractmethod
    def get_fundamentals(
        self,
        symbols: list[str],
        as_of: datetime | None = None,
    ) -> list[Fundamentals]:
        """
        Get fundamental data for symbols.

        Args:
            symbols: List of stock symbols
            as_of: Get fundamentals as of this date (latest if None)

        Returns:
            List of Fundamentals objects
        """
        pass

    @abstractmethod
    def get_sentiment(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        source: str | None = None,
    ) -> list[SentimentScore]:
        """
        Get sentiment scores for symbols.

        Args:
            symbols: List of stock symbols
            start: Start datetime
            end: End datetime
            source: Filter by source ("news", "social", etc.)

        Returns:
            List of SentimentScore objects
        """
        pass

    @abstractmethod
    def get_latest_sentiment(
        self,
        symbols: list[str],
    ) -> dict[str, SentimentScore]:
        """
        Get latest sentiment scores for symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to latest SentimentScore
        """
        pass

    @abstractmethod
    def get_universe(self, universe_name: str = "csi300") -> list[str]:
        """
        Get list of symbols in a universe.

        Args:
            universe_name: Name of the universe (e.g., "csi300", "all")

        Returns:
            List of stock symbols
        """
        pass

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: TimeFrame = TimeFrame.DAY_1,
    ) -> list[Bar]:
        """
        Get bar data for a single symbol.

        Args:
            symbol: Stock symbol
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe

        Returns:
            List of Bar objects
        """
        pass

    def stream_bars(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: TimeFrame = TimeFrame.DAY_1,
    ) -> Iterator[Bar]:
        """
        Stream bar data for multiple symbols in chronological order.

        Args:
            symbols: List of stock symbols
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe

        Yields:
            Bar objects in chronological order
        """
        # Default implementation - can be overridden for efficiency
        all_bars = []
        for symbol in symbols:
            bars = self.get_bars(symbol, start, end, timeframe)
            all_bars.extend(bars)
        all_bars.sort(key=lambda b: b.timestamp)
        for bar in all_bars:
            yield bar


class SignalGenerator(ABC):
    """
    Abstract interface for signal-generating strategies.

    Both sentiment_arbitrage and strategy modules implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this strategy"""
        pass

    @property
    @abstractmethod
    def time_horizon(self) -> str:
        """Strategy time horizon: 'high_frequency', 'medium_term', 'long_term'"""
        pass

    @abstractmethod
    def generate_signals(
        self,
        symbols: list[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> list[TradingSignal]:
        """
        Generate trading signals for given symbols.

        Args:
            symbols: List of stock symbols to analyze
            as_of: Current timestamp
            data_provider: Data source for fetching required data

        Returns:
            List of TradingSignal objects
        """
        pass

    @abstractmethod
    def update(self, new_data: dict[str, Any]) -> None:
        """
        Update internal state with new data.

        Called when new data arrives (for real-time updates).

        Args:
            new_data: Dictionary of new data (format depends on strategy)
        """
        pass

    @abstractmethod
    def get_state(self) -> dict[str, Any]:
        """
        Serialize internal state for persistence.

        Returns:
            Dictionary representing internal state
        """
        pass

    @abstractmethod
    def set_state(self, state: dict[str, Any]) -> None:
        """
        Restore internal state from serialized form.

        Args:
            state: Dictionary from get_state()
        """
        pass

    @abstractmethod
    def get_required_data(self) -> list[str]:
        """
        Get list of required data types for this strategy.

        Returns:
            List of data types: ["prices", "fundamentals", "sentiment", etc.]
        """
        pass

    def validate_signals(self, signals: list[TradingSignal]) -> list[TradingSignal]:
        """
        Validate and filter signals (optional override).

        Args:
            signals: List of generated signals

        Returns:
            Validated/filtered signals
        """
        return signals


class ExecutionClient(ABC):
    """
    Abstract interface for broker execution.

    All broker implementations (Futu, mock, etc.) must implement this interface.
    """

    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to the broker.

        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if connected to broker.

        Returns:
            True if connected
        """
        pass

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """
        Submit an order for execution.

        Args:
            order: Order to submit

        Returns:
            Updated order with broker-assigned ID
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancellation successful
        """
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Order:
        """
        Get order status.

        Args:
            order_id: Order ID to retrieve

        Returns:
            Current order state
        """
        pass

    @abstractmethod
    def get_orders(self, symbol: str | None = None) -> list[Order]:
        """
        Get all orders or orders for a specific symbol.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of orders
        """
        pass

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """
        Get current positions.

        Returns:
            List of current positions
        """
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None:
        """
        Get position for a specific symbol.

        Args:
            symbol: Symbol to retrieve

        Returns:
            Position if exists, None otherwise
        """
        pass

    @abstractmethod
    def get_account_balance(self) -> float:
        """
        Get available account balance.

        Returns:
            Available cash balance
        """
        pass

    @abstractmethod
    def get_total_equity(self) -> float:
        """
        Get total account equity.

        Returns:
            Total equity (cash + positions)
        """
        pass


class SignalRouter(ABC):
    """
    Abstract interface for signal aggregation and routing.

    Collects signals from multiple strategies and produces unified portfolio signals.
    """

    @abstractmethod
    def add_strategy(self, strategy: SignalGenerator) -> None:
        """
        Add a signal-generating strategy.

        Args:
            strategy: Strategy to add
        """
        pass

    @abstractmethod
    def remove_strategy(self, strategy_name: str) -> None:
        """
        Remove a strategy.

        Args:
            strategy_name: Name of strategy to remove
        """
        pass

    @abstractmethod
    def aggregate_signals(
        self,
        symbols: list[str],
        as_of: datetime,
        data_provider: DataProvider,
    ) -> PortfolioSignal:
        """
        Collect and aggregate signals from all strategies.

        Args:
            symbols: List of symbols to analyze
            as_of: Current timestamp
            data_provider: Data source

        Returns:
            Aggregated portfolio signal
        """
        pass

    @abstractmethod
    def set_weights(self, weights: dict[str, float]) -> None:
        """
        Set strategy weights for aggregation.

        Args:
            weights: Dictionary mapping strategy name to weight
        """
        pass


class BacktestEngine(ABC):
    """
    Abstract interface for backtesting.

    Allows strategies to be tested against historical data.
    """

    @abstractmethod
    def run(
        self,
        strategy: SignalGenerator,
        symbols: list[str],
        start: datetime,
        end: datetime,
        initial_capital: float = 1000000.0,
    ) -> "BacktestResult":
        """
        Run backtest for a strategy.

        Args:
            strategy: Strategy to test
            symbols: List of symbols to trade
            start: Start datetime
            end: End datetime
            initial_capital: Starting capital

        Returns:
            BacktestResult with performance metrics
        """
        pass

    @abstractmethod
    def set_commission(self, commission_rate: float, min_commission: float = 0.0) -> None:
        """
        Set commission rates.

        Args:
            commission_rate: Commission as fraction of trade value
            min_commission: Minimum commission per trade
        """
        pass

    @abstractmethod
    def set_slippage(self, slippage_rate: float) -> None:
        """
        Set slippage model.

        Args:
            slippage_rate: Slippage as fraction of price
        """
        pass


class BacktestResult:
    """Container for backtest results"""

    def __init__(self):
        self.initial_capital: float = 0.0
        self.final_capital: float = 0.0
        self.total_return: float = 0.0
        self.annualized_return: float = 0.0
        self.sharpe_ratio: float = 0.0
        self.max_drawdown: float = 0.0
        self.win_rate: float = 0.0
        self.total_trades: int = 0
        self.profit_factor: float = 0.0
        self.trades: list[Trade] = []
        self.equity_curve: list[dict[str, Any]] = []
        self.positions_history: list[dict[str, Any]] = []
        self.signals: list[TradingSignal] = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_return": self.total_return,
            "annualized_return": self.annualized_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "profit_factor": self.profit_factor,
        }

    def summary(self) -> str:
        """Generate summary string"""
        return f"""
Backtest Results
================
Initial Capital:    ¥{self.initial_capital:,.2f}
Final Capital:      ¥{self.final_capital:,.2f}
Total Return:       {self.total_return:.2%}
Annualized Return:  {self.annualized_return:.2%}
Sharpe Ratio:       {self.sharpe_ratio:.2f}
Max Drawdown:       {self.max_drawdown:.2%}
Win Rate:           {self.win_rate:.2%}
Total Trades:       {self.total_trades}
Profit Factor:      {self.profit_factor:.2f}
"""
