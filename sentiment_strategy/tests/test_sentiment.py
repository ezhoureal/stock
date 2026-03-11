"""
Unit tests for the sentiment_strategy module.

Tests cover:
- SentimentSource validation (confidence must be 0-1)
- SentimentAnalyzer basic functionality
- Edge cases like empty data
"""

from datetime import datetime

import pytest

from sentiment_strategy.sentiment import (
    SentimentAnalyzer,
    SentimentConfig,
    SentimentResult,
    SentimentSource,
)


class TestSentimentSource:
    """Tests for SentimentSource dataclass."""

    def test_valid_confidence_zero(self) -> None:
        """Test that confidence 0.0 is valid."""
        source = SentimentSource(
            source="news",
            timestamp=datetime.now(),
            raw_sentiment=0.5,
            normalized=0.5,
            confidence=0.0,
            metadata=None,
        )
        assert source.confidence == 0.0

    def test_valid_confidence_one(self) -> None:
        """Test that confidence 1.0 is valid."""
        source = SentimentSource(
            source="news",
            timestamp=datetime.now(),
            raw_sentiment=0.5,
            normalized=0.5,
            confidence=1.0,
            metadata=None,
        )
        assert source.confidence == 1.0

    def test_valid_confidence_middle(self) -> None:
        """Test that confidence 0.5 is valid."""
        source = SentimentSource(
            source="news",
            timestamp=datetime.now(),
            raw_sentiment=0.5,
            normalized=0.5,
            confidence=0.5,
            metadata=None,
        )
        assert source.confidence == 0.5

    def test_invalid_confidence_negative(self) -> None:
        """Test that negative confidence raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0 and 1"):
            SentimentSource(
                source="news",
                timestamp=datetime.now(),
                raw_sentiment=0.5,
                normalized=0.5,
                confidence=-0.1,
                metadata=None,
            )

    def test_invalid_confidence_above_one(self) -> None:
        """Test that confidence > 1 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0 and 1"):
            SentimentSource(
                source="news",
                timestamp=datetime.now(),
                raw_sentiment=0.5,
                normalized=0.5,
                confidence=1.5,
                metadata=None,
            )


class TestSentimentAnalyzer:
    """Tests for SentimentAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> SentimentAnalyzer:
        """Create a SentimentAnalyzer instance for testing."""
        return SentimentAnalyzer()

    @pytest.fixture
    def config(self) -> SentimentConfig:
        """Create a SentimentConfig instance for testing."""
        return SentimentConfig()

    def test_normalize_sentiment_positive(self, analyzer: SentimentAnalyzer) -> None:
        """Test normalizing positive sentiment."""
        result = analyzer.normalize_sentiment(0.5, -1.0, 1.0)
        assert result == 0.5

    def test_normalize_sentiment_negative(self, analyzer: SentimentAnalyzer) -> None:
        """Test normalizing negative sentiment."""
        result = analyzer.normalize_sentiment(-0.5, -1.0, 1.0)
        assert result == -0.5

    def test_normalize_sentiment_clips_high(self, analyzer: SentimentAnalyzer) -> None:
        """Test that high values are clipped."""
        result = analyzer.normalize_sentiment(2.0, -1.0, 1.0)
        assert result == 1.0

    def test_normalize_sentiment_clips_low(self, analyzer: SentimentAnalyzer) -> None:
        """Test that low values are clipped."""
        result = analyzer.normalize_sentiment(-2.0, -1.0, 1.0)
        assert result == -1.0

    def test_calculate_total_score_bullish(self, analyzer: SentimentAnalyzer) -> None:
        """Test calculating bullish total score."""
        sentiments = {"news": 0.8, "social": 0.6}
        weights = {"news": 0.6, "social": 0.4}
        result = analyzer.calculate_total_score(sentiments, weights)
        # (0.8 * 0.6 + 0.6 * 0.4) / 1.0 * 5 = 3.6
        assert result == pytest.approx(3.6, abs=0.01)

    def test_calculate_total_score_bearish(self, analyzer: SentimentAnalyzer) -> None:
        """Test calculating bearish total score."""
        sentiments = {"news": -0.8, "social": -0.6}
        weights = {"news": 0.6, "social": 0.4}
        result = analyzer.calculate_total_score(sentiments, weights)
        # (-0.8 * 0.6 + -0.6 * 0.4) / 1.0 * 5 = -3.6
        assert result == pytest.approx(-3.6, abs=0.01)

    def test_smooth_score_first_observation(self, analyzer: SentimentAnalyzer) -> None:
        """Test that first observation is returned as-is."""
        result = analyzer.smooth_score(2.0, "TEST", datetime.now())
        assert result == 2.0

    def test_smooth_score_subsequent(self, analyzer: SentimentAnalyzer) -> None:
        """Test EMA smoothing on subsequent observations."""
        symbol = "TEST"
        timestamp = datetime.now()
        # First observation
        analyzer.smooth_score(2.0, symbol, timestamp)
        # Second observation with alpha=0.2
        # smoothed = 0.2 * 3.0 + 0.8 * 2.0 = 0.6 + 1.6 = 2.2
        result = analyzer.smooth_score(3.0, symbol, timestamp)
        assert result == pytest.approx(2.2, abs=0.01)

    def test_interpret_score_extreme_bearish(self, analyzer: SentimentAnalyzer) -> None:
        """Test interpretation of extreme bearish score."""
        result = analyzer.interpret_score(-4.0)
        assert result == "extreme_bearish"

    def test_interpret_score_bearish(self, analyzer: SentimentAnalyzer) -> None:
        """Test interpretation of bearish score."""
        result = analyzer.interpret_score(-2.0)
        assert result == "bearish"

    def test_interpret_score_neutral(self, analyzer: SentimentAnalyzer) -> None:
        """Test interpretation of neutral score."""
        result = analyzer.interpret_score(0.0)
        assert result == "neutral"

    def test_interpret_score_bullish(self, analyzer: SentimentAnalyzer) -> None:
        """Test interpretation of bullish score."""
        result = analyzer.interpret_score(2.0)
        assert result == "bullish"

    def test_interpret_score_extreme_bullish(self, analyzer: SentimentAnalyzer) -> None:
        """Test interpretation of extreme bullish score."""
        result = analyzer.interpret_score(4.0)
        assert result == "extreme_bullish"

    def test_calculate_sentiment_basic(self, analyzer: SentimentAnalyzer) -> None:
        """Test basic sentiment calculation with multiple sources."""
        sources = [
            SentimentSource(
                source="news",
                timestamp=datetime.now(),
                raw_sentiment=-0.3,
                normalized=-0.3,
                confidence=0.8,
                metadata=None,
            ),
            SentimentSource(
                source="social",
                timestamp=datetime.now(),
                raw_sentiment=-0.5,
                normalized=-0.5,
                confidence=0.7,
                metadata=None,
            ),
        ]
        result = analyzer.calculate_sentiment("600519.SH", sources)
        assert isinstance(result, SentimentResult)
        assert result.symbol == "600519.SH"
        assert result.interpretation in ["bearish", "extreme_bearish", "neutral"]


class TestSentimentAnalyzerEdgeCases:
    """Edge case tests for SentimentAnalyzer."""

    @pytest.fixture
    def analyzer(self) -> SentimentAnalyzer:
        """Create a SentimentAnalyzer instance for testing."""
        return SentimentAnalyzer()

    def test_empty_sources(self, analyzer: SentimentAnalyzer) -> None:
        """Test calculating sentiment with no sources."""
        result = analyzer.calculate_sentiment("TEST", [])
        assert result.total_score == 0.0
        assert result.interpretation == "neutral"

    def test_single_source(self, analyzer: SentimentAnalyzer) -> None:
        """Test calculating sentiment with single source."""
        sources = [
            SentimentSource(
                source="news",
                timestamp=datetime.now(),
                raw_sentiment=0.8,
                normalized=0.8,
                confidence=0.9,
                metadata=None,
            ),
        ]
        result = analyzer.calculate_sentiment("TEST", sources)
        # Single source with 0.8 sentiment and 0.4 weight -> 0.8 * 0.4 * 5 = 1.6
        assert result.total_score > 0

    def test_unknown_source_weight(self, analyzer: SentimentAnalyzer) -> None:
        """Test that unknown sources are handled gracefully."""
        sentiments = {"unknown_source": 0.5}
        weights = {"news": 0.4, "social": 0.3}  # No weight for unknown_source
        result = analyzer.calculate_total_score(sentiments, weights)
        # Unknown source has weight 0, so result should be 0
        assert result == 0.0

    def test_roc_with_single_observation(self, analyzer: SentimentAnalyzer) -> None:
        """Test ROC calculation with only one observation."""
        roc = analyzer.calculate_roc("NONEXISTENT")
        assert roc == 0.0

    def test_historical_scores_empty_symbol(self, analyzer: SentimentAnalyzer) -> None:
        """Test getting historical scores for non-existent symbol."""
        df = analyzer.get_historical_scores("NONEXISTENT")
        assert df.empty

    def test_sentiment_stats_no_data(self, analyzer: SentimentAnalyzer) -> None:
        """Test sentiment stats with no historical data."""
        stats = analyzer.calculate_sentiment_stats("NONEXISTENT")
        assert stats == {}

    def test_is_sentiment_extreme_no_data(self, analyzer: SentimentAnalyzer) -> None:
        """Test extreme sentiment check with no data."""
        is_extreme, z_score = analyzer.is_sentiment_extreme("NONEXISTENT")
        assert is_extreme is False
        assert z_score == 0.0


class TestSentimentConfig:
    """Tests for SentimentConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = SentimentConfig()
        assert config.news_weight == 0.40
        assert config.social_weight == 0.35
        assert config.search_weight == 0.15
        assert config.forum_weight == 0.10
        assert config.ema_alpha == 0.2
        assert config.min_score == -5.0
        assert config.max_score == 5.0

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = SentimentConfig(
            news_weight=0.5,
            social_weight=0.3,
            ema_alpha=0.3,
        )
        assert config.news_weight == 0.5
        assert config.social_weight == 0.3
        assert config.ema_alpha == 0.3

    def test_weight_sum_approximately_one(self) -> None:
        """Test that default weights sum to approximately 1.0."""
        config = SentimentConfig()
        total_weight = (
            config.news_weight + config.social_weight + config.search_weight + config.forum_weight
        )
        assert total_weight == pytest.approx(1.0, abs=0.01)


class TestSentimentResult:
    """Tests for SentimentResult dataclass."""

    def test_sentiment_result_creation(self) -> None:
        """Test creating a SentimentResult."""
        result = SentimentResult(
            symbol="600519.SH",
            timestamp=datetime.now(),
            total_score=-2.5,
            smoothed_score=-2.3,
            roc=-0.2,
            interpretation="bearish",
            source_scores={"news": -1.2, "social": -1.0},
            confidences={"news": 0.8, "social": 0.7},
            signals={"rapid_deterioration": True, "bearish": True},
        )
        assert result.symbol == "600519.SH"
        assert result.total_score == -2.5
        assert result.interpretation == "bearish"
