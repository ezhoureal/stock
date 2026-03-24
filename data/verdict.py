"""
Verdict Calculator combining sentiment and valuation data.

This module refactors and extends the functionality from summarize_sentiment.py
to combine stored sentiment data (from DuckDB) with live valuation data (from AKShare)
into unified trading verdicts using contrarian strategy logic.

Usage:
    python -m data.verdict --top 20
    python -m data.verdict --bottom 20
    python -m data.verdict --symbols 600519,000001
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

from common.types import SignalType, VerdictScore
from data.providers import ValuationDataProvider
from data.storage import SentimentStorage

logger = logging.getLogger(__name__)


class VerdictCalculator:
    """
    Combines stored sentiment + live valuation into verdict.

    Uses contrarian strategy logic:
    - BUY: Bearish sentiment + Undervalued fundamentals
    - SELL: Bullish sentiment + Overvalued fundamentals
    - HOLD: Mixed or neutral signals

    Hardcoded thresholds for simplicity:
    - Sentiment bearish: < -0.3
    - Sentiment bullish: > 0.3
    - Valuation undervalued: > 0.10
    - Valuation overvalued: < -0.10
    - Strong threshold: >= 0.7
    - Moderate threshold: >= 0.3
    """

    # Hardcoded thresholds
    SENTIMENT_BEARISH = -0.3
    SENTIMENT_BULLISH = 0.3
    VALUATION_UNDERVALUED = 0.10
    VALUATION_OVERVALUED = -0.10
    STRONG_THRESHOLD = 0.7
    MODERATE_THRESHOLD = 0.3

    def __init__(
        self, storage: SentimentStorage, valuation_provider: ValuationDataProvider
    ) -> None:
        """
        Initialize VerdictCalculator.

        Args:
            storage: SentimentStorage instance for retrieving stored sentiment data
            valuation_provider: ValuationDataProvider instance for live valuation data
        """
        self.storage = storage
        self.valuation_provider = valuation_provider

    def compute_verdict(self, symbols: list[str]) -> dict[str, VerdictScore]:
        """
        Compute verdict for given symbols.

        Process:
        1. Get latest sentiment from DB (SentimentStorage.get_latest_composite)
        2. Get live valuation (ValuationDataProvider.calculate_v_scores)
        3. Combine into VerdictScore using contrarian logic

        Args:
            symbols: List of stock symbols to compute verdicts for

        Returns:
            Dictionary mapping symbol to VerdictScore
        """
        # Get latest sentiment from database
        sentiment_scores = self.storage.get_latest_composite(symbols)

        # Get live valuation from AKShare
        valuation_scores = self.valuation_provider.calculate_v_scores(symbols)

        # Compute verdicts
        verdicts: dict[str, VerdictScore] = {}
        timestamp = datetime.now()

        for symbol in symbols:
            # Get sentiment score (default to 0 if not found)
            sentiment_data = sentiment_scores.get(symbol)
            sentiment_score = sentiment_data.score if sentiment_data else 0.0

            # Get valuation score (default to 0 if not found)
            valuation_score = valuation_scores.get(symbol, 0.0)

            # Compute verdict using contrarian logic
            verdict, score, confidence = self._compute_verdict_score(
                sentiment_score, valuation_score
            )

            # Build source scores from sentiment data
            source_scores = (
                sentiment_data.metadata.get("source_scores", {}) if sentiment_data else {}
            )

            verdicts[symbol] = VerdictScore(
                symbol=symbol,
                timestamp=timestamp,
                verdict=verdict,
                score=score,
                confidence=confidence,
                sentiment_score=sentiment_score,
                valuation_score=valuation_score,
                metadata={"source_scores": source_scores},
            )

        return verdicts

    def _compute_verdict_score(
        self, sentiment: float, valuation: float
    ) -> tuple[SignalType, float, float]:
        """
        Compute verdict score from sentiment and valuation using contrarian logic.

        Magnitude represents signal strength:
        - Strong BUY/SELL: 0.7 to 1.0
        - Moderate BUY/SELL: 0.4 to 0.7
        - Weak BUY/SELL: 0.0 to 0.4
        - HOLD: 0.0

        Args:
            sentiment: Sentiment score (-1 to 1)
            valuation: Valuation score (typically -0.5 to 0.5)

        Returns:
            Tuple of (verdict type, composite score, confidence)
        """
        # BUY signals (contrarian: bearish + undervalued)
        if sentiment < self.SENTIMENT_BEARISH and valuation > self.VALUATION_UNDERVALUED:
            base = 0.6
            strength_boost = min(0.4, abs(sentiment) * 0.3 + valuation * 0.2)
            score = base + strength_boost  # 0.6 to 1.0

            # Confidence based on agreement (normalized to 0-1)
            # Both pointing to buy: high confidence
            norm_sentiment = (self.SENTIMENT_BEARISH - sentiment) / abs(self.SENTIMENT_BEARISH)
            norm_valuation = valuation / self.VALUATION_UNDERVALUED
            confidence = (norm_sentiment + norm_valuation) / 2
            confidence = max(0.0, min(1.0, confidence))

            return SignalType.BUY, score, confidence

        # SELL signals (contrarian: bullish + overvalued)
        elif sentiment > self.SENTIMENT_BULLISH and valuation < self.VALUATION_OVERVALUED:
            base = 0.6
            strength_boost = min(0.4, sentiment * 0.3 + abs(valuation) * 0.2)
            score = -(base + strength_boost)  # -0.6 to -1.0

            # Confidence based on agreement
            norm_sentiment = sentiment / self.SENTIMENT_BULLISH
            norm_valuation = (self.VALUATION_OVERVALUED - valuation) / abs(
                self.VALUATION_OVERVALUED
            )
            confidence = (norm_sentiment + norm_valuation) / 2
            confidence = max(0.0, min(1.0, confidence))

            return SignalType.SELL, score, confidence

        # HOLD signals (mixed/neutral)
        else:
            # For HOLD, we still calculate a small bias based on individual signals
            # but keep score close to 0
            if sentiment < self.SENTIMENT_BEARISH:
                score = 0.2  # Weak buy signal (bearish only)
            elif sentiment > self.SENTIMENT_BULLISH:
                score = -0.2  # Weak sell signal (bullish only)
            elif valuation > self.VALUATION_UNDERVALUED:
                score = 0.15  # Weak buy signal (undervalued only)
            elif valuation < self.VALUATION_OVERVALUED:
                score = -0.15  # Weak sell signal (overvalued only)
            else:
                score = 0.0  # Neutral

            # Low confidence for HOLD signals
            confidence = 0.3

            return SignalType.HOLD, score, confidence

    def get_top_verdicts(self, limit: int = 20) -> list[VerdictScore]:
        """
        Get top N buy verdicts.

        Queries all stocks with sentiment data and returns those with
        the highest BUY scores.

        Args:
            limit: Maximum number of verdicts to return

        Returns:
            List of VerdictScore objects sorted by score descending
        """
        # Get all symbols from sentiment database
        conn = self.storage._get_connection()
        result = conn.execute("""
            SELECT DISTINCT symbol
            FROM sentiment_composite
            ORDER BY symbol
        """).fetchall()

        all_symbols = [row[0] for row in result]

        if not all_symbols:
            logger.warning("No symbols found in sentiment database")
            return []

        # Compute verdicts for all symbols
        logger.info(f"Computing verdicts for {len(all_symbols)} symbols...")
        verdicts = self.compute_verdict(all_symbols)

        # Filter and sort by score
        buy_verdicts = [v for v in verdicts.values() if v.is_buy_signal]
        buy_verdicts.sort(key=lambda x: x.score, reverse=True)

        return buy_verdicts[:limit]

    def get_bottom_verdicts(self, limit: int = 20) -> list[VerdictScore]:
        """
        Get bottom N sell verdicts.

        Queries all stocks with sentiment data and returns those with
        the lowest SELL scores.

        Args:
            limit: Maximum number of verdicts to return

        Returns:
            List of VerdictScore objects sorted by score ascending
        """
        # Get all symbols from sentiment database
        conn = self.storage._get_connection()
        result = conn.execute("""
            SELECT DISTINCT symbol
            FROM sentiment_composite
            ORDER BY symbol
        """).fetchall()

        all_symbols = [row[0] for row in result]

        if not all_symbols:
            logger.warning("No symbols found in sentiment database")
            return []

        # Compute verdicts for all symbols
        logger.info(f"Computing verdicts for {len(all_symbols)} symbols...")
        verdicts = self.compute_verdict(all_symbols)

        # Filter and sort by score
        sell_verdicts = [v for v in verdicts.values() if v.is_sell_signal]
        sell_verdicts.sort(key=lambda x: x.score)

        return sell_verdicts[:limit]


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
        print("Fetching all stock names from API...")
        df = fetch_all_stock_names_from_api()

        if df is not None:
            # Cache ALL names for future use (DuckDB reads DataFrame directly)
            count = storage.update_stock_names_from_df(df)
            print(f"Updated cache with {count} total names")
            # Get the names we need from cache
            cached_names = storage.get_stock_names(symbols)

    return cached_names


def display_verdicts(
    verdicts: list[VerdictScore],
    stock_names: dict[str, str],
    title: str,
    verbose: bool = False,
) -> None:
    """Display verdicts in formatted table."""
    print(f"=== {title} ===\n")
    for i, verdict in enumerate(verdicts, 1):
        name = stock_names.get(verdict.symbol, "N/A")
        strength = verdict.signal_strength

        if verbose:
            sources = format_source_scores(verdict.metadata.get("source_scores", {}))
            print(
                f"{i:2}. {verdict.symbol} ({name})\n"
                f"    Verdict: {verdict.verdict.value} | Score: {verdict.score:+.2f} | "
                f"Strength: {strength} | Conf: {verdict.confidence:.2f}\n"
                f"    Sentiment: {verdict.sentiment_score:+.2f} | "
                f"Valuation: {verdict.valuation_score:+.2f}\n"
                f"    Sources: {sources}"
            )
        else:
            print(
                f"{i:2}. {verdict.symbol:6} {name:12} | "
                f"Verdict: {verdict.verdict.value:4} | Score: {verdict.score:+.2f} | "
                f"Strength: {strength:6} | Conf: {verdict.confidence:.2f}"
            )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Combined Sentiment + Valuation Verdict Calculator"
    )
    parser.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Show top N BUY verdicts",
    )
    parser.add_argument(
        "--bottom",
        type=int,
        metavar="N",
        help="Show bottom N SELL verdicts",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        metavar="X,Y,Z",
        help="Show verdicts for specific symbols (comma-separated)",
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

    if args.top is None and args.bottom is None and args.symbols is None:
        parser.print_help()
        return

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return

    # Initialize storage and providers
    storage = SentimentStorage(db_path)
    valuation_provider = ValuationDataProvider()
    calculator = VerdictCalculator(storage, valuation_provider)

    # Collect all symbols we need names for
    all_symbols: list[str] = []

    if args.top:
        top_verdicts = calculator.get_top_verdicts(args.top)
        all_symbols.extend(v.symbol for v in top_verdicts)

    if args.bottom:
        bottom_verdicts = calculator.get_bottom_verdicts(args.bottom)
        all_symbols.extend(v.symbol for v in bottom_verdicts)

    if args.symbols:
        symbol_list = [s.strip() for s in args.symbols.split(",")]
        all_symbols.extend(symbol_list)

    # Get stock names using cache
    if all_symbols:
        stock_names = get_stock_names_with_cache(list(set(all_symbols)), storage)
    else:
        stock_names = {}

    # Display results
    if args.top:
        display_verdicts(
            top_verdicts,
            stock_names,
            f"Top {args.top} Verdicts (BUY)",
            args.verbose,
        )

    if args.bottom:
        if args.top:
            print()
        display_verdicts(
            bottom_verdicts,
            stock_names,
            f"Bottom {args.bottom} Verdicts (SELL)",
            args.verbose,
        )

    if args.symbols:
        symbol_list = [s.strip() for s in args.symbols.split(",")]
        verdicts = calculator.compute_verdict(symbol_list)
        verdict_list = [verdicts[s] for s in symbol_list if s in verdicts]

        if args.top or args.bottom:
            print()

        display_verdicts(
            verdict_list,
            stock_names,
            f"Verdicts for {args.symbols}",
            args.verbose,
        )


if __name__ == "__main__":
    main()
