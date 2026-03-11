"""
Chinese Stock Sentiment Trading System - Strategy Module

This module provides sentiment-based trading algorithms for Chinese A-share stocks.

Core Components:
- ValuationCalculator: Calculate intrinsic value and undervalued/overvalued scores
- SentimentAnalyzer: Analyze sentiment from news, social media, and search data
- SignalGenerator: Generate buy/sell signals by combining sentiment and valuation

Strategy: Contrarian
- Buy when sentiment is bearish + fundamentals are undervalued
- Sell when sentiment is bullish + fundamentals are overvalued

Usage:
    from strategy import ValuationCalculator, SentimentAnalyzer, SignalGenerator
    from strategy.dataclasses import ValuationMetrics, SectorMetrics

    # Initialize components
    valuation_calc = ValuationCalculator()
    sentiment_analyzer = SentimentAnalyzer()
    signal_generator = SignalGenerator(sentiment_analyzer, valuation_calc)

    # Generate signals
    signal = signal_generator.generate_signal(symbol, price, sentiment, valuation)
"""

from common.types import Position, TradingSignal

from .sentiment import (
    SentimentAnalyzer,
    SentimentConfig,
    SentimentDataParser,
    SentimentResult,
    SentimentSource,
)
from .sentiment import load_config as load_sentiment_config
from .signals import InternalPosition, SignalConfig, SignalGenerator
from .signals import load_config as load_signal_config
from .valuation import (
    SectorMetrics,
    ValuationCalculator,
    ValuationConfig,
    ValuationMetrics,
    ValuationScore,
)
from .valuation import load_config as load_valuation_config

__version__ = "1.0.0"
__all__ = [
    # Valuation
    "ValuationCalculator",
    "ValuationConfig",
    "ValuationMetrics",
    "SectorMetrics",
    "ValuationScore",
    "load_valuation_config",
    # Sentiment
    "SentimentAnalyzer",
    "SentimentConfig",
    "SentimentSource",
    "SentimentResult",
    "SentimentDataParser",
    "load_sentiment_config",
    # Signals
    "SignalGenerator",
    "SignalConfig",
    "TradingSignal",
    "Position",
    "InternalPosition",
    "load_signal_config",
]
