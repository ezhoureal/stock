"""
Main sentiment collector orchestrator.

Coordinates batch queries, computes composite scores, and persists to DuckDB.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from common.types import SentimentScore
from data.providers import SentimentDataProvider
from data.storage import SentimentStorage

logger = logging.getLogger(__name__)


class SentimentCollector:
    """
    Orchestrates sentiment data collection from multiple sources.

    Fetches sentiment from 4 sources, computes composite scores,
    and persists to DuckDB for use by trading strategies.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        """
        Initialize the sentiment collector.

        Args:
            config_path: Path to config.json file
        """
        self.config = self._load_config(config_path)
        self.provider = SentimentDataProvider(self.config.get("sentiment"))
        self.storage = SentimentStorage(self.config["database"]["path"])

        # Get sentiment weights from config
        weights = self.config.get("sentiment", {}).get("weights", {})
        self.weights = {
            "news": weights.get("news", 0.40),
            "social": weights.get("social", 0.35),
            "search": weights.get("search", 0.15),
            "forum": weights.get("forum", 0.10),
        }

    def _load_config(self, config_path: str | Path | None) -> dict:
        """Load configuration from JSON file."""
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"

        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_file}, using defaults")
            return self._default_config()

        with open(config_file, encoding="utf-8") as f:
            return json.load(f)

    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            "database": {"path": "data/sentiment.db", "batch_size": 1000},
            "sentiment": {"weights": {"news": 0.40, "social": 0.35, "search": 0.15, "forum": 0.10}},
        }

    def collect_daily(self) -> dict[str, list[SentimentScore]]:
        """
        Collect sentiment data from all sources.

        Returns:
            Dictionary mapping source to list of SentimentScore objects
        """
        logger.info("Starting daily sentiment collection")

        all_scores = self.provider.get_all_sentiment()

        # Group by source
        scores_by_source: dict[str, list[SentimentScore]] = {
            "news": [],
            "social": [],
            "search": [],
            "forum": [],
        }

        for score in all_scores:
            if score.source in scores_by_source:
                scores_by_source[score.source].append(score)

        # Log summary
        for source, scores in scores_by_source.items():
            logger.info(f"Collected {len(scores)} {source} sentiment scores")

        return scores_by_source

    def compute_composite(
        self, scores_by_source: dict[str, list[SentimentScore]]
    ) -> dict[str, SentimentScore]:
        """
        Compute composite sentiment scores per symbol.

        Args:
            scores_by_source: Dictionary of source -> list of SentimentScore

        Returns:
            Dictionary mapping symbol to composite SentimentScore
        """
        composite_scores: dict[str, SentimentScore] = {}

        # Collect all unique symbols
        all_symbols = set()
        for scores in scores_by_source.values():
            for score in scores:
                all_symbols.add(score.symbol)

        timestamp = datetime.now()

        for symbol in all_symbols:
            source_scores: dict[str, tuple[float, float]] = {}
            total_weight = 0.0
            weighted_sum = 0.0
            confidence_sum = 0.0
            valid_sources = 0

            # Aggregate scores from each source
            for source, scores in scores_by_source.items():
                # Find latest score for this symbol from this source
                source_score = next((s for s in scores if s.symbol == symbol), None)

                if source_score:
                    weight = self.weights.get(source, 0.0)
                    source_scores[source] = (source_score.score, source_score.confidence)

                    weighted_sum += source_score.score * weight
                    total_weight += weight
                    confidence_sum += source_score.confidence
                    valid_sources += 1

            # Compute composite score
            if total_weight > 0 and valid_sources > 0:
                composite_score = weighted_sum / total_weight
                composite_confidence = confidence_sum / valid_sources

                composite_scores[symbol] = SentimentScore(
                    symbol=symbol,
                    timestamp=timestamp,
                    score=composite_score,
                    confidence=composite_confidence,
                    source="composite",
                    raw_score=composite_score,
                    metadata={
                        "source_scores": {s: v[0] for s, v in source_scores.items()},
                        "valid_sources": valid_sources,
                    },
                )

        logger.info(f"Computed {len(composite_scores)} composite sentiment scores")
        return composite_scores

    def persist(
        self,
        scores_by_source: dict[str, list[SentimentScore]],
        composite_scores: dict[str, SentimentScore],
    ) -> dict[str, int]:
        """
        Persist sentiment scores to storage.

        Args:
            scores_by_source: Raw scores by source
            composite_scores: Composite scores by symbol

        Returns:
            Dictionary with counts of stored records
        """
        counts = {"raw": 0, "composite": 0}

        # Store raw scores
        for _source, scores in scores_by_source.items():
            stored = self.storage.store_raw_scores(scores)
            counts["raw"] += stored

        # Store composite scores
        for _symbol, score in composite_scores.items():
            source_scores = score.metadata.get("source_scores", {})
            if self.storage.store_composite_score(
                symbol=score.symbol,
                timestamp=score.timestamp,
                score=score.score,
                confidence=score.confidence,
                source_scores=source_scores,
            ):
                counts["composite"] += 1

        logger.info(f"Persisted {counts['raw']} raw and {counts['composite']} composite scores")
        return counts

    def run_collection(self) -> dict[str, int]:
        """
        Run the full collection pipeline.

        Returns:
            Dictionary with counts of stored records
        """
        # Rate limiting
        rate_limits = self.config.get("rate_limits", {})
        cooldown = rate_limits.get("batch_cooldown_seconds", 1)

        try:
            # Collect from all sources
            scores_by_source = self.collect_daily()
            time.sleep(cooldown)

            # Compute composite scores
            composite_scores = self.compute_composite(scores_by_source)

            # Persist to storage
            counts = self.persist(scores_by_source, composite_scores)

            return counts
        except Exception as e:
            logger.error(f"Error during collection: {e}")
            raise

    def get_latest_sentiment(self, symbols: list[str]) -> dict[str, SentimentScore]:
        """
        Get latest composite sentiment for symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to latest SentimentScore
        """
        return self.storage.get_latest_composite(symbols)

    def get_sentiment_history(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        source: str | None = None,
    ) -> list[SentimentScore]:
        """
        Get sentiment history for symbols.

        Args:
            symbols: List of stock symbols
            start: Start datetime
            end: End datetime
            source: Filter by source

        Returns:
            List of SentimentScore objects
        """
        return self.storage.get_sentiment(symbols, start, end, source)


def main() -> None:
    """CLI entry point for sentiment collection."""
    parser = argparse.ArgumentParser(description="Collect sentiment data for Chinese stocks")
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols to query (for testing)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.json file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        collector = SentimentCollector(args.config)

        if args.symbols:
            # Query latest sentiment for specific symbols
            symbols = [s.strip() for s in args.symbols.split(",")]
            latest = collector.get_latest_sentiment(symbols)

            print(f"\nLatest sentiment for {len(latest)} symbols:")
            for symbol, score in latest.items():
                print(
                    f"  {symbol}: {score.score:+.3f} "
                    f"(confidence: {score.confidence:.2f}, source: {score.source})"
                )
        else:
            # Run full collection pipeline
            print("Starting sentiment collection...")
            counts = collector.run_collection()

            print("\nCollection complete:")
            print(f"  Raw scores stored: {counts['raw']}")
            print(f"  Composite scores stored: {counts['composite']}")

    except KeyboardInterrupt:
        print("\nCollection interrupted")
    except Exception as e:
        logger.error(f"Collection failed: {e}")
        raise


if __name__ == "__main__":
    main()
