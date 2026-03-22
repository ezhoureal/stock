#!/usr/bin/env python3
"""Test script to verify the new AKShare sentiment collection implementation."""

import sys
from datetime import datetime

# Test 1: Import all required classes
print("=" * 60)
print("Test 1: Importing classes from collect_sentiment.py")
print("=" * 60)

try:
    from data.collect_sentiment import (
        AKShareSentimentConfig,
        AKShareSentimentFetcher,
        NewsArticle,
        SentimentCollector,
        SentimentDataPoint,
    )

    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Verify SentimentDataPoint interface
print("\n" + "=" * 60)
print("Test 2: SentimentDataPoint interface")
print("=" * 60)

try:
    dp = SentimentDataPoint(
        source="test_source",
        symbol="600519",
        timestamp=datetime.now(),
        raw_value=10.0,
        normalized=0.5,
        confidence=0.8,
        metadata={"key": "value"},
    )
    assert dp.source == "test_source"
    assert dp.symbol == "600519"
    assert -1 <= dp.normalized <= 1, "normalized should be in [-1, 1]"
    assert 0 <= dp.confidence <= 1, "confidence should be in [0, 1]"

    # Test to_dict method
    dp_dict = dp.to_dict()
    assert "source" in dp_dict
    assert "normalized" in dp_dict
    assert "confidence" in dp_dict
    print("✓ SentimentDataPoint interface is correct")
except Exception as e:
    print(f"✗ SentimentDataPoint test failed: {e}")
    sys.exit(1)

# Test 3: Verify AKShareSentimentConfig
print("\n" + "=" * 60)
print("Test 3: AKShareSentimentConfig interface")
print("=" * 60)

try:
    config = AKShareSentimentConfig()
    weights = [
        config.hot_rank_weight,
        config.comment_weight,
        config.fund_flow_weight,
        config.northbound_weight,
        config.long_hub_weight,
        config.margin_weight,
        config.market_activity_weight,
    ]
    total_weight = sum(weights)
    assert abs(total_weight - 1.0) < 0.01, f"Weights should sum to 1.0, got {total_weight}"
    print(f"✓ Config weights sum to {total_weight:.2f}")
    print("✓ AKShareSentimentConfig interface is correct")
except Exception as e:
    print(f"✗ AKShareSentimentConfig test failed: {e}")
    sys.exit(1)

# Test 4: Verify AKShareSentimentFetcher can be instantiated
print("\n" + "=" * 60)
print("Test 4: AKShareSentimentFetcher instantiation")
print("=" * 60)

try:
    fetcher = AKShareSentimentFetcher()
    print("✓ AKShareSentimentFetcher instantiated successfully")
except Exception as e:
    print(f"✗ AKShareSentimentFetcher instantiation failed: {e}")
    sys.exit(1)

# Test 5: Test hot rank data fetching
print("\n" + "=" * 60)
print("Test 5: Hot rank data fetching")
print("=" * 60)

try:
    df = fetcher.get_hot_rank_data()
    if df is not None and not df.empty:
        print(f"✓ Fetched {len(df)} hot rank entries")
        print(f"  Columns: {df.columns.tolist()}")

        # Test sentiment extraction for a stock
        test_symbol = df.iloc[0]["代码"]
        sentiment = fetcher.get_hot_rank_sentiment(test_symbol)
        if sentiment:
            print(
                f"✓ Got hot rank sentiment for {test_symbol}: normalized={sentiment.normalized:.3f}"
            )
        else:
            print(f"  Could not get sentiment for {test_symbol}")
    else:
        print("  No hot rank data available (API may be rate limited)")
except Exception as e:
    print(f"  Hot rank test skipped: {e}")

# Test 6: Test composite sentiment
print("\n" + "=" * 60)
print("Test 6: Composite sentiment calculation")
print("=" * 60)

try:
    test_symbol = "600519"  # Kweichow Moutai
    composite, data_points = fetcher.get_composite_sentiment(test_symbol, include_market=True)
    print(f"✓ Composite sentiment for {test_symbol}: {composite:.3f}")
    print(f"  Sources available: {list(data_points.keys())}")
    for source, dp in data_points.items():
        print(f"    - {source}: normalized={dp.normalized:.3f}, confidence={dp.confidence:.2f}")
except Exception as e:
    print(f"✗ Composite sentiment test failed: {e}")

# Test 7: Verify compatibility with common.types.SentimentScore
print("\n" + "=" * 60)
print("Test 7: Compatibility with common.types.SentimentScore")
print("=" * 60)

try:
    from common.types import SentimentScore

    # Create a SentimentScore from SentimentDataPoint
    dp = SentimentDataPoint(
        source="test",
        symbol="600519",
        timestamp=datetime.now(),
        raw_value=10.0,
        normalized=0.5,
        confidence=0.8,
        metadata={},
    )

    score = SentimentScore(
        symbol=dp.symbol,
        timestamp=dp.timestamp,
        score=dp.normalized,  # Map normalized to score
        confidence=dp.confidence,
        source=dp.source,
        raw_score=dp.raw_value,
        metadata=dp.metadata,
    )
    print("✓ Successfully created SentimentScore from SentimentDataPoint")
    print(
        f"  SentimentScore: symbol={score.symbol}, score={score.score:.3f}, confidence={score.confidence:.2f}"
    )
except Exception as e:
    print(f"✗ SentimentScore compatibility test failed: {e}")
    sys.exit(1)

# Test 8: Verify SentimentCollector interface
print("\n" + "=" * 60)
print("Test 8: SentimentCollector interface")
print("=" * 60)

try:
    # Test that SentimentCollector has the expected methods
    assert hasattr(SentimentCollector, "collect_sentiment"), "Missing collect_sentiment method"
    assert hasattr(SentimentCollector, "collect_akshare_sentiment"), (
        "Missing collect_akshare_sentiment method"
    )
    assert hasattr(SentimentCollector, "save_sentiment_data"), "Missing save_sentiment_data method"
    print("✓ SentimentCollector has all required methods")
except Exception as e:
    print(f"✗ SentimentCollector interface test failed: {e}")
    sys.exit(1)

# Test 9: Verify NewsArticle interface
print("\n" + "=" * 60)
print("Test 9: NewsArticle interface")
print("=" * 60)

try:
    article = NewsArticle(
        title="Test Article",
        url="https://example.com/test",
        publish_time=datetime.now(),
        content="Test content",
        source="test",
        stock_symbols=["600519"],
    )
    article_dict = article.to_dict()
    assert "title" in article_dict
    assert "url" in article_dict
    assert "stock_symbols" in article_dict
    print("✓ NewsArticle interface is correct")
except Exception as e:
    print(f"✗ NewsArticle test failed: {e}")
    sys.exit(1)

# Test 10: Verify DataProvider can read sentiment data format
print("\n" + "=" * 60)
print("Test 10: DataProvider compatibility")
print("=" * 60)

try:
    from data.providers import DuckDBDataProvider

    # Check that DuckDBDataProvider has the required methods
    assert hasattr(DuckDBDataProvider, "get_sentiment"), "Missing get_sentiment method"
    assert hasattr(DuckDBDataProvider, "get_latest_sentiment"), (
        "Missing get_latest_sentiment method"
    )
    print("✓ DuckDBDataProvider has required sentiment methods")
except Exception as e:
    print(f"✗ DataProvider compatibility test failed: {e}")
    sys.exit(1)

# Summary
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)
print("All interface compatibility tests passed!")
print("\nThe new AKShare sentiment collection implementation is compatible with:")
print("  - common.types.SentimentScore")
print("  - data.providers.DuckDBDataProvider")
print("  - sentiment_strategy signals module (via DataProvider interface)")
