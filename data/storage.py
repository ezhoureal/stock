"""
DuckDB storage for sentiment data.

Implements DataProvider interface for sentiment persistence and retrieval.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import duckdb

from common.interfaces import DataProvider
from common.types import SentimentScore

logger = logging.getLogger(__name__)


class SentimentStorage(DataProvider):
    """
    DuckDB-based storage for sentiment scores.

    Implements DataProvider interface for integration with trading system.
    """

    def __init__(self, db_path: str | Path = "data/sentiment.db") -> None:
        """
        Initialize storage with DuckDB database.

        Args:
            db_path: Path to DuckDB database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._initialize_db()

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = duckdb.connect(str(self.db_path))
        return self._conn

    def _initialize_db(self) -> None:
        """Create database schema if not exists."""
        conn = self._get_connection()

        # Create sequences for auto-incrementing IDs
        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS sentiment_raw_id_seq
        """)

        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS sentiment_composite_id_seq
        """)

        # Raw sentiment scores by source
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_raw (
                id INTEGER PRIMARY KEY DEFAULT nextval('sentiment_raw_id_seq'),
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                source VARCHAR NOT NULL,
                score FLOAT NOT NULL,
                confidence FLOAT NOT NULL,
                raw_data JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Composite sentiment (aggregated)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_composite (
                id INTEGER PRIMARY KEY DEFAULT nextval('sentiment_composite_id_seq'),
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                score FLOAT NOT NULL,
                confidence FLOAT NOT NULL,
                source_scores JSON,
                UNIQUE(symbol, timestamp)
            )
        """)

        # Create indexes for common queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_raw_symbol_time
            ON sentiment_raw(symbol, timestamp DESC)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_raw_source
            ON sentiment_raw(source, timestamp DESC)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_composite_symbol_time
            ON sentiment_composite(symbol, timestamp DESC)
        """)

        logger.info(f"Database initialized at {self.db_path}")

    def store_raw_scores(self, scores: list[SentimentScore]) -> int:
        """
        Store raw sentiment scores.

        Args:
            scores: List of SentimentScore objects

        Returns:
            Number of scores stored
        """
        if not scores:
            return 0

        conn = self._get_connection()

        stored = 0
        for score in scores:
            try:
                raw_data = {
                    "raw_score": score.raw_score,
                    "sample_size": score.sample_size,
                    "metadata": score.metadata,
                }

                conn.execute(
                    """
                    INSERT INTO sentiment_raw
                    (symbol, timestamp, source, score, confidence, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        score.symbol,
                        score.timestamp,
                        score.source,
                        score.score,
                        score.confidence,
                        json.dumps(raw_data, ensure_ascii=False),
                    ),
                )
                stored += 1
            except Exception as e:
                logger.debug(f"Error storing score for {score.symbol}: {e}")

        logger.info(f"Stored {stored}/{len(scores)} raw sentiment scores")
        return stored

    def store_composite_score(
        self,
        symbol: str,
        timestamp: datetime,
        score: float,
        confidence: float,
        source_scores: dict[str, float],
    ) -> bool:
        """
        Store or update composite sentiment score.

        Args:
            symbol: Stock symbol
            timestamp: Timestamp of the score
            score: Composite sentiment score
            confidence: Composite confidence
            source_scores: Dictionary of source -> score

        Returns:
            True if stored successfully
        """
        conn = self._get_connection()

        try:
            conn.execute(
                """
                INSERT INTO sentiment_composite
                (symbol, timestamp, score, confidence, source_scores)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (symbol, timestamp) DO UPDATE SET
                    score = excluded.score,
                    confidence = excluded.confidence,
                    source_scores = excluded.source_scores
            """,
                (
                    symbol,
                    timestamp,
                    score,
                    confidence,
                    json.dumps(source_scores, ensure_ascii=False),
                ),
            )
            return True
        except Exception as e:
            logger.error(f"Error storing composite score for {symbol}: {e}")
            return False

    def get_sentiment(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        source: str | None = None,
    ) -> list[SentimentScore]:
        """
        Get sentiment scores for symbols within date range.

        Args:
            symbols: List of stock symbols
            start: Start datetime
            end: End datetime
            source: Filter by source ("news", "social", etc.)

        Returns:
            List of SentimentScore objects
        """
        conn = self._get_connection()

        if not symbols:
            return []

        # Build query
        if source:
            query = """
                SELECT symbol, timestamp, source, score, confidence, raw_data
                FROM sentiment_raw
                WHERE symbol IN (?, ?)
                AND timestamp BETWEEN ? AND ?
                AND source = ?
                ORDER BY timestamp DESC
            """
            params = [
                symbols[0],
                symbols[-1] if len(symbols) > 1 else symbols[0],
                start,
                end,
                source,
            ]
        else:
            query = """
                SELECT symbol, timestamp, source, score, confidence, raw_data
                FROM sentiment_raw
                WHERE symbol IN (?, ?)
                AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp DESC
            """
            params = [symbols[0], symbols[-1] if len(symbols) > 1 else symbols[0], start, end]

        try:
            result = conn.execute(query, params).fetchall()

            scores: list[SentimentScore] = []
            for row in result:
                symbol, timestamp, source, score, confidence, raw_data_str = row

                # Parse raw data
                raw_data = json.loads(raw_data_str) if raw_data_str else {}

                scores.append(
                    SentimentScore(
                        symbol=symbol,
                        timestamp=timestamp,
                        score=score,
                        confidence=confidence,
                        source=source or "unknown",
                        raw_score=raw_data.get("raw_score"),
                        sample_size=raw_data.get("sample_size"),
                        metadata=raw_data.get("metadata", {}),
                    )
                )

            return scores
        except Exception as e:
            logger.error(f"Error retrieving sentiment: {e}")
            return []

    def get_latest_sentiment(self, symbols: list[str]) -> dict[str, SentimentScore]:
        """
        Get latest sentiment scores for symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to latest SentimentScore
        """
        conn = self._get_connection()

        if not symbols:
            return {}

        result_dict: dict[str, SentimentScore] = {}

        for symbol in symbols:
            try:
                result = conn.execute(
                    """
                    SELECT symbol, timestamp, source, score, confidence, raw_data
                    FROM sentiment_raw
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                """,
                    (symbol,),
                ).fetchone()

                if result:
                    symbol, timestamp, source, score, confidence, raw_data_str = result
                    raw_data = json.loads(raw_data_str) if raw_data_str else {}

                    result_dict[symbol] = SentimentScore(
                        symbol=symbol,
                        timestamp=timestamp,
                        score=score,
                        confidence=confidence,
                        source=source,
                        raw_score=raw_data.get("raw_score"),
                        sample_size=raw_data.get("sample_size"),
                        metadata=raw_data.get("metadata", {}),
                    )
            except Exception as e:
                logger.debug(f"Error retrieving latest sentiment for {symbol}: {e}")

        return result_dict

    def get_prices(
        self, symbols: list[str], start: datetime, end: datetime, timeframe: str = "1d"
    ) -> list:
        """Not implemented for sentiment storage."""
        return []

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """Not implemented for sentiment storage."""
        return {}

    def get_bars(
        self, symbols: list[str], start: datetime, end: datetime, interval: str = "1d"
    ) -> list:
        """Not implemented for sentiment storage."""
        return []

    def get_fundamentals(self, symbols: list[str], as_of: datetime | None = None) -> list:
        """Not implemented for sentiment storage."""
        return []

    def get_universe(self, universe_name: str = "csi300") -> list[str]:
        """Not implemented for sentiment storage."""
        return []

    def get_latest_composite(self, symbols: list[str]) -> dict[str, SentimentScore]:
        """
        Get latest composite sentiment scores.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to latest composite SentimentScore
        """
        conn = self._get_connection()

        if not symbols:
            return {}

        result_dict: dict[str, SentimentScore] = {}

        for symbol in symbols:
            try:
                result = conn.execute(
                    """
                    SELECT symbol, timestamp, score, confidence, source_scores
                    FROM sentiment_composite
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                """,
                    (symbol,),
                ).fetchone()

                if result:
                    symbol, timestamp, score, confidence, source_scores_str = result
                    source_scores = json.loads(source_scores_str) if source_scores_str else {}

                    result_dict[symbol] = SentimentScore(
                        symbol=symbol,
                        timestamp=timestamp,
                        score=score,
                        confidence=confidence,
                        source="composite",
                        raw_score=score,
                        metadata={"source_scores": source_scores},
                    )
            except Exception as e:
                logger.debug(f"Error retrieving latest composite for {symbol}: {e}")

        return result_dict

    def cleanup_old_data(self, retention_days: int = 365) -> int:
        """
        Remove sentiment data older than retention period.

        Args:
            retention_days: Number of days to retain data

        Returns:
            Number of rows removed
        """
        conn = self._get_connection()

        try:
            result = conn.execute(f"""
                DELETE FROM sentiment_raw
                WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '{retention_days} days'
            """)

            deleted = result.rowcount if hasattr(result, "rowcount") else 0
            logger.info(f"Cleaned up {deleted} old sentiment records")
            return deleted
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return 0

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> SentimentStorage:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
