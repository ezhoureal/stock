"""
Data collection module for Chinese A-share stock data.

Provides sentiment data collection using AKShare APIs, storing results
in DuckDB for use by trading strategies. Also provides verdict analysis
combining sentiment and valuation scores.

Note: This module uses lazy imports to avoid circular dependencies with
the common module. Import classes directly from their submodules:
- from data.sentiment_collector import SentimentCollector
- from data.storage import SentimentStorage
- from data.providers import SentimentDataProvider
- from data.verdict import VerdictCalculator
"""

__all__ = ["SentimentCollector", "SentimentStorage", "SentimentDataProvider", "VerdictCalculator"]


def __getattr__(name: str):
    """Lazy import to avoid circular dependencies."""
    if name == "SentimentCollector":
        from data.sentiment_collector import SentimentCollector

        return SentimentCollector
    if name == "SentimentStorage":
        from data.storage import SentimentStorage

        return SentimentStorage
    if name == "SentimentDataProvider":
        from data.providers import SentimentDataProvider

        return SentimentDataProvider
    if name == "VerdictCalculator":
        from data.verdict import VerdictCalculator

        return VerdictCalculator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
