"""
DuckDB Data Provider stub for backward compatibility.

This is a minimal implementation to maintain compatibility with the
existing trading system while the data collection module is being refactored.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from common.interfaces import DataProvider
from common.types import Bar, Fundamentals, SentimentScore

logger = logging.getLogger(__name__)


class DuckDBDataProvider(DataProvider):
    """
    Minimal DuckDB data provider implementation.

    This is a stub implementation that provides empty results.
    The full implementation will be added as part of the data
    collection module refactoring.
    """

    def __init__(self, config: Any = None) -> None:
        """Initialize the data provider."""
        self.config = config or {}
        logger.warning("DuckDBDataProvider is using stub implementation")

    def get_prices(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: str = "1d",
    ) -> list:
        """Get price data (not implemented in stub)."""
        logger.warning("get_prices called on stub provider")
        return []

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """Get latest prices (not implemented in stub)."""
        logger.warning("get_latest_prices called on stub provider")
        return {}

    def get_fundamentals(
        self, symbols: list[str], as_of: datetime | None = None
    ) -> list[Fundamentals]:
        """Get fundamental data (not implemented in stub)."""
        logger.warning("get_fundamentals called on stub provider")
        return []

    def get_sentiment(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        source: str | None = None,
    ) -> list[SentimentScore]:
        """Get sentiment data (not implemented in stub)."""
        logger.warning("get_sentiment called on stub provider")
        return []

    def get_latest_sentiment(self, symbols: list[str]) -> dict[str, SentimentScore]:
        """Get latest sentiment (not implemented in stub)."""
        logger.warning("get_latest_sentiment called on stub provider")
        return {}

    def get_universe(self, universe_name: str = "csi300") -> list[str]:
        """Get universe (not implemented in stub)."""
        logger.warning("get_universe called on stub provider")
        return []

    def get_bars(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> list[Bar]:
        """Get bar data (not implemented in stub)."""
        logger.warning("get_bars called on stub provider")
        return []

    def close(self) -> None:
        """Close the data provider and release resources."""
        logger.debug("DuckDBDataProvider closed")
