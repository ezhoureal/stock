#!/usr/bin/env python3
"""
Rank ALL A-share stocks based on sentiment score combined with intrinsic value (valuation).

This script implements the contrarian strategy philosophy:
- BUY candidates: Bearish sentiment (< -1.5) + Undervalued (V > +0.10) -> HIGH RANK
- HOLD/Neutral: Sentiment between -1.5 and +1.5 OR valuation near fair value
- SELL candidates: Bullish sentiment (> +1.5) + Overvalued (V < -0.10) -> LOW RANK

Usage:
    uv run python data/rank_stocks.py --universe csi300 --top 10
    uv run python data/rank_stocks.py --universe all --top 20 --signal-type BUY
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from common.types import Fundamentals
from sentiment_strategy.valuation import SectorMetrics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration paths
CONFIG_PATHS = [
    "/home/zireael/trade/stocks/data/config.json",  # Linux server
    Path(__file__).parent / "config.json",  # Local
]


@dataclass
class RankingConfig:
    """Configuration for stock ranking"""

    # Sentiment thresholds (from contrarian strategy)
    bearish_threshold: float = -1.5  # Sentiment < -1.5 is bearish
    bullish_threshold: float = 1.5  # Sentiment > +1.5 is bullish

    # Valuation thresholds (from contrarian strategy)
    undervalued_threshold: float = 0.10  # V > +0.10 is undervalued
    overvalued_threshold: float = -0.10  # V < -0.10 is overvalued

    # Weights for combined score
    sentiment_weight: float = 0.5
    valuation_weight: float = 0.5


@dataclass
class StockRanking:
    """Ranking result for a single stock"""

    rank: int
    stock_code: str
    stock_name: str
    sentiment_score: float
    valuation_score: float
    combined_strength: float
    signal_type: str
    reasons: list[str]


def load_config() -> dict:
    """Load configuration from config.json"""
    for config_path in CONFIG_PATHS:
        if Path(config_path).exists():
            with open(config_path) as f:
                config = json.load(f)
                # Adjust database path if needed
                db_path = config.get("database", {}).get("path", "")
                if db_path.startswith("/home/zireael/") and not Path(db_path).exists():
                    config["database"]["path"] = str(Path(__file__).parent / "stocks.duckdb")
                return config
    raise FileNotFoundError(f"Config file not found in any of: {CONFIG_PATHS}")


def get_stocks_from_db(conn, universe: str = "csi300") -> pd.DataFrame:
    """
    Get stock list from DuckDB database.

    Args:
        conn: DuckDB connection
        universe: "csi300" or "all"

    Returns:
        DataFrame with stock_id, name, ts_code
    """
    if universe == "csi300":
        query = """
            SELECT stock_id, name, ts_code
            FROM stocks
            WHERE is_csi300 = TRUE AND is_active = TRUE AND stock_id != 'SYSTEM'
            ORDER BY stock_id
        """
    else:
        query = """
            SELECT stock_id, name, ts_code
            FROM stocks
            WHERE is_active = TRUE AND stock_id != 'SYSTEM'
            ORDER BY stock_id
        """

    result = conn.execute(query).fetchall()
    df = pd.DataFrame(result, columns=["stock_id", "name", "ts_code"])  # type: ignore[arg-type]
    logger.info(f"Loaded {len(df)} stocks from database (universe={universe})")
    return df


def get_sentiment_scores(
    fetcher, stocks_df: pd.DataFrame, progress: bool = True
) -> dict[str, float]:
    """
    Get sentiment scores for stocks using AKShareSentimentFetcher.

    Args:
        fetcher: AKShareSentimentFetcher instance
        stocks_df: DataFrame with stock_id column
        progress: Show progress bar

    Returns:
        Dict mapping stock_id to sentiment score (-1 to 1)
    """

    sentiment_scores = {}
    total = len(stocks_df)

    # Use lightweight mode for large batches to avoid rate limiting
    # Lightweight mode skips per-stock API calls (fund_flow, northbound)
    is_large_batch = total > 500
    lightweight = is_large_batch

    if is_large_batch:
        logger.info(
            f"Large batch detected ({total} stocks). "
            "Using lightweight mode (skipping per-stock fund flow & northbound data)..."
        )

    for i, (_, row) in enumerate(stocks_df.iterrows()):
        stock_id = str(row["stock_id"])
        idx = i
        if progress and (idx + 1) % 10 == 0:
            logger.info(f"Fetching sentiment: {idx + 1}/{total} stocks...")

        try:
            composite, _ = fetcher.get_composite_sentiment(
                stock_id, include_market=False, lightweight=lightweight
            )
            # Normalize composite to -1 to 1 range (composite can be -2 to 2)
            normalized = np.clip(composite / 2.0, -1.0, 1.0)
            sentiment_scores[stock_id] = normalized
        except Exception as e:
            logger.debug(f"Failed to get sentiment for {stock_id}: {e}")
            sentiment_scores[stock_id] = 0.0  # Neutral if failed

    return sentiment_scores


def get_valuation_scores(
    calculator, conn, stocks_df: pd.DataFrame, progress: bool = True
) -> dict[str, float]:
    """
    Get valuation scores for stocks using ValuationCalculator.

    Uses fundamental data from the database with sector-specific metrics for
    more accurate valuation comparisons. Falls back to market-wide defaults
    if sector data is unavailable.

    Args:
        calculator: ValuationCalculator instance
        conn: DuckDB connection
        stocks_df: DataFrame with stock_id column
        progress: Show progress

    Returns:
        Dict mapping stock_id to valuation score (V)
    """
    valuation_scores = {}
    total = len(stocks_df)

    # Get fundamentals from database (including sector_code)
    fundamentals_data = {}
    try:
        result = conn.execute("""
            SELECT f.stock_id, f.pe, f.pe_ttm, f.pb, f.bps, f.roe, s.sector
            FROM fundamentals f
            LEFT JOIN stocks s ON f.stock_id = s.stock_id
            WHERE f.report_date = (
                SELECT MAX(report_date) FROM fundamentals
            )
        """).fetchall()

        for row in result:
            fundamentals_data[row[0]] = {
                "pe": float(row[1]) if row[1] else None,
                "pe_ttm": float(row[2]) if row[2] else None,
                "pb": float(row[3]) if row[3] else None,
                "bps": float(row[4]) if row[4] else None,
                "roe": float(row[5]) if row[5] else None,
                "sector_code": row[6],  # Sector classification
            }
        logger.info(f"Loaded fundamentals for {len(fundamentals_data)} stocks")
    except Exception as e:
        logger.warning(f"Could not load fundamentals from database: {e}")

    # Load sector metrics from database
    sector_metrics = {}
    try:
        result = conn.execute("""
            SELECT sector_code, pe_ratio, pb_ratio, dividend_yield
            FROM sectors
            WHERE report_date = (SELECT MAX(report_date) FROM sectors)
               OR report_date IS NULL
        """).fetchall()

        for row in result:
            sector_metrics[row[0]] = SectorMetrics(
                pe_ratio=float(row[1]) if row[1] else 15.0,
                pb_ratio=float(row[2]) if row[2] else 2.0,
                dividend_yield=float(row[3]) if row[3] else 0.02,
                peg_ratio=1.5,  # Default PEG if not available
            )
        logger.info(f"Loaded sector metrics for {len(sector_metrics)} sectors")
    except Exception as e:
        logger.warning(f"Could not load sector metrics from database: {e}")

    # Default sector metrics (conservative market-wide defaults)
    default_sector = SectorMetrics(
        pe_ratio=15.0,
        pb_ratio=2.0,
        dividend_yield=0.02,
        peg_ratio=1.5,
    )

    for i, (_, row) in enumerate(stocks_df.iterrows()):
        stock_id = str(row["stock_id"])
        idx = i
        if progress and (idx + 1) % 50 == 1:
            logger.info(f"Calculating valuation: {idx + 1}/{total} stocks...")

        try:
            # Get fundamentals for this stock
            fund_data = fundamentals_data.get(stock_id, {})

            fundamentals = Fundamentals(
                symbol=stock_id,
                timestamp=datetime.now(),
                pe_ratio=fund_data.get("pe"),
                pe_ttm=fund_data.get("pe_ttm"),
                pb_ratio=fund_data.get("pb"),
                book_value_per_share=fund_data.get("bps"),
                roe=fund_data.get("roe") if fund_data.get("roe") is not None else None,
            )

            # Get sector-specific metrics if available
            sector_code = fund_data.get("sector_code")
            if sector_code and sector_code in sector_metrics:
                sector = sector_metrics[sector_code]
                logger.debug(f"Using sector {sector_code} metrics for {stock_id}")
            else:
                sector = default_sector
                if sector_code:
                    logger.debug(f"Sector {sector_code} not found, using defaults for {stock_id}")

            # Calculate valuation score with sector-specific metrics
            valuation = calculator.calculate_from_fundamentals(fundamentals, sector)
            valuation_scores[stock_id] = valuation.composite_score

        except Exception as e:
            logger.debug(f"Failed to calculate valuation for {stock_id}: {e}")
            valuation_scores[stock_id] = 0.0  # Neutral if failed

    return valuation_scores


def determine_signal_type(
    sentiment: float, valuation: float, config: RankingConfig
) -> tuple[str, list[str]]:
    """
    Determine signal type based on contrarian strategy logic.

    Args:
        sentiment: Sentiment score (-1 to 1)
        valuation: Valuation score (V)
        config: Ranking configuration

    Returns:
        Tuple of (signal_type, list of reasons)
    """
    reasons = []

    # Scale sentiment from [-1, 1] to match strategy thresholds
    # Strategy uses threshold of 1.5 for composite sentiment
    # Our normalized sentiment is -1 to 1, so multiply by 3 to approximate
    scaled_sentiment = sentiment * 3.0

    # Check BUY conditions: Bearish sentiment + Undervalued
    is_bearish = scaled_sentiment < config.bearish_threshold
    is_undervalued = valuation > config.undervalued_threshold

    # Check SELL conditions: Bullish sentiment + Overvalued
    is_bullish = scaled_sentiment > config.bullish_threshold
    is_overvalued = valuation < config.overvalued_threshold

    if is_bearish and is_undervalued:
        signal_type = "BUY"
        reasons.append(f"Bearish sentiment: {scaled_sentiment:.2f} < {config.bearish_threshold}")
        reasons.append(f"Undervalued: V={valuation:.3f} > {config.undervalued_threshold}")
    elif is_bullish and is_overvalued:
        signal_type = "SELL"
        reasons.append(f"Bullish sentiment: {scaled_sentiment:.2f} > {config.bullish_threshold}")
        reasons.append(f"Overvalued: V={valuation:.3f} < {config.overvalued_threshold}")
    else:
        signal_type = "HOLD"
        if not is_bearish and not is_bullish:
            reasons.append(f"Neutral sentiment: {scaled_sentiment:.2f}")
        elif is_bearish:
            reasons.append(f"Bearish sentiment: {scaled_sentiment:.2f}")
        else:
            reasons.append(f"Bullish sentiment: {scaled_sentiment:.2f}")

        if not is_undervalued and not is_overvalued:
            reasons.append(f"Fair value: V={valuation:.3f}")
        elif is_undervalued:
            reasons.append(f"Undervalued: V={valuation:.3f}")
        else:
            reasons.append(f"Overvalued: V={valuation:.3f}")

    return signal_type, reasons


def calculate_combined_strength(
    sentiment: float, valuation: float, signal_type: str, config: RankingConfig
) -> float:
    """
    Calculate combined signal strength (0-100).

    For BUY signals: strength = (bearishness + undervaluation) / 2 * 100
    For SELL signals: strength = (bullishness + overvaluation) / 2 * 100
    For HOLD signals: strength = 0

    Args:
        sentiment: Sentiment score (-1 to 1)
        valuation: Valuation score
        signal_type: BUY, SELL, or HOLD
        config: Ranking configuration

    Returns:
        Strength score 0-100
    """
    if signal_type == "HOLD":
        return 0.0

    # Scale sentiment to match strategy thresholds
    scaled_sentiment = sentiment * 3.0

    if signal_type == "BUY":
        # More negative sentiment = stronger buy signal
        sentiment_strength = max(-scaled_sentiment, 0) / abs(config.bearish_threshold)
        # More positive valuation = stronger buy signal
        valuation_strength = max(valuation, 0) / config.undervalued_threshold

        strength = (
            sentiment_strength * config.sentiment_weight
            + valuation_strength * config.valuation_weight
        ) * 100

    else:  # SELL
        # More positive sentiment = stronger sell signal
        sentiment_strength = max(scaled_sentiment, 0) / config.bullish_threshold
        # More negative valuation = stronger sell signal
        valuation_strength = max(-valuation, 0) / abs(config.overvalued_threshold)

        strength = (
            sentiment_strength * config.sentiment_weight
            + valuation_strength * config.valuation_weight
        ) * 100

    return float(np.clip(strength, 0, 100))


def rank_stocks(
    stocks_df: pd.DataFrame,
    sentiment_scores: dict[str, float],
    valuation_scores: dict[str, float],
    config: RankingConfig,
    signal_filter: str | None = None,
) -> list[StockRanking]:
    """
    Rank stocks based on combined sentiment and valuation.

    Args:
        stocks_df: DataFrame with stock info
        sentiment_scores: Dict of sentiment scores
        valuation_scores: Dict of valuation scores
        config: Ranking configuration
        signal_filter: Filter by signal type (BUY, SELL, HOLD, or None for all)

    Returns:
        List of StockRanking objects, sorted by combined strength (descending)
    """
    rankings = []

    for _, row in stocks_df.iterrows():
        stock_id = str(row["stock_id"])
        stock_name = str(row["name"])

        sentiment = sentiment_scores.get(stock_id, 0.0)
        valuation = valuation_scores.get(stock_id, 0.0)

        signal_type, reasons = determine_signal_type(sentiment, valuation, config)

        # Apply filter if specified
        if signal_filter and signal_type != signal_filter:
            continue

        strength = calculate_combined_strength(sentiment, valuation, signal_type, config)

        rankings.append(
            StockRanking(
                rank=0,  # Will be set after sorting
                stock_code=stock_id,
                stock_name=stock_name,
                sentiment_score=sentiment,
                valuation_score=valuation,
                combined_strength=strength,
                signal_type=signal_type,
                reasons=reasons,
            )
        )

    # Sort by combined strength (descending), then by signal type priority
    signal_priority = {"BUY": 0, "HOLD": 1, "SELL": 2}
    rankings.sort(key=lambda x: (-x.combined_strength, signal_priority[x.signal_type]))

    # Assign ranks
    for i, ranking in enumerate(rankings, 1):
        ranking.rank = i

    return rankings


def print_rankings(rankings: list[StockRanking], top_n: int = 20) -> None:
    """Print top N rankings to console."""
    print("\n" + "=" * 100)
    print(f"TOP {top_n} STOCK RANKINGS - Contrarian Strategy")
    print("=" * 100)
    print(
        f"{'Rank':<6} {'Code':<8} {'Name':<12} {'Sentiment':<12} {'Valuation':<12} "
        f"{'Strength':<10} {'Signal':<8}"
    )
    print("-" * 100)

    for ranking in rankings[:top_n]:
        print(
            f"{ranking.rank:<6} {ranking.stock_code:<8} {ranking.stock_name[:12]:<12} "
            f"{ranking.sentiment_score:>10.3f}  {ranking.valuation_score:>10.3f}  "
            f"{ranking.combined_strength:>8.1f}  {ranking.signal_type:<8}"
        )

    print("-" * 100)

    # Print summary statistics
    buy_count = sum(1 for r in rankings if r.signal_type == "BUY")
    sell_count = sum(1 for r in rankings if r.signal_type == "SELL")
    hold_count = sum(1 for r in rankings if r.signal_type == "HOLD")

    print(
        f"\nSummary: {buy_count} BUY | {hold_count} HOLD | {sell_count} SELL (Total: {len(rankings)})"
    )

    # Print top BUY candidates details
    buy_candidates = [r for r in rankings if r.signal_type == "BUY"][:5]
    if buy_candidates:
        print("\n" + "=" * 100)
        print("TOP BUY CANDIDATES (Bearish Sentiment + Undervalued)")
        print("=" * 100)
        for ranking in buy_candidates:
            print(f"\n#{ranking.rank} {ranking.stock_code} - {ranking.stock_name}")
            print(
                f"  Sentiment: {ranking.sentiment_score:.3f} | Valuation: {ranking.valuation_score:.3f}"
            )
            print(f"  Strength: {ranking.combined_strength:.1f}")
            print("  Reasons:")
            for reason in ranking.reasons:
                print(f"    - {reason}")


def save_to_csv(rankings: list[StockRanking], output_dir: Path) -> Path:
    """Save rankings to CSV file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y%m%d")
    output_path = output_dir / f"stock_rankings_{date_str}.csv"

    # Convert to DataFrame
    data = []
    for r in rankings:
        data.append(
            {
                "rank": r.rank,
                "stock_code": r.stock_code,
                "stock_name": r.stock_name,
                "sentiment_score": r.sentiment_score,
                "valuation_score": r.valuation_score,
                "combined_strength": r.combined_strength,
                "signal_type": r.signal_type,
                "reasons": "; ".join(r.reasons),
            }
        )

    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    logger.info(f"Saved {len(rankings)} rankings to {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Rank A-share stocks based on sentiment and valuation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python data/rank_stocks.py --universe csi300 --top 10
    uv run python data/rank_stocks.py --universe all --top 20 --signal-type BUY
        """,
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of top stocks to display (default: 20)",
    )
    parser.add_argument(
        "--signal-type",
        choices=["BUY", "SELL", "HOLD"],
        default=None,
        help="Filter by signal type (default: show all)",
    )
    parser.add_argument(
        "--universe",
        choices=["csi300", "all"],
        default="csi300",
        help="Stock universe: csi300 (faster) or all (comprehensive)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress messages",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for CSV (default: data/output)",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config()
    ranking_config = RankingConfig()

    # Setup output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(__file__).parent / "output"

    try:
        import duckdb
    except ImportError:
        logger.error("duckdb not installed. Install with: uv pip install duckdb")
        sys.exit(1)

    # Connect to database
    db_path = config["database"]["path"]
    logger.info(f"Connecting to database: {db_path}")
    conn = duckdb.connect(db_path, read_only=True)

    try:
        # Get stock list
        stocks_df = get_stocks_from_db(conn, args.universe)
        if stocks_df.empty:
            logger.error("No stocks found in database. Run collect_all_ashare.py first.")
            sys.exit(1)

        # Initialize sentiment fetcher
        try:
            from data.collect_sentiment import AKShareSentimentFetcher

            sentiment_fetcher = AKShareSentimentFetcher()
            logger.info("Initialized AKShare sentiment fetcher")
        except ImportError as e:
            logger.error(f"Failed to import sentiment fetcher: {e}")
            sys.exit(1)

        # Initialize valuation calculator
        from sentiment_strategy.valuation import ValuationCalculator

        valuation_calculator = ValuationCalculator()
        logger.info("Initialized valuation calculator")

        # Get sentiment scores
        logger.info(f"Fetching sentiment scores for {len(stocks_df)} stocks...")
        sentiment_scores = get_sentiment_scores(
            sentiment_fetcher, stocks_df, progress=not args.no_progress
        )

        # Get valuation scores
        logger.info(f"Calculating valuation scores for {len(stocks_df)} stocks...")
        valuation_scores = get_valuation_scores(
            valuation_calculator, conn, stocks_df, progress=not args.no_progress
        )

        # Rank stocks
        logger.info("Ranking stocks...")
        rankings = rank_stocks(
            stocks_df,
            sentiment_scores,
            valuation_scores,
            ranking_config,
            signal_filter=args.signal_type,
        )

        if not rankings:
            logger.warning("No stocks matched the criteria")
            print("\nNo stocks matched the specified criteria.")
            sys.exit(0)

        # Print results
        print_rankings(rankings, top_n=args.top)

        # Save to CSV
        csv_path = save_to_csv(rankings, output_dir)
        print(f"\nFull rankings saved to: {csv_path}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
