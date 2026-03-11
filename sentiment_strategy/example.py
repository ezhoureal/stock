"""
Example script demonstrating the full Chinese Stock Sentiment Trading System

This example shows how to use the strategy modules together to generate trading signals.
"""

from datetime import datetime

from common.types import SignalType
from sentiment_strategy.sentiment import SentimentAnalyzer, SentimentSource
from sentiment_strategy.signals import InternalPosition, SignalGenerator

# Import strategy components
from sentiment_strategy.valuation import SectorMetrics, ValuationCalculator, ValuationMetrics


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def example_buy_signal():
    """
    Example 1: Generate a BUY signal
    Scenario: Bearish sentiment + Undervalued fundamentals
    """
    print_section("EXAMPLE 1: BUY SIGNAL (Contrarian)")

    # Initialize components
    valuation_calc = ValuationCalculator()
    sentiment_analyzer = SentimentAnalyzer()
    signal_generator = SignalGenerator(sentiment_analyzer, valuation_calc)

    # Company: Undervalued (low PE, high dividend vs sector)
    company = ValuationMetrics(
        pe_ratio=12.0,  # Low P/E vs sector median
        pb_ratio=1.8,  # Moderate P/B
        dividend_yield=0.035,  # High dividend yield (3.5%)
        peg_ratio=1.1,  # Low PEG (growth is cheap)
        eps=2.5,
        book_value_per_share=10.0,
        annual_dividend=0.6,
    )

    # Sector: Higher valuation
    sector = SectorMetrics(
        pe_ratio=25.0,  # Sector P/E is higher
        pb_ratio=2.5,
        dividend_yield=0.015,
        peg_ratio=2.0,
    )

    # Calculate valuation
    valuation = valuation_calc.calculate_valuation(company, sector)

    print("\n--- Valuation Analysis ---")
    print(f"Company PE: {company.pe_ratio:.1f} (Sector: {sector.pe_ratio:.1f})")
    print(f"Company P/B: {company.pb_ratio:.1f} (Sector: {sector.pb_ratio:.1f})")
    print(f"Company Dividend: {company.dividend_yield:.1%} (Sector: {sector.dividend_yield:.1%})")
    print(f"Company PEG: {company.peg_ratio:.1f} (Sector: {sector.peg_ratio:.1f})")
    print(f"\nValuation Score (V): {valuation.composite_score:.3f}")
    print(f"Interpretation: {valuation.interpretation}")

    # Sentiment: Bearish (panic selling)
    bearish_sources = [
        SentimentSource(
            source="news",
            timestamp=datetime.now(),
            raw_sentiment=-0.4,
            normalized=-0.4,
            confidence=0.8,
            metadata={"article_count": 5, "headlines": "Company faces regulatory scrutiny"},
        ),
        SentimentSource(
            source="social",
            timestamp=datetime.now(),
            raw_sentiment=-0.6,
            normalized=-0.6,
            confidence=0.7,
            metadata={"platform": "weibo", "post_count": 150, "sentiment": "Fearful"},
        ),
        SentimentSource(
            source="search",
            timestamp=datetime.now(),
            raw_sentiment=-0.7,
            normalized=-0.7,
            confidence=0.6,
            metadata={"volume_ratio": 2.5, "price_change": -0.08},  # Panic search
        ),
        SentimentSource(
            source="forum",
            timestamp=datetime.now(),
            raw_sentiment=-0.5,
            normalized=-0.5,
            confidence=0.5,
            metadata={"post_count": 80},
        ),
    ]

    sentiment = sentiment_analyzer.calculate_sentiment("600519.SH", bearish_sources)

    print("\n--- Sentiment Analysis ---")
    print(f"News sentiment: {bearish_sources[0].normalized:.2f}")
    print(f"Social sentiment: {bearish_sources[1].normalized:.2f}")
    print(f"Search sentiment: {bearish_sources[2].normalized:.2f}")
    print(f"Forum sentiment: {bearish_sources[3].normalized:.2f}")
    print(f"\nTotal Score: {sentiment.total_score:.2f}")
    print(f"Smoothed Score: {sentiment.smoothed_score:.2f}")
    print(f"Rate of Change: {sentiment.roc:.2f}")
    print(f"Interpretation: {sentiment.interpretation}")

    # Generate signal
    current_price = company.pe_ratio * company.eps  # Approximate current price
    signal = signal_generator.generate_signal(
        symbol="600519.SH",
        current_price=current_price,
        sentiment=sentiment,
        valuation=valuation,
        portfolio_value=100000.0,
    )

    print("\n--- Trading Signal ---")
    print(f"Signal Type: {signal.signal_type}")
    print(f"Strength: {signal.strength:.1f}/100")
    print(f"Confidence: {signal.confidence:.2f}")
    print(f"Entry Price: ¥{signal.entry_price:.2f}")
    print(f"Stop Loss: ¥{signal.stop_loss:.2f}")
    print(f"Take Profit: ¥{signal.take_profit:.2f}")
    if signal.metadata.get("quantity"):
        quantity = signal.metadata["quantity"]
        position_value = quantity * current_price
        print(f"Quantity: {quantity} shares")
        print(f"Position Value: ¥{position_value:.2f}")
    print("\nReasons:")
    for reason in signal.reasons:
        print(f"  - {reason}")

    return signal


def example_sell_signal():
    """
    Example 2: Generate a SELL signal
    Scenario: Bullish sentiment + Overvalued fundamentals
    """
    print_section("EXAMPLE 2: SELL SIGNAL (Contrarian)")

    # Initialize components
    valuation_calc = ValuationCalculator()
    sentiment_analyzer = SentimentAnalyzer()
    signal_generator = SignalGenerator(sentiment_analyzer, valuation_calc)

    # Company: Overvalued (high PE, low dividend vs sector)
    company = ValuationMetrics(
        pe_ratio=45.0,  # High P/E vs sector median
        pb_ratio=4.5,  # High P/B
        dividend_yield=0.008,  # Low dividend yield (0.8%)
        peg_ratio=3.0,  # High PEG (expensive growth)
        eps=1.0,
        book_value_per_share=5.0,
        annual_dividend=0.08,
    )

    # Sector: Lower valuation
    sector = SectorMetrics(
        pe_ratio=25.0,  # Sector P/E is lower
        pb_ratio=2.5,
        dividend_yield=0.015,
        peg_ratio=2.0,
    )

    # Calculate valuation
    valuation = valuation_calc.calculate_valuation(company, sector)

    print("\n--- Valuation Analysis ---")
    print(f"Company PE: {company.pe_ratio:.1f} (Sector: {sector.pe_ratio:.1f})")
    print(f"Company P/B: {company.pb_ratio:.1f} (Sector: {sector.pb_ratio:.1f})")
    print(f"Company Dividend: {company.dividend_yield:.1%} (Sector: {sector.dividend_yield:.1%})")
    print(f"Company PEG: {company.peg_ratio:.1f} (Sector: {sector.peg_ratio:.1f})")
    print(f"\nValuation Score (V): {valuation.composite_score:.3f}")
    print(f"Interpretation: {valuation.interpretation}")

    # Sentiment: Bullish (euphoria)
    bullish_sources = [
        SentimentSource(
            source="news",
            timestamp=datetime.now(),
            raw_sentiment=0.7,
            normalized=0.7,
            confidence=0.8,
            metadata={"article_count": 8, "headlines": "Company announces breakthrough"},
        ),
        SentimentSource(
            source="social",
            timestamp=datetime.now(),
            raw_sentiment=0.6,
            normalized=0.6,
            confidence=0.7,
            metadata={"platform": "weibo", "post_count": 300, "sentiment": "Excited"},
        ),
        SentimentSource(
            source="search",
            timestamp=datetime.now(),
            raw_sentiment=0.5,
            normalized=0.5,
            confidence=0.6,
            metadata={"volume_ratio": 1.8, "price_change": 0.06},  # FOMO
        ),
        SentimentSource(
            source="forum",
            timestamp=datetime.now(),
            raw_sentiment=0.4,
            normalized=0.4,
            confidence=0.5,
            metadata={"post_count": 120},
        ),
    ]

    sentiment = sentiment_analyzer.calculate_sentiment("000858.SZ", bullish_sources)

    print("\n--- Sentiment Analysis ---")
    print(f"News sentiment: {bullish_sources[0].normalized:.2f}")
    print(f"Social sentiment: {bullish_sources[1].normalized:.2f}")
    print(f"Search sentiment: {bullish_sources[2].normalized:.2f}")
    print(f"Forum sentiment: {bullish_sources[3].normalized:.2f}")
    print(f"\nTotal Score: {sentiment.total_score:.2f}")
    print(f"Smoothed Score: {sentiment.smoothed_score:.2f}")
    print(f"Rate of Change: {sentiment.roc:.2f}")
    print(f"Interpretation: {sentiment.interpretation}")

    # Generate signal
    current_price = company.pe_ratio * company.eps
    signal = signal_generator.generate_signal(
        symbol="000858.SZ",
        current_price=current_price,
        sentiment=sentiment,
        valuation=valuation,
        portfolio_value=100000.0,
    )

    print("\n--- Trading Signal ---")
    print(f"Signal Type: {signal.signal_type}")
    print(f"Strength: {signal.strength:.1f}/100")
    print(f"Confidence: {signal.confidence:.2f}")
    print(f"Entry Price: ¥{signal.entry_price:.2f}")
    print(f"Stop Loss: ¥{signal.stop_loss:.2f}")
    print(f"Take Profit: ¥{signal.take_profit:.2f}")
    if signal.metadata.get("quantity"):
        quantity = signal.metadata["quantity"]
        position_value = quantity * current_price
        print(f"Quantity: {quantity} shares")
        print(f"Position Value: ¥{position_value:.2f}")
    print("\nReasons:")
    for reason in signal.reasons:
        print(f"  - {reason}")

    return signal


def example_hold_signal():
    """
    Example 3: Generate a HOLD signal
    Scenario: Neutral sentiment + fair valuation
    """
    print_section("EXAMPLE 3: HOLD SIGNAL (No Action)")

    # Initialize components
    valuation_calc = ValuationCalculator()
    sentiment_analyzer = SentimentAnalyzer()
    signal_generator = SignalGenerator(sentiment_analyzer, valuation_calc)

    # Company: Fairly valued
    company = ValuationMetrics(
        pe_ratio=25.0,  # At sector median
        pb_ratio=2.5,  # At sector median
        dividend_yield=0.015,  # At sector median
        peg_ratio=2.0,  # At sector median
        eps=2.0,
        book_value_per_share=8.0,
        annual_dividend=0.3,
    )

    # Sector: Similar valuation
    sector = SectorMetrics(pe_ratio=25.0, pb_ratio=2.5, dividend_yield=0.015, peg_ratio=2.0)

    # Calculate valuation
    valuation = valuation_calc.calculate_valuation(company, sector)

    print("\n--- Valuation Analysis ---")
    print(f"Valuation Score (V): {valuation.composite_score:.3f}")
    print(f"Interpretation: {valuation.interpretation}")

    # Sentiment: Neutral
    neutral_sources = [
        SentimentSource("news", datetime.now(), 0.1, 0.1, 0.6, {}),
        SentimentSource("social", datetime.now(), -0.1, -0.1, 0.5, {}),
        SentimentSource("search", datetime.now(), 0.0, 0.0, 0.5, {}),
        SentimentSource("forum", datetime.now(), 0.2, 0.2, 0.4, {}),
    ]

    sentiment = sentiment_analyzer.calculate_sentiment("600036.SH", neutral_sources)

    print("\n--- Sentiment Analysis ---")
    print(f"Smoothed Score: {sentiment.smoothed_score:.2f}")
    print(f"Interpretation: {sentiment.interpretation}")

    # Generate signal
    current_price = company.pe_ratio * company.eps
    signal = signal_generator.generate_signal(
        symbol="600036.SH",
        current_price=current_price,
        sentiment=sentiment,
        valuation=valuation,
        portfolio_value=100000.0,
    )

    print("\n--- Trading Signal ---")
    print(f"Signal Type: {signal.signal_type}")
    print(f"Strength: {signal.strength:.1f}/100")
    print(f"Reasons: {signal.reasons}")

    return signal


def example_position_tracking():
    """
    Example 4: Track a position and check exit conditions
    """
    print_section("EXAMPLE 4: Position Tracking & Exit")

    # Initialize components
    sentiment_analyzer = SentimentAnalyzer()
    valuation_calc = ValuationCalculator()
    signal_generator = SignalGenerator(sentiment_analyzer, valuation_calc)

    # Create a position
    position = InternalPosition(
        symbol="600519.SH",
        entry_type=SignalType.BUY,
        entry_price=100.0,
        entry_date=datetime.now(),
        quantity=100,
        stop_loss=92.0,  # 8% stop-loss
        take_profit=115.0,  # 15% take-profit
        original_signal_strength=75.0,
    )

    # Add to signal generator
    signal_generator.add_position(position)

    print(f"\nPosition: {position.symbol} ({position.entry_type.value})")
    print(f"Entry Price: Y{position.entry_price:.2f}")
    print(f"Quantity: {position.quantity} shares")
    print(f"Stop Loss: Y{position.stop_loss:.2f}")
    print(f"Take Profit: Y{position.take_profit:.2f}")

    # Scenario 1: Price hits stop-loss
    print("\n--- Scenario 1: Stop-Loss Hit ---")
    current_price = 91.5  # Below stop-loss
    exit_result = signal_generator._check_exit_conditions(position, current_price)
    if exit_result:
        exit_type, reasons = exit_result
        print(f"Exit Signal: {exit_type.value}")
        print(f"Reason: {reasons[0]}")

    # Scenario 2: Price hits take-profit
    print("\n--- Scenario 2: Take-Profit Hit ---")
    current_price = 116.0  # Above take-profit
    exit_result = signal_generator._check_exit_conditions(position, current_price)
    if exit_result:
        exit_type, reasons = exit_result
        print(f"Exit Signal: {exit_type.value}")
        print(f"Reason: {reasons[0]}")

    # Scenario 3: Sentiment reversal
    print("\n--- Scenario 3: Sentiment Reversal ---")
    # Current price is neutral
    current_price = 105.0

    # Sentiment has improved (become bullish)
    bullish_sources = [
        SentimentSource("news", datetime.now(), 0.6, 0.6, 0.8, {}),
        SentimentSource("social", datetime.now(), 0.5, 0.5, 0.7, {}),
        SentimentSource("search", datetime.now(), 0.4, 0.4, 0.6, {}),
        SentimentSource("forum", datetime.now(), 0.3, 0.3, 0.5, {}),
    ]

    # Add some history for ROC calculation
    for _ in range(3):
        bearish_sources = [
            SentimentSource("news", datetime.now(), -0.3, -0.3, 0.7, {}),
            SentimentSource("social", datetime.now(), -0.4, -0.4, 0.6, {}),
            SentimentSource("search", datetime.now(), -0.5, -0.5, 0.5, {}),
            SentimentSource("forum", datetime.now(), -0.4, -0.4, 0.5, {}),
        ]
        sentiment_analyzer.calculate_sentiment("600519.SH", bearish_sources)

    # Now check with bullish sentiment
    sentiment = sentiment_analyzer.calculate_sentiment("600519.SH", bullish_sources)

    print(f"New Sentiment: {sentiment.smoothed_score:.2f} (was bearish)")
    print(f"Rate of Change: {sentiment.roc:.2f}")

    exit_result = signal_generator._check_exit_conditions(
        position, current_price, sentiment=sentiment
    )
    if exit_result:
        exit_type, reasons = exit_result
        print(f"Exit Signal: {exit_type.value}")
        print(f"Reason: {reasons[0]}")
    else:
        print("No exit signal - sentiment not reversed enough")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print(" CHINESE STOCK SENTIMENT TRADING SYSTEM - EXAMPLES")
    print("=" * 60)

    # Run examples
    example_buy_signal()
    example_sell_signal()
    example_hold_signal()
    example_position_tracking()

    print("\n" + "=" * 60)
    print(" EXAMPLES COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Customize parameters in config.json")
    print("2. Integrate with real data sources (Tushare, AkShare)")
    print("3. Backtest the strategy")
    print("4. Deploy for paper trading")
    print()


if __name__ == "__main__":
    main()
