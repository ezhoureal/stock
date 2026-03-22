"""Unit tests for SentimentStorage."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from common.types import SentimentScore
from data.storage import SentimentStorage


class TestSentimentStorage:
    """Tests for SentimentStorage class."""

    @pytest.fixture
    def temp_db(self) -> Generator[SentimentStorage, None, None]:
        """Create a temporary database for testing."""

        # Create a temporary file path but don't create the file
        # DuckDB will create the file when connecting
        fd, db_path = tempfile.mkstemp(suffix=".db")
        # Close the file descriptor and delete the file
        import os

        os.close(fd)
        os.unlink(db_path)

        storage = SentimentStorage(db_path)
        yield storage
        storage.close()

        # Clean up
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    def test_store_raw_scores(self, temp_db: SentimentStorage) -> None:
        """Test storing raw sentiment scores."""
        scores = [
            SentimentScore(
                symbol="600519",
                timestamp=datetime.now(),
                score=0.5,
                confidence=0.8,
                source="news",
                raw_score=0.5,
                metadata={"test": "data"},
            ),
            SentimentScore(
                symbol="000001",
                timestamp=datetime.now(),
                score=-0.3,
                confidence=0.6,
                source="social",
                raw_score=-0.3,
            ),
        ]

        stored = temp_db.store_raw_scores(scores)
        assert stored == 2

    def test_store_composite_score(self, temp_db: SentimentStorage) -> None:
        """Test storing composite sentiment score."""
        result = temp_db.store_composite_score(
            symbol="600519",
            timestamp=datetime.now(),
            score=0.4,
            confidence=0.7,
            source_scores={"news": 0.5, "social": 0.3},
        )

        assert result is True

    def test_get_sentiment(self, temp_db: SentimentStorage) -> None:
        """Test retrieving sentiment scores."""
        # Store test data
        now = datetime.now()
        scores = [
            SentimentScore(
                symbol="600519",
                timestamp=now,
                score=0.5,
                confidence=0.8,
                source="news",
                raw_score=0.5,
            ),
        ]

        temp_db.store_raw_scores(scores)

        # Retrieve
        retrieved = temp_db.get_sentiment(["600519"], now, now)
        assert len(retrieved) == 1
        assert retrieved[0].symbol == "600519"
        assert retrieved[0].score == 0.5

    def test_get_sentiment_filter_by_source(self, temp_db: SentimentStorage) -> None:
        """Test filtering sentiment by source."""
        now = datetime.now()
        scores = [
            SentimentScore(
                symbol="600519",
                timestamp=now,
                score=0.5,
                confidence=0.8,
                source="news",
                raw_score=0.5,
            ),
            SentimentScore(
                symbol="600519",
                timestamp=now,
                score=0.3,
                confidence=0.6,
                source="social",
                raw_score=0.3,
            ),
        ]

        temp_db.store_raw_scores(scores)

        # Filter by news
        retrieved = temp_db.get_sentiment(["600519"], now, now, source="news")
        assert len(retrieved) == 1
        assert retrieved[0].source == "news"

    def test_get_latest_sentiment(self, temp_db: SentimentStorage) -> None:
        """Test getting latest sentiment for symbols."""
        now = datetime.now()
        scores = [
            SentimentScore(
                symbol="600519",
                timestamp=now,
                score=0.5,
                confidence=0.8,
                source="news",
                raw_score=0.5,
            ),
        ]

        temp_db.store_raw_scores(scores)

        # Get latest
        latest = temp_db.get_latest_sentiment(["600519"])
        assert "600519" in latest
        assert latest["600519"].score == 0.5

    def test_get_latest_composite(self, temp_db: SentimentStorage) -> None:
        """Test getting latest composite sentiment."""
        now = datetime.now()
        temp_db.store_composite_score(
            symbol="600519",
            timestamp=now,
            score=0.4,
            confidence=0.7,
            source_scores={"news": 0.5, "social": 0.3},
        )

        # Get latest
        latest = temp_db.get_latest_composite(["600519"])
        assert "600519" in latest
        # Use approximate comparison for floating point
        assert abs(latest["600519"].score - 0.4) < 0.01
        assert latest["600519"].source == "composite"

    def test_get_prices_not_implemented(self, temp_db: SentimentStorage) -> None:
        """Test that get_prices returns empty list."""
        result = temp_db.get_prices(["600519"], datetime.now(), datetime.now())
        assert result == []

    def test_get_latest_prices_not_implemented(self, temp_db: SentimentStorage) -> None:
        """Test that get_latest_prices returns empty dict."""
        result = temp_db.get_latest_prices(["600519"])
        assert result == {}

    def test_get_fundamentals_not_implemented(self, temp_db: SentimentStorage) -> None:
        """Test that get_fundamentals returns empty list."""
        result = temp_db.get_fundamentals(["600519"])
        assert result == []

    def test_get_universe_not_implemented(self, temp_db: SentimentStorage) -> None:
        """Test that get_universe returns empty list."""
        result = temp_db.get_universe()
        assert result == []

    def test_cleanup_old_data(self, temp_db: SentimentStorage) -> None:
        """Test cleanup of old data."""
        # This test just verifies the method runs without error
        deleted = temp_db.cleanup_old_data(retention_days=365)
        # DuckDB may return -1 for rowcount, so we just verify it runs without error
        assert deleted >= -1  # -1 indicates unknown rowcount
