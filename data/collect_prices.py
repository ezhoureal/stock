#!/usr/bin/env python3
"""
Production-ready historical price collection for CSI 300 stocks.
Handles multiple data sources with robust error handling and fallback logic.

Usage:
    python collect_prices.py --source baostock
    python collect_prices.py --source akshare
    python collect_prices.py --source auto  # Automatically chooses best source
"""

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "price_collection.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class DataCollectionError(Exception):
    """Base exception for data collection errors"""

    pass


class DataSourceError(DataCollectionError):
    """Error specific to data source API"""

    pass


class DataValidationError(DataCollectionError):
    """Error in data validation"""

    pass


class RateLimitError(DataCollectionError):
    """Rate limit hit on API"""

    pass


class PriceCollector:
    """
    Robust price data collector with multiple source support and automatic fallback.
    """

    def __init__(self, config_path: str | None = None):
        """
        Initialize the price collector.

        Args:
            config_path: Path to configuration file (default: data/config.json)
        """
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.json")

        self.config = self._load_config(config_path)
        self.db_path = self.config["database"]["path"]
        self.logger = logger

        # Load data source modules lazily
        self._baostock = None
        self._akshare = None

        # Rate limiting
        self.request_count = 0
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 1.0  # Initial delay in seconds
        self.retry_backoff = 2.0  # Exponential backoff multiplier

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            raise DataCollectionError(f"Config load failed: {e}") from e

    def _rate_limit(self):
        """Apply rate limiting between API calls"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)

        self.last_request_time = time.time()
        self.request_count += 1

    def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Execute function with retry logic and exponential backoff.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func call

        Raises:
            DataCollectionError: If all retries fail
        """
        last_error = None
        delay = self.retry_delay

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                self.logger.warning(
                    f"Rate limit hit (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    self.logger.info(f"Waiting {delay}s before retry...")
                    time.sleep(delay)
                    delay *= self.retry_backoff
                last_error = e
            except Exception as e:
                self.logger.warning(f"Error on attempt {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    self.logger.info(f"Waiting {delay}s before retry...")
                    time.sleep(delay)
                    delay *= self.retry_backoff
                last_error = e

        raise DataCollectionError(f"Failed after {self.max_retries} attempts: {last_error}")

    def _get_baostock(self):
        """Lazy load baostock module"""
        if self._baostock is None:
            try:
                import baostock as bs

                self._baostock = bs
                self.logger.info("Baostock loaded successfully")
            except ImportError as e:
                raise DataSourceError("Baostock not installed") from e
        return self._baostock

    def _get_akshare(self):
        """Lazy load akshare module"""
        if self._akshare is None:
            try:
                import akshare as ak

                self._akshare = ak
                self.logger.info("Akshare loaded successfully")
            except ImportError as e:
                raise DataSourceError("Akshare not installed") from e
        return self._akshare

    def _connect_database(self):
        """Connect to DuckDB database"""
        try:
            import duckdb

            conn = duckdb.connect(self.db_path)
            return conn
        except Exception as e:
            raise DataCollectionError(f"Database connection failed: {e}") from e

    def _validate_price_data(self, df) -> bool:
        """
        Validate price data DataFrame.

        Args:
            df: DataFrame with price data

        Returns:
            True if valid, raises DataValidationError if invalid
        """
        if df is None or len(df) == 0:
            raise DataValidationError("Empty price data")

        required_columns = ["date", "open", "high", "low", "close", "volume"]
        missing = [col for col in required_columns if col not in df.columns]

        if missing:
            raise DataValidationError(f"Missing required columns: {missing}")

        # Check for NULL values in critical columns
        null_counts = df[required_columns].isnull().sum()
        if null_counts.any():
            self.logger.warning(f"NULL values found in price data:\n{null_counts}")
            # Don't fail, just warn

        # Check price ranges
        for col in ["open", "high", "low", "close"]:
            invalid = (df[col] <= 0) | (df[col] > 100000)
            if invalid.any():
                self.logger.warning(f"Invalid price values in {col}: {invalid.sum()} rows")

        # Check high >= low >= 0
        invalid_hl = df["high"] < df["low"]
        if invalid_hl.any():
            raise DataValidationError(f"High < Low in {invalid_hl.sum()} rows")

        return True

    def fetch_prices_baostock(self, stock_id: str, start_date: str, end_date: str):
        """
        Fetch historical prices from Baostock.

        Args:
            stock_id: Stock ID (e.g., '600519')
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            DataFrame with price data

        Raises:
            DataSourceError: If fetch fails
        """
        bs = self._get_baostock()

        # Convert stock_id to baostock format
        if stock_id.startswith("6"):
            bs_code = f"sh.{stock_id}"
        else:
            bs_code = f"sz.{stock_id}"

        self.logger.debug(f"Fetching baostock data for {bs_code} from {start_date} to {end_date}")

        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount,turn,tradestatus,pctChg,isST",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="2",  # 2=复权
            )

            if rs is None or rs.error_code != "0":
                error_code = rs.error_code if rs is not None else "unknown"
                error_msg = rs.error_msg if rs is not None else "No response"
                raise DataSourceError(f"Baostock API error: {error_code} - {error_msg}")

            data_list = []
            while (rs.error_code == "0") & rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                self.logger.warning(f"No data returned for {stock_id}")
                return None

            # Convert to DataFrame
            import pandas as pd

            fields: list[str] = list(rs.fields) if rs is not None else []
            df = pd.DataFrame(data_list, columns=fields)  # type: ignore[arg-type]

            # Convert data types
            df["date"] = pd.to_datetime(df["date"])
            numeric_cols = ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # Filter out suspended days
            df = df[df["tradestatus"] == "1"]

            # Keep only needed columns
            df = df[["date", "open", "high", "low", "close", "volume"]]

            return df

        except Exception as e:
            self.logger.error(f"Baostock fetch failed for {stock_id}: {e}")
            raise DataSourceError(f"Baostock fetch failed: {e}") from e

    def fetch_prices_akshare(self, stock_id: str, start_date: str, end_date: str):
        """
        Fetch historical prices from Akshare.

        Args:
            stock_id: Stock ID (e.g., '600519')
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            DataFrame with price data

        Raises:
            DataSourceError: If fetch fails
        """
        ak = self._get_akshare()

        self.logger.debug(f"Fetching akshare data for {stock_id} from {start_date} to {end_date}")

        try:
            import pandas as pd

            # Akshare requires stock code with exchange suffix
            if stock_id.startswith("6"):
                ak_code = f"{stock_id}.SH"
            else:
                ak_code = f"{stock_id}.SZ"

            # Fetch data
            df = ak.stock_zh_a_hist(
                symbol=ak_code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",  # 前复权
            )

            if df is None or len(df) == 0:
                self.logger.warning(f"No data returned for {stock_id}")
                return None

            # Rename columns to match expected format
            column_mapping = {
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
            }

            df = df.rename(columns=column_mapping)

            # Convert date
            df["date"] = pd.to_datetime(df["date"])

            # Keep only needed columns
            df = df[["date", "open", "high", "low", "close", "volume"]]

            return df

        except Exception as e:
            self.logger.error(f"Akshare fetch failed for {stock_id}: {e}")
            raise DataSourceError(f"Akshare fetch failed: {e}") from e

    def fetch_prices(self, stock_id: str, start_date: str, end_date: str, source: str = "auto"):
        """
        Fetch historical prices with automatic source selection and fallback.

        Args:
            stock_id: Stock ID (e.g., '600519')
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            source: Data source ('baostock', 'akshare', or 'auto')

        Returns:
            DataFrame with price data

        Raises:
            DataCollectionError: If all sources fail
        """
        self._rate_limit()

        if source == "auto":
            # Try baostock first (more reliable), then akshare
            sources = ["baostock", "akshare"]
        else:
            sources = [source]

        last_error = None

        for src in sources:
            try:
                self.logger.info(f"Trying source: {src}")

                if src == "baostock":
                    df = self._retry_with_backoff(
                        self.fetch_prices_baostock, stock_id, start_date, end_date
                    )
                elif src == "akshare":
                    df = self._retry_with_backoff(
                        self.fetch_prices_akshare, stock_id, start_date, end_date
                    )
                else:
                    raise DataSourceError(f"Unknown source: {src}")

                if df is not None:
                    # Validate data
                    self._validate_price_data(df)
                    self.logger.info(f"✓ Fetched {len(df)} price records for {stock_id} from {src}")
                    return df

            except (DataSourceError, DataValidationError) as e:
                self.logger.warning(f"Source {src} failed for {stock_id}: {e}")
                last_error = e
                continue
            except Exception as e:
                self.logger.error(f"Unexpected error with {src} for {stock_id}: {e}")
                traceback.print_exc()
                last_error = e
                continue

        raise DataCollectionError(f"All sources failed for {stock_id}. Last error: {last_error}")

    def save_prices(self, conn, stock_id: str, df, source: str = "unknown") -> int:
        """
        Save price data to database.

        Args:
            conn: DuckDB connection
            stock_id: Stock ID
            df: DataFrame with price data
            source: Data source name

        Returns:
            Number of records inserted
        """
        inserted_count = 0

        try:
            conn.execute("BEGIN TRANSACTION")

            for _, row in df.iterrows():
                # Check if record exists
                existing = conn.execute(
                    """
                    SELECT 1 FROM daily_prices
                    WHERE stock_id = ? AND date = ?
                """,
                    [stock_id, row["date"]],
                ).fetchone()

                if existing:
                    # Update existing record
                    conn.execute(
                        """
                        UPDATE daily_prices
                        SET open = ?, high = ?, low = ?, close = ?, volume = ?,
                            data_source = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE stock_id = ? AND date = ?
                    """,
                        [
                            row["open"],
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                            source,
                            stock_id,
                            row["date"],
                        ],
                    )
                else:
                    # Insert new record
                    conn.execute(
                        """
                        INSERT INTO daily_prices
                        (stock_id, date, open, high, low, close, volume, data_source, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                        [
                            stock_id,
                            row["date"],
                            row["open"],
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                            source,
                        ],
                    )
                    inserted_count += 1

            conn.execute("COMMIT")
            self.logger.info(f"Saved {inserted_count} new price records for {stock_id}")

            return inserted_count

        except Exception as e:
            conn.execute("ROLLBACK")
            raise DataCollectionError(f"Failed to save prices for {stock_id}: {e}") from e

    def collect_prices(
        self,
        stock_ids: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        source: str = "auto",
    ):
        """
        Collect historical prices for multiple stocks.

        Args:
            stock_ids: List of stock IDs (None = all CSI 300)
            start_date: Start date (None = 1 year ago)
            end_date: End date (None = today)
            source: Data source ('baostock', 'akshare', or 'auto')

        Returns:
            Summary statistics dict
        """
        # Connect to database
        conn = self._connect_database()

        try:
            # Get stock IDs if not provided
            if stock_ids is None:
                self.logger.info("Fetching CSI 300 stock list from database...")
                rows = conn.execute("""
                    SELECT stock_id FROM stocks
                    WHERE is_csi300 = TRUE AND is_active = TRUE
                    ORDER BY stock_id
                """).fetchall()
                stock_ids = [row[0] for row in rows]
                self.logger.info(f"Found {len(stock_ids)} CSI 300 stocks")

            # Set date range
            if end_date is None:
                end_date = datetime.now().strftime("%Y-%m-%d")
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

            self.logger.info(f"Date range: {start_date} to {end_date}")
            self.logger.info(f"Data source: {source}")
            self.logger.info(f"Processing {len(stock_ids)} stocks...")

            # Statistics
            stats = {
                "total_stocks": len(stock_ids),
                "success": 0,
                "failed": 0,
                "total_records": 0,
                "failed_stocks": [],
            }

            # Process each stock
            for i, stock_id in enumerate(stock_ids):
                try:
                    self.logger.info(f"[{i + 1}/{len(stock_ids)}] Processing {stock_id}...")

                    # Fetch prices
                    df = self.fetch_prices(stock_id, start_date, end_date, source)

                    if df is not None:
                        # Save to database
                        inserted = self.save_prices(conn, stock_id, df, source)
                        stats["total_records"] += inserted
                        stats["success"] += 1

                except DataCollectionError as e:
                    self.logger.error(f"Failed to collect prices for {stock_id}: {e}")
                    stats["failed"] += 1
                    stats["failed_stocks"].append(stock_id)
                    continue

            # Print summary
            self.logger.info("=" * 80)
            self.logger.info("Price Collection Summary")
            self.logger.info("=" * 80)
            self.logger.info(f"Total stocks: {stats['total_stocks']}")
            self.logger.info(f"Successful: {stats['success']}")
            self.logger.info(f"Failed: {stats['failed']}")
            self.logger.info(f"Total records collected: {stats['total_records']}")

            if stats["failed_stocks"]:
                self.logger.warning(f"Failed stocks: {', '.join(stats['failed_stocks'])}")

            return stats

        finally:
            conn.close()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Collect historical stock prices")
    parser.add_argument(
        "--source",
        choices=["auto", "baostock", "akshare"],
        default="auto",
        help="Data source to use",
    )
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD, default: 1 year ago)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD, default: today)")
    parser.add_argument("--stock-id", help="Specific stock ID to collect (default: all CSI 300)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        # Create collector
        collector = PriceCollector()

        # Collect prices
        stock_ids = [args.stock_id] if args.stock_id else None
        stats = collector.collect_prices(
            stock_ids=stock_ids,
            start_date=args.start_date,
            end_date=args.end_date,
            source=args.source,
        )

        # Exit with error if any failures
        if stats["failed"] > 0:
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
