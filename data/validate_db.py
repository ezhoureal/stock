#!/usr/bin/env python3
"""
Database validation and cleanup script for the sentiment arbitrage system.
Performs data quality checks and identifies issues in the database.

Usage:
    python validate_db.py
    python validate_db.py --fix
    python validate_db.py --table daily_prices
"""

import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Configure logging
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "db_validation.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class ValidationResult:
    """Result of a validation check"""

    def __init__(self, check_name: str):
        self.check_name = check_name
        self.passed = True
        self.issues = []
        self.suggestions = []

    def add_issue(self, issue: str):
        """Add an issue to the results"""
        self.issues.append(issue)
        self.passed = False

    def add_suggestion(self, suggestion: str):
        """Add a suggestion to the results"""
        self.suggestions.append(suggestion)

    def __repr__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status}: {self.check_name} ({len(self.issues)} issues, {len(self.suggestions)} suggestions)"


class DatabaseValidator:
    """
    Validates data quality in the sentiment arbitrage database.
    """

    def __init__(self, config_path: str | None = None):
        """
        Initialize the database validator.

        Args:
            config_path: Path to configuration file (default: data/config.json)
        """
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.json")

        self.config = self._load_config(config_path)
        self.db_path = self.config["database"]["path"]
        self.conn = None
        self.logger = logger

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

    def _connect_database(self):
        """Connect to DuckDB database"""
        try:
            import duckdb

            self.conn = duckdb.connect(self.db_path)
            return True
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            return False

    def _disconnect_database(self):
        """Disconnect from database"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def validate_schema(self) -> ValidationResult:
        """Validate database schema"""
        result = ValidationResult("Schema Validation")

        try:
            # Check if required tables exist
            required_tables = [
                "stocks",
                "daily_prices",
                "fundamentals",
                "sentiment_scores",
                "news_raw",
                "csi300_history",
            ]

            for table in required_tables:
                tables = self.conn.execute("SHOW TABLES").fetchall()
                table_names = [t[0] for t in tables]

                if table not in table_names:
                    result.add_issue(f"Missing required table: {table}")
                else:
                    self.logger.debug(f"✓ Table {table} exists")

            # Check critical columns in daily_prices
            critical_columns = {
                "daily_prices": ["stock_id", "date", "open", "high", "low", "close", "volume"],
                "stocks": ["stock_id", "name", "is_csi300"],
                "news_raw": ["title", "url", "publish_time", "source"],
            }

            for table, columns in critical_columns.items():
                try:
                    columns_info = self.conn.execute(f"PRAGMA table_info('{table}')").fetchall()
                    existing_columns = {col[1] for col in columns_info}

                    for col in columns:
                        if col not in existing_columns:
                            result.add_issue(f"Table {table} missing column: {col}")
                except Exception as e:
                    result.add_issue(f"Could not check columns for {table}: {e}")

        except Exception as e:
            result.add_issue(f"Schema validation error: {e}")

        return result

    def validate_price_data(self) -> ValidationResult:
        """Validate price data quality"""
        result = ValidationResult("Price Data Quality")

        try:
            # Check for NULL values in critical columns
            null_check = self.conn.execute("""
                SELECT
                    SUM(CASE WHEN open IS NULL THEN 1 ELSE 0 END) as null_open,
                    SUM(CASE WHEN high IS NULL THEN 1 ELSE 0 END) as null_high,
                    SUM(CASE WHEN low IS NULL THEN 1 ELSE 0 END) as null_low,
                    SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) as null_close,
                    SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) as null_volume,
                    COUNT(*) as total_rows
                FROM daily_prices
            """).fetchone()

            if null_check:
                total_rows = null_check[5]
                nulls = {
                    "open": null_check[0],
                    "high": null_check[1],
                    "low": null_check[2],
                    "close": null_check[3],
                    "volume": null_check[4],
                }

                for col, null_count in nulls.items():
                    if null_count > 0:
                        null_pct = (null_count / total_rows) * 100
                        result.add_issue(
                            f"Column {col}: {null_count} NULL values ({null_pct:.2f}%)"
                        )
                        if null_pct > 5:
                            result.add_suggestion(
                                f"Consider cleaning or filling NULL values in {col}"
                            )

            # Check for price anomalies (high < low, prices <= 0)
            anomalies = self.conn.execute("""
                SELECT
                    SUM(CASE WHEN high < low THEN 1 ELSE 0 END) as high_less_than_low,
                    SUM(CASE WHEN open <= 0 THEN 1 ELSE 0 END) as non_positive_open,
                    SUM(CASE WHEN high <= 0 THEN 1 ELSE 0 END) as non_positive_high,
                    SUM(CASE WHEN low <= 0 THEN 1 ELSE 0 END) as non_positive_low,
                    SUM(CASE WHEN close <= 0 THEN 1 ELSE 0 END) as non_positive_close
                FROM daily_prices
            """).fetchone()

            if anomalies[0] > 0:
                result.add_issue(f"{anomalies[0]} rows where high < low (impossible)")
                result.add_suggestion("Remove or correct these rows")

            for i, col in enumerate(["open", "high", "low", "close"]):
                if anomalies[i + 1] > 0:
                    result.add_issue(f"{anomalies[i + 1]} rows with non-positive {col}")

            # Check for extreme outliers (price changes > 50% in one day)
            outliers = self.conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT
                        stock_id,
                        date,
                        (close - LAG(close) OVER (PARTITION BY stock_id ORDER BY date)) / LAG(close) OVER (PARTITION BY stock_id ORDER BY date) as daily_return
                    FROM daily_prices
                    WHERE LAG(close) OVER (PARTITION BY stock_id ORDER BY date) IS NOT NULL
                ) t
                WHERE ABS(daily_return) > 0.5
            """).fetchone()

            if outliers and outliers[0] > 0:
                result.add_suggestion(
                    f"Found {outliers[0]} extreme price moves (>50%), review for data errors"
                )

            # Check data coverage by date
            coverage = self.conn.execute("""
                SELECT
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date,
                    COUNT(DISTINCT date) as trading_days,
                    COUNT(DISTINCT stock_id) as stocks_with_data
                FROM daily_prices
            """).fetchone()

            if coverage:
                self.logger.info("Price data coverage:")
                self.logger.info(f"  Date range: {coverage[0]} to {coverage[1]}")
                self.logger.info(f"  Trading days: {coverage[2]}")
                self.logger.info(f"  Stocks with data: {coverage[3]}")

                # Check if coverage is reasonable
                expected_days = (coverage[1] - coverage[0]).days
                if expected_days > 0:
                    coverage_pct = (coverage[2] / expected_days) * 100
                    if coverage_pct < 70:
                        result.add_suggestion(f"Only {coverage_pct:.1f}% of trading days have data")

        except Exception as e:
            result.add_issue(f"Price data validation error: {e}")
            traceback.print_exc()

        return result

    def validate_stock_data(self) -> ValidationResult:
        """Validate stocks table data"""
        result = ValidationResult("Stocks Data Quality")

        try:
            # Check for CSI 300 stocks
            csi300_count = self.conn.execute("""
                SELECT COUNT(*) FROM stocks WHERE is_csi300 = TRUE
            """).fetchone()[0]

            if csi300_count < 300:
                result.add_issue(f"Only {csi300_count} CSI 300 stocks in database (expected 300)")

            # Check for active stocks
            active_count = self.conn.execute("""
                SELECT COUNT(*) FROM stocks WHERE is_active = TRUE
            """).fetchone()[0]

            self.logger.info(f"Stocks: {active_count} active, {csi300_count} CSI 300")

            # Check for missing stock IDs or names
            missing_data = self.conn.execute("""
                SELECT COUNT(*) FROM stocks
                WHERE stock_id IS NULL OR name IS NULL OR name = ''
            """).fetchone()[0]

            if missing_data > 0:
                result.add_issue(f"{missing_data} stocks with missing ID or name")

            # Check for duplicates
            duplicates = self.conn.execute("""
                SELECT stock_id, COUNT(*) as cnt
                FROM stocks
                GROUP BY stock_id
                HAVING cnt > 1
            """).fetchall()

            if duplicates:
                result.add_issue(f"Found {len(duplicates)} duplicate stock IDs")

        except Exception as e:
            result.add_issue(f"Stock data validation error: {e}")

        return result

    def validate_news_data(self) -> ValidationResult:
        """Validate news data quality"""
        result = ValidationResult("News Data Quality")

        try:
            # Check for news data
            news_count = self.conn.execute("SELECT COUNT(*) FROM news_raw").fetchone()[0]

            if news_count == 0:
                result.add_suggestion("No news data collected yet")
                return result

            self.logger.info(f"News articles: {news_count}")

            # Check for NULL titles
            null_titles = self.conn.execute("""
                SELECT COUNT(*) FROM news_raw
                WHERE title IS NULL OR title = ''
            """).fetchone()[0]

            if null_titles > 0:
                result.add_issue(f"{null_titles} articles with NULL or empty title")

            # Check for missing URLs
            null_urls = self.conn.execute("""
                SELECT COUNT(*) FROM news_raw
                WHERE url IS NULL OR url = ''
            """).fetchone()[0]

            if null_urls > 0:
                result.add_issue(f"{null_urls} articles with NULL or empty URL")

            # Check for duplicates
            duplicates = self.conn.execute("""
                SELECT url, COUNT(*) as cnt
                FROM news_raw
                GROUP BY url
                HAVING cnt > 1
            """).fetchall()

            if duplicates:
                result.add_issue(f"Found {len(duplicates)} duplicate news URLs")

            # Check news recency
            latest_news = self.conn.execute("""
                SELECT MAX(publish_time) as latest
                FROM news_raw
            """).fetchone()

            if latest_news and latest_news[0]:
                days_old = (datetime.now() - latest_news[0]).days
                self.logger.info(f"Latest news: {latest_news[0]} ({days_old} days old)")

                if days_old > 7:
                    result.add_suggestion(f"News data is {days_old} days old, consider updating")

        except Exception as e:
            result.add_issue(f"News data validation error: {e}")

        return result

    def validate_fundamental_data(self) -> ValidationResult:
        """Validate fundamental data quality"""
        result = ValidationResult("Fundamental Data Quality")

        try:
            # Check for fundamental data
            fund_count = self.conn.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]

            if fund_count == 0:
                result.add_suggestion("No fundamental data collected yet")
                return result

            self.logger.info(f"Fundamental records: {fund_count}")

            # Check for critical columns
            critical_metrics = ["pe_ratio", "pb_ratio", "roe"]
            for metric in critical_metrics:
                null_count = self.conn.execute(f"""
                    SELECT COUNT(*) FROM fundamentals WHERE {metric} IS NULL
                """).fetchone()[0]

                null_pct = (null_count / fund_count) * 100
                if null_pct > 50:
                    result.add_suggestion(f"Metric {metric}: {null_pct:.1f}% NULL values")

            # Check data recency
            latest_fund = self.conn.execute("""
                SELECT MAX(report_date) as latest
                FROM fundamentals
            """).fetchone()

            if latest_fund and latest_fund[0]:
                days_old = (datetime.now() - latest_fund[0]).days
                self.logger.info(f"Latest fundamental data: {latest_fund[0]} ({days_old} days old)")

                if days_old > 120:
                    result.add_suggestion(
                        f"Fundamental data is {days_old} days old, consider updating"
                    )

        except Exception as e:
            result.add_issue(f"Fundamental data validation error: {e}")

        return result

    def fix_issues(self, results: list[ValidationResult], auto_fix: bool = False):
        """
        Attempt to fix identified issues.

        Args:
            results: List of ValidationResult objects
            auto_fix: If True, automatically fix issues without prompting
        """
        for result in results:
            if not result.passed:
                self.logger.warning(f"Issues found in {result.check_name}")

                for issue in result.issues:
                    self.logger.warning(f"  - {issue}")

                if auto_fix:
                    self._auto_fix_issues(result)

    def _auto_fix_issues(self, result: ValidationResult):
        """Automatically fix issues in a validation result"""
        try:
            if "high < low" in str(result.issues):
                self.logger.info("Fixing rows where high < low...")
                self.conn.execute("""
                    DELETE FROM daily_prices WHERE high < low
                """)
                self.logger.info("✓ Removed invalid rows")

            # Add more auto-fix logic as needed

        except Exception as e:
            self.logger.error(f"Auto-fix failed: {e}")

    def run_validation(self, table: str | None = None, fix: bool = False) -> list[ValidationResult]:
        """
        Run all or specific validations.

        Args:
            table: Specific table to validate (None = all)
            fix: If True, attempt to fix issues

        Returns:
            List of ValidationResult objects
        """
        self.logger.info("=" * 80)
        self.logger.info("Database Validation")
        self.logger.info("=" * 80)

        # Connect to database
        if not self._connect_database():
            self.logger.error("Failed to connect to database")
            return []

        results = []

        try:
            # Run validations
            if table is None or table == "schema":
                results.append(self.validate_schema())

            if table is None or table == "stocks":
                results.append(self.validate_stock_data())

            if table is None or table == "daily_prices":
                results.append(self.validate_price_data())

            if table is None or table == "news_raw":
                results.append(self.validate_news_data())

            if table is None or table == "fundamentals":
                results.append(self.validate_fundamental_data())

            # Print summary
            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info("Validation Summary")
            self.logger.info("=" * 80)

            passed = sum(1 for r in results if r.passed)
            failed = len(results) - passed

            self.logger.info(f"Passed: {passed}/{len(results)}")
            self.logger.info(f"Failed: {failed}/{len(results)}")

            for result in results:
                self.logger.info(result)

            # Fix issues if requested
            if fix:
                self.logger.info("")
                self.logger.info("Attempting to fix issues...")
                self.fix_issues(results, auto_fix=True)

            return results

        finally:
            self._disconnect_database()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Validate database for sentiment arbitrage system")
    parser.add_argument(
        "--table",
        choices=["schema", "stocks", "daily_prices", "news_raw", "fundamentals"],
        help="Specific table to validate (default: all)",
    )
    parser.add_argument("--fix", action="store_true", help="Attempt to automatically fix issues")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        # Create validator
        validator = DatabaseValidator()

        # Run validation
        results = validator.run_validation(table=args.table, fix=args.fix)

        # Exit with error if any validations failed
        if any(not r.passed for r in results):
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
