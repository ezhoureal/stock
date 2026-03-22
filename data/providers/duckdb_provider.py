"""
DuckDB Data Provider Implementation

Provides data access from DuckDB database.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from common.config import DataConfig
from common.interfaces import DataProvider
from common.types import (
    Bar,
    Fundamentals,
    SentimentScore,
    TimeFrame,
)

logger = logging.getLogger(__name__)


class DuckDBDataProvider(DataProvider):
    """
    Data provider implementation using DuckDB.

    Provides efficient access to price, fundamental, and sentiment data
    stored in DuckDB format.
    """

    def __init__(self, config: DataConfig | None = None):
        """
        Initialize DuckDB data provider.

        Args:
            config: Data configuration
        """
        self.config = config or DataConfig()
        self._conn = None
        self._cache: dict[str, Any] = {}

    def _get_connection(self):
        """Get or create database connection"""
        if self._conn is None:
            import duckdb

            db_path = Path(self.config.db_path)

            if not db_path.exists():
                logger.warning(f"Database not found at {db_path}")

            self._conn = duckdb.connect(str(db_path), read_only=True)
            logger.info(f"Connected to DuckDB: {db_path}")

        return self._conn

    def close(self) -> None:
        """Close database connection"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_prices(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: TimeFrame = TimeFrame.DAY_1,
    ) -> pd.DataFrame:
        """
        Get price data for symbols.

        Args:
            symbols: List of stock symbols
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe (only DAY_1 supported currently)

        Returns:
            DataFrame with MultiIndex (symbol, timestamp)
        """
        conn = self._get_connection()

        if not symbols:
            return pd.DataFrame()

        # Build query
        placeholders = ",".join(["?" for _ in symbols])

        query = f"""
            SELECT
                stock_id as symbol,
                trade_date as timestamp,
                open,
                high,
                low,
                close,
                volume,
                amount,
                pct_chg,
                adj_factor
            FROM daily_prices
            WHERE stock_id IN ({placeholders})
            AND trade_date >= ?
            AND trade_date <= ?
            ORDER BY stock_id, trade_date
        """

        params = symbols + [start.date(), end.date()]

        try:
            df = conn.execute(query, params).fetchdf()

            if df.empty:
                return pd.DataFrame()

            # Convert types
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            for col in ["open", "high", "low", "close", "volume", "amount"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # Apply adjustment factor
            if "adj_factor" in df.columns:
                # Normalize adjustment factor
                for symbol in df["symbol"].unique():
                    mask = df["symbol"] == symbol
                    base_factor = df.loc[mask, "adj_factor"].iloc[-1]  # Most recent
                    df.loc[mask, "adj_factor"] = df.loc[mask, "adj_factor"] / base_factor

                for col in ["open", "high", "low", "close"]:
                    df[col] = df[col] * df["adj_factor"]

            # Set MultiIndex
            df = df.set_index(["symbol", "timestamp"])

            return df

        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            return pd.DataFrame()

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """
        Get latest prices for symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to latest price
        """
        conn = self._get_connection()

        if not symbols:
            return {}

        placeholders = ",".join(["?" for _ in symbols])

        query = f"""
            SELECT DISTINCT ON (stock_id)
                stock_id as symbol,
                close,
                trade_date
            FROM daily_prices
            WHERE stock_id IN ({placeholders})
            ORDER BY stock_id, trade_date DESC
        """

        try:
            df = conn.execute(query, symbols).fetchdf()

            return dict(zip(df["symbol"], df["close"], strict=False))

        except Exception as e:
            logger.error(f"Error fetching latest prices: {e}")
            return {}

    def get_fundamentals(
        self,
        symbols: list[str],
        as_of: datetime | None = None,
    ) -> list[Fundamentals]:
        """
        Get fundamental data for symbols.

        Args:
            symbols: List of stock symbols
            as_of: Get fundamentals as of this date

        Returns:
            List of Fundamentals objects
        """
        conn = self._get_connection()

        if not symbols:
            return []

        as_of_date = as_of.date() if as_of else datetime.now().date()
        placeholders = ",".join(["?" for _ in symbols])

        query = f"""
            SELECT DISTINCT ON (f.stock_id)
                f.stock_id as symbol,
                f.report_date,
                f.pe,
                f.pe_ttm,
                f.pb,
                f.ps,
                f.roe,
                f.roa,
                f.eps,
                f.bps as book_value_per_share,
                f.total_mv,
                f.circ_mv,
                s.sector,
                s.industry
            FROM fundamentals f
            LEFT JOIN stocks s ON f.stock_id = s.stock_id
            WHERE f.stock_id IN ({placeholders})
            AND f.report_date <= ?
            ORDER BY f.stock_id, f.report_date DESC
        """

        params = symbols + [as_of_date]

        try:
            df = conn.execute(query, params).fetchdf()

            results = []
            for _, row in df.iterrows():
                # Extract scalar values from Series
                report_date = row["report_date"]
                if isinstance(report_date, pd.Series):
                    report_date = cast(datetime, report_date.iloc[0])
                results.append(
                    Fundamentals(
                        symbol=str(row["symbol"]),
                        timestamp=pd.Timestamp(report_date).to_pydatetime(),  # type: ignore[arg-type]
                        pe_ratio=float(row["pe"]) if row["pe"] is not None else None,
                        pe_ttm=float(row["pe_ttm"]) if row["pe_ttm"] is not None else None,
                        pb_ratio=float(row["pb"]) if row["pb"] is not None else None,
                        ps_ratio=float(row["ps"]) if row["ps"] is not None else None,
                        roe=float(row["roe"]) if row["roe"] is not None else None,
                        roa=float(row["roa"]) if row["roa"] is not None else None,
                        eps=float(row["eps"]) if row["eps"] is not None else None,
                        book_value_per_share=float(row["book_value_per_share"])
                        if row["book_value_per_share"] is not None
                        else None,
                        total_mv=float(row["total_mv"]) if row["total_mv"] is not None else None,
                        circ_mv=float(row["circ_mv"]) if row["circ_mv"] is not None else None,
                        sector=str(row["sector"]) if row["sector"] is not None else None,
                        industry=str(row["industry"]) if row["industry"] is not None else None,
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Error fetching fundamentals: {e}")
            return []

    def get_sentiment(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        source: str | None = None,
    ) -> list[SentimentScore]:
        """
        Get sentiment scores for symbols.

        Args:
            symbols: List of stock symbols
            start: Start datetime
            end: End datetime
            source: Filter by source

        Returns:
            List of SentimentScore objects
        """
        conn = self._get_connection()

        if not symbols:
            return []

        placeholders = ",".join(["?" for _ in symbols])
        params = symbols + [start, end]

        source_filter = ""
        if source:
            source_filter = "AND source = ?"
            params.append(source)

        query = f"""
            SELECT
                stock_id as symbol,
                timestamp,
                overall_score,
                source,
                news_count,
                news_score,
                social_count,
                social_score
            FROM sentiment_scores
            WHERE stock_id IN ({placeholders})
            AND timestamp >= ?
            AND timestamp <= ?
            {source_filter}
            ORDER BY stock_id, timestamp
        """

        try:
            df = conn.execute(query, params).fetchdf()

            results = []
            for _, row in df.iterrows():
                overall_score = row["overall_score"]
                source_val = row["source"]
                news_count = row.get("news_count")
                # Extract scalar timestamp from Series
                timestamp = row["timestamp"]
                if isinstance(timestamp, pd.Series):
                    timestamp = cast(datetime, timestamp.iloc[0])
                results.append(
                    SentimentScore(
                        symbol=str(row["symbol"]),
                        timestamp=pd.Timestamp(timestamp).to_pydatetime(),  # type: ignore[arg-type]
                        score=float(overall_score) if overall_score is not None else 0.0,
                        confidence=0.8,  # Default confidence
                        source=str(source_val) if source_val is not None else "composite",
                        sample_size=int(news_count) if news_count is not None else 0,
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Error fetching sentiment: {e}")
            return []

    def get_latest_sentiment(
        self,
        symbols: list[str],
    ) -> dict[str, SentimentScore]:
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

        placeholders = ",".join(["?" for _ in symbols])

        query = f"""
            SELECT DISTINCT ON (stock_id)
                stock_id as symbol,
                timestamp,
                overall_score,
                source
            FROM sentiment_scores
            WHERE stock_id IN ({placeholders})
            ORDER BY stock_id, timestamp DESC
        """

        try:
            df = conn.execute(query, symbols).fetchdf()

            result = {}
            for _, row in df.iterrows():
                overall_score = row["overall_score"]
                source_val = row["source"]
                # Extract scalar timestamp from Series
                timestamp = row["timestamp"]
                if isinstance(timestamp, pd.Series):
                    timestamp = cast(datetime, timestamp.iloc[0])
                result[str(row["symbol"])] = SentimentScore(
                    symbol=str(row["symbol"]),
                    timestamp=pd.Timestamp(timestamp).to_pydatetime(),  # type: ignore[arg-type]
                    score=float(overall_score) if overall_score is not None else 0.0,
                    confidence=0.8,
                    source=str(source_val) if source_val is not None else "composite",
                )

            return result

        except Exception as e:
            logger.error(f"Error fetching latest sentiment: {e}")
            return {}

    def get_universe(self, universe_name: str = "csi300") -> list[str]:
        """
        Get list of symbols in a universe.

        Args:
            universe_name: Name of the universe

        Returns:
            List of stock symbols
        """
        conn = self._get_connection()

        if universe_name == "csi300":
            query = """
                SELECT stock_id
                FROM stocks
                WHERE is_csi300 = TRUE
                AND is_active = TRUE
                ORDER BY stock_id
            """
        else:
            query = """
                SELECT stock_id
                FROM stocks
                WHERE is_active = TRUE
                ORDER BY stock_id
            """

        try:
            result = conn.execute(query).fetchall()
            return [row[0] for row in result]

        except Exception as e:
            logger.error(f"Error fetching universe: {e}")
            return []

    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: TimeFrame = TimeFrame.DAY_1,
    ) -> list[Bar]:
        """
        Get bar data for a single symbol.

        Args:
            symbol: Stock symbol
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe

        Returns:
            List of Bar objects
        """
        conn = self._get_connection()

        query = """
            SELECT
                trade_date as timestamp,
                open,
                high,
                low,
                close,
                volume,
                amount
            FROM daily_prices
            WHERE stock_id = ?
            AND trade_date >= ?
            AND trade_date <= ?
            ORDER BY trade_date
        """

        try:
            df = conn.execute(query, [symbol, start.date(), end.date()]).fetchdf()

            bars = []
            for _, row in df.iterrows():
                amount = row["amount"]
                # Extract scalar timestamp from Series
                timestamp = row["timestamp"]
                if isinstance(timestamp, pd.Series):
                    timestamp = cast(datetime, timestamp.iloc[0])
                bars.append(
                    Bar(
                        symbol=symbol,
                        timestamp=pd.Timestamp(timestamp).to_pydatetime(),  # type: ignore[arg-type]
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                        amount=float(amount) if amount is not None else None,
                    )
                )

            return bars

        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return []

    def get_price_dataframe(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Get price data as a pivoted DataFrame (symbols as columns).

        Useful for matrix operations and vectorized strategies.

        Args:
            symbols: List of stock symbols
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with dates as index and symbols as columns
        """
        df = self.get_prices(symbols, start, end)

        if df.empty:
            return pd.DataFrame()

        # Pivot to get close prices with symbols as columns
        close_prices = df["close"].unstack(level=0)

        # Ensure we return DataFrame even if unstack returns Series
        return pd.DataFrame(close_prices)

    def get_return_dataframe(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Get daily returns as a pivoted DataFrame.

        Args:
            symbols: List of stock symbols
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with dates as index and symbol returns as columns
        """
        prices = self.get_price_dataframe(symbols, start, end)

        if prices.empty:
            return pd.DataFrame()

        returns = prices.pct_change()

        return returns
