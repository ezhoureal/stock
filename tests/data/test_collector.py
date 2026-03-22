"""Unit tests for SentimentCollector."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from data.sentiment_collector import SentimentCollector


class TestSentimentCollector:
    """Tests for SentimentCollector class."""

    @pytest.fixture
    def temp_config(self) -> Path:
        """Create a temporary config file for testing."""
        config = {
            "database": {"path": ":memory:", "batch_size": 100},
            "sentiment": {"weights": {"news": 0.40, "social": 0.35, "search": 0.15, "forum": 0.10}},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            return Path(f.name)

    @pytest.fixture
    def collector(self, temp_config: Path) -> SentimentCollector:
        """Create a collector instance for testing."""
        return SentimentCollector(temp_config)

    def test_init(self, temp_config: Path) -> None:
        """Test collector initialization."""
        collector = SentimentCollector(temp_config)
        assert collector is not None
        assert collector.storage is not None
        assert collector.provider is not None

    def test_init_default_config(self) -> None:
        """Test collector initialization with default config."""
        collector = SentimentCollector(None)
        assert collector is not None
        # Should use default config
        assert collector.weights["news"] == 0.40

    def test_load_config(self, temp_config: Path) -> None:
        """Test config loading."""
        collector = SentimentCollector(temp_config)
        assert collector.config is not None
        assert "database" in collector.config

    def test_weights(self, collector: SentimentCollector) -> None:
        """Test sentiment weights."""
        assert collector.weights["news"] == 0.40
        assert collector.weights["social"] == 0.35
        assert collector.weights["search"] == 0.15
        assert collector.weights["forum"] == 0.10

    def test_compute_composite_empty(self, collector: SentimentCollector) -> None:
        """Test composite calculation with empty data."""
        scores_by_source = {
            "news": [],
            "social": [],
            "search": [],
            "forum": [],
        }

        composite = collector.compute_composite(scores_by_source)
        assert composite == {}

    def test_compute_composite_single_source(self, collector: SentimentCollector) -> None:
        """Test composite calculation with single source."""
        from common.types import SentimentScore

        now = datetime.now()
        scores_by_source = {
            "news": [
                SentimentScore(
                    symbol="600519",
                    timestamp=now,
                    score=0.6,
                    confidence=0.8,
                    source="news",
                    raw_score=0.6,
                )
            ],
            "social": [],
            "search": [],
            "forum": [],
        }

        composite = collector.compute_composite(scores_by_source)
        assert "600519" in composite
        # Composite should equal the only source score
        assert composite["600519"].score == 0.6

    def test_compute_composite_multiple_sources(self, collector: SentimentCollector) -> None:
        """Test composite calculation with multiple sources."""
        from common.types import SentimentScore

        now = datetime.now()
        scores_by_source = {
            "news": [
                SentimentScore(
                    symbol="600519",
                    timestamp=now,
                    score=0.6,
                    confidence=0.8,
                    source="news",
                    raw_score=0.6,
                )
            ],
            "social": [
                SentimentScore(
                    symbol="600519",
                    timestamp=now,
                    score=0.4,
                    confidence=0.7,
                    source="social",
                    raw_score=0.4,
                )
            ],
            "search": [],
            "forum": [],
        }

        composite = collector.compute_composite(scores_by_source)
        assert "600519" in composite

        # Composite should be weighted average: (0.6 * 0.4 + 0.4 * 0.35) / (0.4 + 0.35)
        # = (0.24 + 0.14) / 0.75 = 0.38 / 0.75 ≈ 0.507
        expected = (0.6 * 0.4 + 0.4 * 0.35) / (0.4 + 0.35)
        assert abs(composite["600519"].score - expected) < 0.01
        assert composite["600519"].source == "composite"

    def test_get_latest_sentiment_empty(self, collector: SentimentCollector) -> None:
        """Test getting latest sentiment with no data."""
        latest = collector.get_latest_sentiment(["600519"])
        assert latest == {}

    def test_get_sentiment_history_empty(self, collector: SentimentCollector) -> None:
        """Test getting sentiment history with no data."""
        now = datetime.now()
        history = collector.get_sentiment_history(["600519"], now, now)
        assert history == []

    def test_storage_integration(self, collector: SentimentCollector) -> None:
        """Test that collector has access to storage."""
        assert collector.storage is not None
        # Storage should be an instance of SentimentStorage
        from data.storage import SentimentStorage

        assert isinstance(collector.storage, SentimentStorage)

    def test_provider_integration(self, collector: SentimentCollector) -> None:
        """Test that collector has access to provider."""
        assert collector.provider is not None
        # Provider should be an instance of SentimentDataProvider
        from data.providers import SentimentDataProvider

        assert isinstance(collector.provider, SentimentDataProvider)
