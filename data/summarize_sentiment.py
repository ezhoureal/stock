"""
Summarize sentiment data from the database.

Usage:
    python -m data.summarize_sentiment --top 10
    python -m data.summarize_sentiment --bottom 20
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from data.storage import SentimentStorage

logger = logging.getLogger(__name__)


def fetch_stock_names_from_api(symbols: list[str]) -> dict[str, str]:
    """Fetch stock names from AKShare API."""
    try:
        import akshare as ak

        df = ak.stock_zh_a_spot_em()
        name_map: dict[str, str] = {}
        for _, row in df.iterrows():
            symbol = str(row.get("代码", ""))
            name = str(row.get("名称", ""))
            if symbol in symbols and name:
                name_map[symbol] = name
        return name_map
    except Exception as e:
        logger.warning(f"Failed to fetch stock names from API: {e}")
        return {}


def get_latest_sentiment(
    storage: SentimentStorage, limit: int, order: str
) -> list[tuple[str, float, float, dict]]:
    """
    Get latest sentiment scores from database.

    Args:
        storage: SentimentStorage instance
        limit: Number of results
        order: "DESC" for top, "ASC" for bottom

    Returns:
        List of (symbol, score, confidence, source_scores) tuples
    """
    import json

    conn = storage._get_connection()

    # Get the latest composite score for each symbol
    query = f"""
        WITH latest AS (
            SELECT symbol, timestamp, score, confidence, source_scores,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) as rn
            FROM sentiment_composite
        )
        SELECT symbol, score, confidence, source_scores
        FROM latest
        WHERE rn = 1
        ORDER BY score {order}
        LIMIT ?
    """

    results: list[tuple[str, float, float, dict]] = []
    for row in conn.execute(query, [limit]).fetchall():
        symbol, score, confidence, source_scores_str = row
        source_scores = json.loads(source_scores_str) if source_scores_str else {}
        results.append((symbol, score, confidence, source_scores))

    return results


def format_source_scores(source_scores: dict[str, float]) -> str:
    """Format source scores for display."""
    if not source_scores:
        return "N/A"

    parts = []
    for source, score in sorted(source_scores.items()):
        parts.append(f"{source[:3]}:{score:+.2f}")
    return " ".join(parts)


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
        print(f"Fetching {len(missing_symbols)} missing names from API...")
        api_names = fetch_stock_names_from_api(missing_symbols)

        if api_names:
            # Update cache with new names
            storage.update_stock_names(api_names)
            cached_names.update(api_names)
            print(f"Updated cache with {len(api_names)} new names")

    return cached_names


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize sentiment data")
    parser.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Show top N stocks by sentiment",
    )
    parser.add_argument(
        "--bottom",
        type=int,
        metavar="N",
        help="Show bottom N stocks by sentiment",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/sentiment.db",
        help="Path to DuckDB database (default: data/sentiment.db)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show source score breakdown",
    )

    args = parser.parse_args()

    if args.top is None and args.bottom is None:
        parser.print_help()
        return

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return

    # Initialize storage (creates stock_names table if needed)
    storage = SentimentStorage(db_path)

    # Collect all symbols we need names for
    all_symbols: list[str] = []
    if args.top:
        results = get_latest_sentiment(storage, args.top, "DESC")
        all_symbols.extend(r[0] for r in results)
    if args.bottom:
        results = get_latest_sentiment(storage, args.bottom, "ASC")
        all_symbols.extend(r[0] for r in results)

    # Get stock names using cache
    stock_names = get_stock_names_with_cache(all_symbols, storage)

    def display_results(results: list[tuple[str, float, float, dict]], title: str) -> None:
        """Display sentiment results in formatted table."""
        print(f"=== {title} ===\n")
        for i, (symbol, score, confidence, source_scores) in enumerate(results, 1):
            name = stock_names.get(symbol, "N/A")
            if args.verbose:
                sources = format_source_scores(source_scores)
                print(
                    f"{i:2}. {symbol} ({name})\n"
                    f"    Score: {score:+.3f} | Confidence: {confidence:.2f}\n"
                    f"    Sources: {sources}"
                )
            else:
                print(f"{i:2}. {symbol:6} {name:8} | Score: {score:+.3f} | Conf: {confidence:.2f}")

    if args.top:
        results = get_latest_sentiment(storage, args.top, "DESC")
        display_results(results, f"Top {args.top} Sentiment Stocks")

    if args.bottom:
        if args.top:
            print()
        results = get_latest_sentiment(storage, args.bottom, "ASC")
        display_results(results, f"Bottom {args.bottom} Sentiment Stocks")


if __name__ == "__main__":
    main()
