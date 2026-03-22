"""Unit tests for SentimentDataProvider."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from common.types import SentimentScore
from data.providers import SentimentDataProvider


class TestSentimentDataProvider:
    """Tests for SentimentDataProvider class."""

    @pytest.fixture
    def provider(self) -> SentimentDataProvider:
        """Create a provider instance for testing."""
        return SentimentDataProvider()

    def test_get_social_sentiment_empty_data(self, provider: SentimentDataProvider) -> None:
        """Test social sentiment with empty data."""
        hot_rank_df = pd.DataFrame()
        spot_df = pd.DataFrame()

        scores = provider.get_social_sentiment(hot_rank_df, spot_df)
        assert scores == []

    def test_get_social_sentiment_basic(self, provider: SentimentDataProvider) -> None:
        """Test basic social sentiment calculation."""
        # Create test data
        hot_rank_df = pd.DataFrame(
            {
                "代码": ["600519", "000001"],
            }
        )
        spot_df = pd.DataFrame(
            {
                "代码": ["600519", "000001"],
                "涨跌幅": [2.5, -3.0],
            }
        )

        scores = provider.get_social_sentiment(hot_rank_df, spot_df)

        # Should return 2 scores
        assert len(scores) == 2

        # All scores should have source='social'
        for score in scores:
            assert score.source == "social"
            assert -1.0 <= score.score <= 1.0
            assert 0.0 <= score.confidence <= 1.0

    def test_get_news_sentiment_empty_data(self, provider: SentimentDataProvider) -> None:
        """Test news sentiment with empty data."""
        dt_list_df = pd.DataFrame()
        hsgt_df = pd.DataFrame()

        scores = provider.get_news_sentiment(dt_list_df, hsgt_df)
        assert scores == []

    def test_get_news_sentiment_basic(self, provider: SentimentDataProvider) -> None:
        """Test basic news sentiment calculation."""
        # Create test data with dragon-tiger net buy
        dt_list_df = pd.DataFrame(
            {
                "代码": ["600519"],
                "净买入": [1000000],
            }
        )
        hsgt_df = pd.DataFrame()

        scores = provider.get_news_sentiment(dt_list_df, hsgt_df)

        # Should return 1 score
        assert len(scores) == 1
        assert scores[0].source == "news"
        assert scores[0].symbol == "600519"

    def test_get_forum_sentiment_empty_data(self, provider: SentimentDataProvider) -> None:
        """Test forum sentiment with empty data."""
        fund_flow_df = pd.DataFrame()
        margin_df = pd.DataFrame()

        scores = provider.get_forum_sentiment(fund_flow_df, margin_df)
        # Empty data should return scores based on default values
        assert isinstance(scores, list)

    def test_get_forum_sentiment_basic(self, provider: SentimentDataProvider) -> None:
        """Test basic forum sentiment calculation."""
        # Create test data
        fund_flow_df = pd.DataFrame(
            {
                "代码": ["600519"],
                "主力净流入": [5000000],
                "散户净流入": [2000000],
            }
        )
        margin_df = pd.DataFrame()

        scores = provider.get_forum_sentiment(fund_flow_df, margin_df)

        # Should return 1 score
        assert len(scores) == 1
        assert scores[0].source == "forum"

    def test_get_search_sentiment_empty_data(self, provider: SentimentDataProvider) -> None:
        """Test search sentiment with empty data."""
        margin_df = pd.DataFrame()
        spot_df = pd.DataFrame()

        scores = provider.get_search_sentiment(margin_df, spot_df)
        # Empty data should return scores based on default values
        assert isinstance(scores, list)

    def test_get_search_sentiment_basic(self, provider: SentimentDataProvider) -> None:
        """Test basic search sentiment calculation."""
        # Create test data
        margin_df = pd.DataFrame(
            {
                "代码": ["600519"],
                "融资余额": [15000000],
            }
        )
        spot_df = pd.DataFrame(
            {
                "代码": ["600519"],
                "成交量": [20000000],
            }
        )

        scores = provider.get_search_sentiment(margin_df, spot_df)

        # Should return 1 score
        assert len(scores) == 1
        assert scores[0].source == "search"

    def test_sentiment_scores_valid_range(self, provider: SentimentDataProvider) -> None:
        """Test that all sentiment scores are within valid range."""
        # Create test data
        hot_rank_df = pd.DataFrame({"代码": ["600519"]})
        spot_df = pd.DataFrame(
            {
                "代码": ["600519"],
                "涨跌幅": [0.0],
            }
        )

        scores = provider.get_social_sentiment(hot_rank_df, spot_df)

        for score in scores:
            assert -1.0 <= score.score <= 1.0
            assert 0.0 <= score.confidence <= 1.0
            assert score.source in ["news", "social", "search", "forum"]
            assert isinstance(score.symbol, str)
            assert isinstance(score.timestamp, datetime)

    def test_sentiment_score_properties(self, provider: SentimentDataProvider) -> None:
        """Test SentimentScore properties."""
        # Create test scores
        bullish = SentimentScore(
            symbol="600519",
            timestamp=datetime.now(),
            score=0.6,
            confidence=0.8,
            source="social",
        )
        bearish = SentimentScore(
            symbol="000001",
            timestamp=datetime.now(),
            score=-0.6,
            confidence=0.7,
            source="news",
        )
        neutral = SentimentScore(
            symbol="000002",
            timestamp=datetime.now(),
            score=0.0,
            confidence=0.5,
            source="forum",
        )

        assert bullish.is_bullish is True
        assert bullish.is_bearish is False
        assert bullish.is_neutral is False

        assert bearish.is_bullish is False
        assert bearish.is_bearish is True
        assert bearish.is_neutral is False

        assert neutral.is_bullish is False
        assert neutral.is_bearish is False
        assert neutral.is_neutral is True
