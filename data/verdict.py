"""
Stock Verdict Analysis Script

Retrieves top-n or bottom-n stocks by sentiment score, fetches fundamental
metrics via AKShare APIs, calculates a combined sentiment + valuation score,
and outputs a ranking table.

Usage:
    uv run python data/verdict.py --bottom-n 10   # Contrarian buy candidates
    uv run python data/verdict.py --top-n 10      # Potential sell candidates
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd

from common.types import Fundamentals, SignalType
from data.storage import SentimentStorage
from sentiment_strategy.valuation import SectorMetrics, ValuationCalculator

logger = logging.getLogger(__name__)


def fetch_all_stock_names_from_api():
    """Fetch all stock names from AKShare API as DataFrame."""
    try:
        import akshare as ak

        df = ak.stock_info_a_code_name()
        # Rename columns to match database schema
        df = df.rename(columns={"code": "symbol", "name": "name"})
        # Filter out rows with empty values
        df = df[df["symbol"].notna() & df["name"].notna()]
        return df
    except Exception as e:
        logger.warning(f"Failed to fetch stock names from API: {e}")
        return None


def get_stock_names_with_cache(symbols: list[str], storage: SentimentStorage) -> dict[str, str]:
    """
    Get stock names using cache-first strategy.

    Args:
        symbols: List of stock symbols to look up
        storage: SentimentStorage instance for cache access

    Returns:
        Dictionary mapping symbol to name
    """
    # Check cache first
    cached_names = storage.get_stock_names(symbols)
    print(f"Found {len(cached_names)} names in cache")

    # Find symbols not in cache
    missing_symbols = [s for s in symbols if s not in cached_names]

    if missing_symbols:
        print("Fetching all stock names from API...")
        df = fetch_all_stock_names_from_api()

        if df is not None:
            # Cache ALL names for future use (DuckDB reads DataFrame directly)
            count = storage.update_stock_names_from_df(df)
            print(f"Updated cache with {count} total names")
            # Get the names we need from cache
            cached_names = storage.get_stock_names(symbols)

    return cached_names


@dataclass
class VerdictResult:
    """Result of verdict analysis for a single stock."""

    symbol: str
    name: str
    sentiment_score: float
    valuation_score: float
    combined_score: float
    verdict: SignalType
    pe_ratio: float | None
    pb_ratio: float | None
    dividend_yield: float | None
    peg_ratio: float | None
    confidence: float


class VerdictCalculator:
    """
    Calculates combined sentiment + valuation verdict for stocks.

    Uses contrarian strategy logic:
    - BUY: Bearish sentiment + Undervalued fundamentals
    - SELL: Bullish sentiment + Overvalued fundamentals
    - HOLD: Mixed or neutral signals
    """

    def __init__(
        self,
        weight_sentiment: float = 0.5,
        db_path: str | Path = "data/sentiment.db",
    ) -> None:
        """
        Initialize the verdict calculator.

        Args:
            weight_sentiment: Weight for sentiment in combined score (0-1)
            db_path: Path to DuckDB database with sentiment data
        """
        self.weight_sentiment = weight_sentiment
        self.weight_valuation = 1.0 - weight_sentiment
        self.storage = SentimentStorage(db_path)
        self.valuation_calculator = ValuationCalculator()

        # Default market-wide sector metrics for Chinese A-shares
        self.default_sector = SectorMetrics(
            pe_ratio=15.0,
            pb_ratio=2.0,
            dividend_yield=0.02,
            peg_ratio=1.5,
        )

    def get_top_n_sentiment(self, n: int) -> list[tuple[str, float]]:
        """
        Get top N stocks by sentiment score (most bullish).

        Args:
            n: Number of stocks to return

        Returns:
            List of (symbol, sentiment_score) tuples
        """
        conn = self.storage._get_connection()
        result = conn.execute(
            """
            SELECT symbol, score
            FROM sentiment_composite
            WHERE (symbol, timestamp) IN (
                SELECT symbol, MAX(timestamp)
                FROM sentiment_composite
                GROUP BY symbol
            )
            ORDER BY score DESC
            LIMIT ?
            """,
            (n,),
        ).fetchall()
        return [(row[0], row[1]) for row in result]

    def get_bottom_n_sentiment(self, n: int) -> list[tuple[str, float]]:
        """
        Get bottom N stocks by sentiment score (most bearish).

        Args:
            n: Number of stocks to return

        Returns:
            List of (symbol, sentiment_score) tuples
        """
        conn = self.storage._get_connection()
        result = conn.execute(
            """
            SELECT symbol, score
            FROM sentiment_composite
            WHERE (symbol, timestamp) IN (
                SELECT symbol, MAX(timestamp)
                FROM sentiment_composite
                GROUP BY symbol
            )
            ORDER BY score ASC
            LIMIT ?
            """,
            (n,),
        ).fetchall()
        return [(row[0], row[1]) for row in result]

    def fetch_spot_data(self) -> pd.DataFrame:
        """Fetch A-share spot data with PE and PB ratios."""
        try:
            df = ak.stock_zh_a_spot_em()
            logger.info(f"Fetched {len(df)} spot records")
            return df
        except Exception as e:
            logger.error(f"Error fetching spot data: {e}")
            return pd.DataFrame()

    def fetch_dividend_data(self) -> pd.DataFrame:
        """Fetch dividend yield data for all stocks."""
        try:
            df = ak.stock_history_dividend()
            logger.info(f"Fetched {len(df)} dividend records")
            return df
        except Exception as e:
            logger.error(f"Error fetching dividend data: {e}")
            return pd.DataFrame()

    def get_stock_names(self, symbols: list[str]) -> dict[str, str]:
        """
        Get stock names from cache or fetch from AKShare.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to name
        """
        # First try to get from cache
        cached_names = self.storage.get_stock_names(symbols)

        # Find symbols not in cache
        missing_symbols = [s for s in symbols if s not in cached_names]
        if missing_symbols:
            # Fetch from spot data
            spot_df = self.fetch_spot_data()
            if not spot_df.empty:
                for symbol in missing_symbols:
                    row = spot_df[spot_df["代码"] == symbol]
                    if not row.empty:
                        cached_names[symbol] = str(row.iloc[0]["名称"])

                # Update cache
                self.storage.update_stock_names(cached_names)

        return cached_names

    def fetch_fundamentals(self, symbols: list[str]) -> dict[str, Fundamentals]:
        """
        Fetch fundamental data for given symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to Fundamentals
        """
        fundamentals: dict[str, Fundamentals] = {}

        # Fetch spot data for PE and PB
        spot_df = self.fetch_spot_data()

        # Fetch dividend data
        div_df = self.fetch_dividend_data()

        # Build lookup dictionaries
        spot_dict: dict[str, dict[str, Any]] = {}
        if not spot_df.empty:
            for _, row in spot_df.iterrows():
                symbol = str(row["代码"])
                spot_dict[symbol] = {
                    "pe_ratio": row.get("市盈率-动态"),
                    "pb_ratio": row.get("市净率"),
                    "name": row.get("名称", ""),
                }

        div_dict: dict[str, float] = {}
        if not div_df.empty:
            for _, row in div_df.iterrows():
                symbol = str(row["代码"])
                # 年均股息 is in percentage, convert to ratio
                avg_div = row.get("年均股息", 0)
                if avg_div is not None and pd.notna(avg_div):
                    div_dict[symbol] = float(avg_div) / 100.0

        # Build Fundamentals for each symbol
        timestamp = datetime.now()
        for symbol in symbols:
            spot_data = spot_dict.get(symbol, {})

            pe = spot_data.get("pe_ratio")
            pb = spot_data.get("pb_ratio")
            div_yield = div_dict.get(symbol)

            # Convert to float or None
            pe_ratio = float(pe) if pe is not None and pd.notna(pe) else None
            pb_ratio = float(pb) if pb is not None and pd.notna(pb) else None
            dividend_yield: float | None = div_yield if div_yield is not None else None

            fundamentals[symbol] = Fundamentals(
                symbol=symbol,
                timestamp=timestamp,
                pe_ratio=pe_ratio,
                pe_ttm=pe_ratio,
                pb_ratio=pb_ratio,
                dividend_yield=dividend_yield,
                peg_ratio=None,  # Not readily available from AKShare
            )

        return fundamentals

    def calculate_combined_score(
        self,
        sentiment_score: float,
        valuation_score: float,
        is_bottom_n: bool = True,
    ) -> float:
        """
        Calculate combined sentiment + valuation score.

        Normalizes both scores to 0-100 scale and combines them.
        For contrarian strategy:
        - Bottom-n (bearish): low sentiment + high valuation = good buy
        - Top-n (bullish): high sentiment + low valuation = good sell

        Args:
            sentiment_score: Raw sentiment score (typically -5 to +5)
            valuation_score: Valuation V score (typically -0.5 to +0.5)
            is_bottom_n: Whether this is for bottom-n (bearish) stocks

        Returns:
            Combined score (0-100)
        """
        # Normalize sentiment from [-5, 5] to [0, 100]
        sentiment_normalized = (sentiment_score + 5) / 10 * 100
        sentiment_normalized = max(0, min(100, sentiment_normalized))

        # Normalize valuation from [-0.5, 0.5] to [0, 100]
        # Higher V = more undervalued
        valuation_normalized = (valuation_score + 0.5) / 1.0 * 100
        valuation_normalized = max(0, min(100, valuation_normalized))

        if is_bottom_n:
            # For bearish stocks: high valuation score (undervalued) is good
            # Low sentiment (contrarian) + high valuation = high combined score
            combined = (
                sentiment_normalized * self.weight_sentiment
                + valuation_normalized * self.weight_valuation
            )
        else:
            # For bullish stocks: low valuation score (overvalued) suggests sell
            # High sentiment + low valuation = low combined score (sell signal)
            combined = (
                sentiment_normalized * self.weight_sentiment
                + (100 - valuation_normalized) * self.weight_valuation
            )

        return combined

    def determine_verdict(
        self,
        sentiment_score: float,
        valuation_score: float,
        is_bottom_n: bool,
    ) -> SignalType:
        """
        Determine trading verdict based on sentiment and valuation.

        Args:
            sentiment_score: Raw sentiment score
            valuation_score: Valuation V score
            is_bottom_n: Whether this is for bottom-n (bearish) stocks

        Returns:
            SignalType (BUY, SELL, or HOLD)
        """
        # Sentiment thresholds
        bullish_threshold = 1.5
        bearish_threshold = -1.5

        # Valuation thresholds
        undervalued_threshold = 0.10
        overvalued_threshold = -0.10

        if is_bottom_n:
            # Looking for buy candidates: bearish + undervalued
            if sentiment_score < bearish_threshold and valuation_score > undervalued_threshold:
                return SignalType.BUY
            elif sentiment_score < 0 and valuation_score > 0:
                return SignalType.BUY
            else:
                return SignalType.HOLD
        else:
            # Looking for sell candidates: bullish + overvalued
            if sentiment_score > bullish_threshold and valuation_score < overvalued_threshold:
                return SignalType.SELL
            elif sentiment_score > 0 and valuation_score < 0:
                return SignalType.SELL
            else:
                return SignalType.HOLD

    def analyze_stocks(
        self,
        stocks: list[tuple[str, float]],
        is_bottom_n: bool = True,
    ) -> list[VerdictResult]:
        """
        Analyze a list of stocks and calculate verdicts.

        Args:
            stocks: List of (symbol, sentiment_score) tuples
            is_bottom_n: Whether these are bottom-n (bearish) stocks

        Returns:
            List of VerdictResult objects
        """
        symbols = [s[0] for s in stocks]

        # Get stock names using cache-first strategy
        names_dict = get_stock_names_with_cache(symbols, self.storage)

        # Fetch fundamentals
        fundamentals_dict = self.fetch_fundamentals(symbols)

        results: list[VerdictResult] = []
        for symbol, sentiment_score in stocks:
            name = names_dict.get(symbol, symbol)
            fundamentals = fundamentals_dict.get(symbol)

            if fundamentals is None:
                logger.warning(f"No fundamentals found for {symbol}")
                continue

            # Calculate valuation score
            valuation = self.valuation_calculator.calculate_from_fundamentals(
                fundamentals, self.default_sector
            )
            valuation_score = valuation.composite_score

            # Calculate combined score
            combined_score = self.calculate_combined_score(
                sentiment_score, valuation_score, is_bottom_n
            )

            # Determine verdict
            verdict = self.determine_verdict(sentiment_score, valuation_score, is_bottom_n)

            # Calculate confidence based on agreement between signals
            confidence = 0.5
            if is_bottom_n:
                # Bearish sentiment + undervalued = high confidence
                if sentiment_score < 0 and valuation_score > 0:
                    confidence = min(0.9, 0.5 + abs(sentiment_score) * 0.1 + valuation_score)
            else:
                # Bullish sentiment + overvalued = high confidence
                if sentiment_score > 0 and valuation_score < 0:
                    confidence = min(0.9, 0.5 + abs(sentiment_score) * 0.1 + abs(valuation_score))

            results.append(
                VerdictResult(
                    symbol=symbol,
                    name=name,
                    sentiment_score=sentiment_score,
                    valuation_score=valuation_score,
                    combined_score=combined_score,
                    verdict=verdict,
                    pe_ratio=fundamentals.pe_ratio,
                    pb_ratio=fundamentals.pb_ratio,
                    dividend_yield=fundamentals.dividend_yield,
                    peg_ratio=fundamentals.peg_ratio,
                    confidence=confidence,
                )
            )

        # Sort by combined score
        if is_bottom_n:
            # For bottom-n, higher combined = better buy candidate
            results.sort(key=lambda x: x.combined_score, reverse=True)
        else:
            # For top-n, lower combined = better sell candidate
            results.sort(key=lambda x: x.combined_score)

        return results

    def close(self) -> None:
        """Close database connection."""
        self.storage.close()


def format_table(results: list[VerdictResult], is_bottom_n: bool) -> str:
    """
    Format results as a readable table.

    Args:
        results: List of VerdictResult objects
        is_bottom_n: Whether these are bottom-n stocks

    Returns:
        Formatted table string
    """
    if not results:
        return "No results to display."

    # Header
    header = (
        f"{'Rank':>4} | {'Symbol':<8} | {'Name':<10} | "
        f"{'Sentiment':>9} | {'V Score':>8} | {'Combined':>8} | "
        f"{'Verdict':<6} | {'PE':>8} | {'PB':>6} | {'Div%':>6}"
    )
    separator = "-" * len(header)

    lines = [separator, header, separator]

    for i, r in enumerate(results, 1):
        pe_str = f"{r.pe_ratio:.1f}" if r.pe_ratio is not None else "N/A"
        pb_str = f"{r.pb_ratio:.2f}" if r.pb_ratio is not None else "N/A"
        div_str = f"{r.dividend_yield * 100:.2f}" if r.dividend_yield is not None else "N/A"

        line = (
            f"{i:>4} | {r.symbol:<8} | {r.name[:10]:<10} | "
            f"{r.sentiment_score:>9.2f} | {r.valuation_score:>8.3f} | "
            f"{r.combined_score:>8.1f} | {r.verdict.value:<6} | "
            f"{pe_str:>8} | {pb_str:>6} | {div_str:>6}"
        )
        lines.append(line)

    lines.append(separator)

    # Add legend
    if is_bottom_n:
        lines.append("")
        lines.append("Legend: Bottom-N (Bearish) stocks - Higher Combined = Better BUY candidate")
        lines.append("  Sentiment: Lower = More bearish (contrarian opportunity)")
        lines.append("  V Score: Higher = More undervalued")
    else:
        lines.append("")
        lines.append("Legend: Top-N (Bullish) stocks - Lower Combined = Better SELL candidate")
        lines.append("  Sentiment: Higher = More bullish (potential overvaluation)")
        lines.append("  V Score: Lower = More overvalued")

    return "\n".join(lines)


def format_csv(results: list[VerdictResult]) -> str:
    """Format results as CSV."""
    lines = [
        "symbol,name,sentiment_score,valuation_score,combined_score,verdict,pe_ratio,pb_ratio,dividend_yield,confidence"
    ]
    for r in results:
        pe = r.pe_ratio if r.pe_ratio is not None else ""
        pb = r.pb_ratio if r.pb_ratio is not None else ""
        div = r.dividend_yield if r.dividend_yield is not None else ""
        lines.append(
            f"{r.symbol},{r.name},{r.sentiment_score:.4f},{r.valuation_score:.4f},"
            f"{r.combined_score:.2f},{r.verdict.value},{pe},{pb},{div},{r.confidence:.2f}"
        )
    return "\n".join(lines)


def format_json(results: list[VerdictResult]) -> str:
    """Format results as JSON."""
    data = []
    for r in results:
        data.append(
            {
                "symbol": r.symbol,
                "name": r.name,
                "sentiment_score": r.sentiment_score,
                "valuation_score": r.valuation_score,
                "combined_score": r.combined_score,
                "verdict": r.verdict.value,
                "pe_ratio": r.pe_ratio,
                "pb_ratio": r.pb_ratio,
                "dividend_yield": r.dividend_yield,
                "peg_ratio": r.peg_ratio,
                "confidence": r.confidence,
            }
        )
    return json.dumps(data, indent=2, ensure_ascii=False)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Stock Verdict Analysis - Combined Sentiment + Valuation Ranking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get bottom 10 (contrarian buy candidates)
  uv run python data/verdict.py --bottom-n 10

  # Get top 10 (potential sell candidates)
  uv run python data/verdict.py --top-n 10

  # Output as CSV
  uv run python data/verdict.py --bottom-n 20 --output csv

  # Custom sentiment weight
  uv run python data/verdict.py --bottom-n 10 --weight-sentiment 0.6
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--top-n",
        type=int,
        help="Top N bullish stocks (highest sentiment)",
    )
    group.add_argument(
        "--bottom-n",
        type=int,
        help="Bottom N bearish stocks (lowest sentiment)",
    )

    parser.add_argument(
        "--weight-sentiment",
        type=float,
        default=0.5,
        help="Weight for sentiment in combined score (default: 0.5)",
    )
    parser.add_argument(
        "--output",
        choices=["table", "csv", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/sentiment.db",
        help="Path to DuckDB database (default: data/sentiment.db)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Determine if we're looking at top or bottom
    is_bottom_n = args.bottom_n is not None
    n = args.bottom_n if is_bottom_n else args.top_n

    if n is None or n <= 0:
        print("Error: N must be a positive integer", file=sys.stderr)
        return 1

    # Initialize calculator
    calculator = VerdictCalculator(
        weight_sentiment=args.weight_sentiment,
        db_path=args.db_path,
    )

    try:
        # Get stocks by sentiment
        if is_bottom_n:
            stocks = calculator.get_bottom_n_sentiment(n)
            print(f"\n=== Bottom {n} Stocks by Sentiment (Contrarian BUY Candidates) ===\n")
        else:
            stocks = calculator.get_top_n_sentiment(n)
            print(f"\n=== Top {n} Stocks by Sentiment (Potential SELL Candidates) ===\n")

        if not stocks:
            print("No stocks found in sentiment database.", file=sys.stderr)
            print("Run sentiment collection first: uv run python data/sentiment_collector.py")
            return 1

        # Analyze stocks
        results = calculator.analyze_stocks(stocks, is_bottom_n)

        # Format and output
        if args.output == "table":
            print(format_table(results, is_bottom_n))
        elif args.output == "csv":
            print(format_csv(results))
        elif args.output == "json":
            print(format_json(results))

        return 0

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1

    finally:
        calculator.close()


if __name__ == "__main__":
    sys.exit(main())
