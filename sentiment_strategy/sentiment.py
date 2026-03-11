"""
Sentiment Module - Chinese Stock Sentiment Trading System

Calculates sentiment scores from multiple sources (news, social media, search volume)
for Chinese stocks.
"""

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class SentimentConfig:
    """Configuration for sentiment calculations"""

    # Source weights
    news_weight: float = 0.40
    social_weight: float = 0.35
    search_weight: float = 0.15
    forum_weight: float = 0.10

    # Smoothing
    ema_alpha: float = 0.2  # EMA smoothing factor
    roc_threshold: float = 1.0  # Rate of change threshold

    # Scoring range
    min_score: float = -5.0
    max_score: float = 5.0

    # Thresholds for interpretation
    extreme_bearish: float = -3.0
    bearish: float = -1.5
    bullish: float = 1.5
    extreme_bullish: float = 3.0

    # BUG-005: Cold start fallback configuration
    min_observations_for_stats: int = 10  # Minimum observations for reliable z-score
    fallback_threshold_abs: float = 2.0  # Absolute threshold for fallback mode


@dataclass
class SentimentSource:
    """Sentiment data from a single source"""

    source: str  # 'news', 'social', 'search', 'forum'
    timestamp: datetime  # When the data was collected
    raw_sentiment: float  # Raw sentiment [-1, 1] before weighting
    normalized: float  # Normalized [-1, 1]
    confidence: float  # Confidence score [0, 1]
    metadata: dict | None  # Additional metadata

    def __post_init__(self) -> None:
        """Validate confidence is in valid range [0, 1]."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0 and 1, got {self.confidence}")


@dataclass
class SentimentResult:
    """Complete sentiment analysis result"""

    symbol: str
    timestamp: datetime
    total_score: float  # S_total [-5, 5]
    smoothed_score: float  # EMA-smoothed
    roc: float  # Rate of change
    interpretation: str  # Text interpretation
    source_scores: dict[str, float]  # Score by source
    confidences: dict[str, float]  # Confidence by source
    signals: dict[str, bool]  # Signal flags (rapid_deterioration, rapid_improvement, etc.)


class SentimentAnalyzer:
    """
    Analyzes sentiment from multiple sources for Chinese stocks.
    """

    def __init__(self, config: SentimentConfig | None = None):
        """
        Initialize the sentiment analyzer.

        Args:
            config: Sentiment configuration (uses defaults if None)
        """
        self.config = config or SentimentConfig()
        # Store RAW scores for accurate ROC calculation (BUG-006 fix)
        self._historical_raw_scores: dict[str, list[float]] = {}
        # Store smoothed scores for historical tracking
        self._historical_scores: dict[str, list[float]] = {}
        self._historical_timestamps: dict[str, list[datetime]] = {}
        # BUG-016: Thread safety lock for concurrent access to historical scores
        self._lock = threading.Lock()

    def normalize_sentiment(
        self, raw_sentiment: float, min_val: float = -1.0, max_val: float = 1.0
    ) -> float:
        """
        Normalize raw sentiment to [-1, 1] range.

        Args:
            raw_sentiment: Raw sentiment value
            min_val: Expected minimum value
            max_val: Expected maximum value

        Returns:
            Normalized sentiment in [-1, 1]
        """
        # Clip to expected range
        clipped = np.clip(raw_sentiment, min_val, max_val)

        # Normalize to [-1, 1]
        normalized = 2 * (clipped - min_val) / (max_val - min_val) - 1

        return float(normalized)

    def apply_weight(self, sentiment: float, weight: float) -> float:
        """
        Apply source weight to sentiment score.

        Args:
            sentiment: Normalized sentiment [-1, 1]
            weight: Source weight [0, 1]

        Returns:
            Weighted sentiment
        """
        return sentiment * weight

    def calculate_total_score(
        self, source_sentiments: dict[str, float], weights: dict[str, float]
    ) -> float:
        """
        Calculate total sentiment score from multiple sources.

        S_total = sum(sentiment_i * weight_i) * 5

        Args:
            source_sentiments: Dict of source -> normalized sentiment [-1, 1]
            weights: Dict of source -> weight (sum to 1.0)

        Returns:
            Total sentiment score in [-5, 5]
        """
        weighted_sum = 0.0
        total_weight = 0.0

        for source, sentiment in source_sentiments.items():
            weight = weights.get(source, 0.0)
            weighted_sum += sentiment * weight
            total_weight += weight

        # Normalize weights if they don't sum to 1
        if total_weight > 0:
            weighted_sum /= total_weight

        # Scale to [-5, 5] range
        total_score = weighted_sum * 5

        return np.clip(total_score, self.config.min_score, self.config.max_score)

    def smooth_score(
        self, current_score: float, symbol: str, timestamp: datetime | None = None
    ) -> float:
        """
        Apply EMA smoothing to sentiment score.

        S_smoothed[t] = alpha * S_total[t] + (1-alpha) * S_smoothed[t-1]

        Note (BUG-006 fix): Raw scores are stored separately from smoothed scores.
        This prevents "double-smoothing" when computing rate of change (ROC).
        The ROC is calculated from smoothed scores, but raw scores are preserved
        for potential future analysis and debugging.

        Args:
            current_score: Current sentiment score
            symbol: Stock symbol
            timestamp: Current timestamp

        Returns:
            Smoothed sentiment score
        """
        if timestamp is None:
            timestamp = datetime.now()

        alpha = self.config.ema_alpha

        # BUG-016: Use lock for thread-safe access to historical scores
        with self._lock:
            # Initialize historical data if needed
            if symbol not in self._historical_scores:
                # First observation: both raw and smoothed are the same
                self._historical_raw_scores[symbol] = [current_score]
                self._historical_scores[symbol] = [current_score]
                self._historical_timestamps[symbol] = [timestamp]
                return current_score

            # Get previous smoothed value for EMA calculation
            prev_smoothed = self._historical_scores[symbol][-1]

            # Calculate smoothed value using EMA formula
            smoothed = alpha * current_score + (1 - alpha) * prev_smoothed

            # Store RAW score separately (BUG-006 fix: prevents double-smoothed ROC)
            self._historical_raw_scores[symbol].append(current_score)
            # Store smoothed value for historical tracking and ROC calculation
            self._historical_scores[symbol].append(smoothed)
            self._historical_timestamps[symbol].append(timestamp)

            # Keep only last 100 data points
            if len(self._historical_scores[symbol]) > 100:
                self._historical_raw_scores[symbol] = self._historical_raw_scores[symbol][-100:]
                self._historical_scores[symbol] = self._historical_scores[symbol][-100:]
                self._historical_timestamps[symbol] = self._historical_timestamps[symbol][-100:]

        return smoothed

    def calculate_roc(self, symbol: str) -> float:
        """
        Calculate rate of change of sentiment.

        S_roc[t] = S_smoothed[t] - S_smoothed[t-1]

        Args:
            symbol: Stock symbol

        Returns:
            Rate of change
        """
        # BUG-016: Use lock for thread-safe access to historical scores
        with self._lock:
            if symbol not in self._historical_scores or len(self._historical_scores[symbol]) < 2:
                return 0.0

            current = self._historical_scores[symbol][-1]
            previous = self._historical_scores[symbol][-2]

        return current - previous

    def interpret_score(self, score: float) -> str:
        """
        Interpret sentiment score.

        Args:
            score: Sentiment score [-5, 5]

        Returns:
            Human-readable interpretation
        """
        if score <= self.config.extreme_bearish:
            return "extreme_bearish"
        elif score <= self.config.bearish:
            return "bearish"
        elif score >= self.config.extreme_bullish:
            return "extreme_bullish"
        elif score >= self.config.bullish:
            return "bullish"
        else:
            return "neutral"

    def calculate_sentiment(
        self, symbol: str, sources: list[SentimentSource], timestamp: datetime | None = None
    ) -> SentimentResult:
        """
        Calculate complete sentiment analysis from multiple sources.

        Args:
            symbol: Stock symbol
            sources: List of SentimentSource objects
            timestamp: Analysis timestamp

        Returns:
            SentimentResult with full analysis
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Define weights
        weights = {
            "news": self.config.news_weight,
            "social": self.config.social_weight,
            "search": self.config.search_weight,
            "forum": self.config.forum_weight,
        }

        # Extract normalized sentiments by source
        source_sentiments = {}
        source_scores = {}
        confidences = {}

        for source in sources:
            source_sentiments[source.source] = source.normalized
            source_scores[source.source] = source.normalized * weights.get(source.source, 0.0) * 5
            confidences[source.source] = source.confidence

        # Calculate total score
        total_score = self.calculate_total_score(source_sentiments, weights)

        # Smooth score
        smoothed_score = self.smooth_score(total_score, symbol, timestamp)

        # Calculate rate of change
        roc = self.calculate_roc(symbol)

        # Interpret
        interpretation = self.interpret_score(smoothed_score)

        # Generate signals
        signals = {
            "rapid_deterioration": roc < -self.config.roc_threshold,
            "rapid_improvement": roc > self.config.roc_threshold,
            "extreme_bearish": smoothed_score <= self.config.extreme_bearish,
            "extreme_bullish": smoothed_score >= self.config.extreme_bullish,
            "bearish": self.config.extreme_bearish < smoothed_score <= self.config.bearish,
            "bullish": self.config.bullish <= smoothed_score < self.config.extreme_bullish,
            "neutral": self.config.bearish < smoothed_score < self.config.bullish,
        }

        return SentimentResult(
            symbol=symbol,
            timestamp=timestamp,
            total_score=total_score,
            smoothed_score=smoothed_score,
            roc=roc,
            interpretation=interpretation,
            source_scores=source_scores,
            confidences=confidences,
            signals=signals,
        )

    def get_historical_scores(
        self, symbol: str, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> pd.DataFrame:
        """
        Get historical sentiment scores for a symbol.

        Args:
            symbol: Stock symbol
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            DataFrame with columns [timestamp, score]
        """
        # BUG-016: Use lock for thread-safe access to historical scores
        with self._lock:
            if symbol not in self._historical_scores:
                return pd.DataFrame(columns=["timestamp", "score"])

            timestamps = self._historical_timestamps[symbol]
            scores = self._historical_scores[symbol]

            df = pd.DataFrame({"timestamp": timestamps, "score": scores})

        if start_date:
            df = df[df["timestamp"] >= start_date]
        if end_date:
            df = df[df["timestamp"] <= end_date]

        return df.reset_index(drop=True)

    # BUG-019: Minimum std dev threshold for z-score calculation
    # When std dev is very small, z-scores become unreliable and can produce
    # extremely large values. We use a minimum threshold to handle this case.
    MIN_STD_FOR_ZSCORE: float = 0.01

    def calculate_sentiment_stats(self, symbol: str, window: int = 30) -> dict[str, float]:
        """
        Calculate statistics for sentiment over a time window.

        Args:
            symbol: Stock symbol
            window: Number of data points to include

        Returns:
            Dict with stats (mean, std, min, max, etc.)
        """
        # BUG-016: Use lock for thread-safe access to historical scores
        with self._lock:
            if symbol not in self._historical_scores:
                return {}

            scores = self._historical_scores[symbol][-window:]

            if len(scores) == 0:
                return {}

        # Calculate z-score with proper handling for near-zero std dev (BUG-019 fix)
        z_score = 0.0
        if len(scores) > 1:
            mean_excl_current = np.mean(scores[:-1])
            std_excl_current = np.std(scores[:-1])

            # BUG-019 fix: Handle near-zero std dev properly
            # When std dev is below threshold, the z-score is unreliable.
            # We return 0.0 z-score to indicate "normal" (not extreme) sentiment.
            if std_excl_current < self.MIN_STD_FOR_ZSCORE:
                # Log warning about low variance
                logger.warning(
                    "Low variance in sentiment scores for %s: std=%.6f < %.6f. "
                    "Z-score set to 0.0 (neutral).",
                    symbol,
                    std_excl_current,
                    self.MIN_STD_FOR_ZSCORE,
                )
                z_score = 0.0
            else:
                z_score = (scores[-1] - mean_excl_current) / std_excl_current

        return {
            "mean": np.mean(scores),
            "std": np.std(scores),
            "min": np.min(scores),
            "max": np.max(scores),
            "current": scores[-1],
            "z_score": z_score,
        }

    def is_sentiment_extreme(self, symbol: str, threshold_std: float = 1.5) -> tuple[bool, float]:
        """
        Check if current sentiment is extreme (deviation from mean).

        BUG-005 fix: This method now handles the "cold start" problem where
        there isn't enough historical data for reliable z-score calculation.

        Fallback behavior:
        - If fewer than min_observations_for_stats observations: Use absolute threshold
          on the raw sentiment score instead of z-score.
        - Log a warning when using fallback mode.

        Args:
            symbol: Stock symbol
            threshold_std: Threshold in standard deviations (for normal mode)
                           or absolute threshold (for fallback mode)

        Returns:
            Tuple of (is_extreme, z_score_or_fallback_value)
            - In normal mode: z_score is the actual z-score
            - In fallback mode: z_score is the absolute value of the raw score
        """
        # BUG-016: Use lock for thread-safe access to historical scores
        with self._lock:
            # Check if we have any historical data at all
            if symbol not in self._historical_scores:
                logger.warning(
                    "No historical data for %s, cannot determine if sentiment is extreme",
                    symbol,
                )
                return False, 0.0

            scores = self._historical_scores[symbol]
            num_observations = len(scores)

            # BUG-005 fix: Cold start fallback
            # If we don't have enough observations for reliable statistics,
            # use a simpler threshold-based check on the raw sentiment score.
            if num_observations < self.config.min_observations_for_stats:
                logger.warning(
                    "Cold start fallback for %s: only %d observations (need %d). "
                    "Using absolute threshold %.2f on raw score.",
                    symbol,
                    num_observations,
                    self.config.min_observations_for_stats,
                    self.config.fallback_threshold_abs,
                )
                # Use the current (smoothed) score with absolute threshold
                current_score = scores[-1]
                is_extreme = abs(current_score) >= self.config.fallback_threshold_abs
                # Return the absolute score value as the "z-score" for consistency
                return is_extreme, abs(current_score)

        # Normal mode: use z-score calculation
        stats = self.calculate_sentiment_stats(symbol, window=30)

        if not stats:
            return False, 0.0

        z_score = abs(stats["z_score"])
        is_extreme = z_score >= threshold_std

        return is_extreme, z_score


class SentimentDataParser:
    """
    Parser for different sentiment data sources.
    """

    @staticmethod
    def parse_news_sentiment(
        articles: list[dict], sentiment_field: str = "sentiment"
    ) -> list[SentimentSource]:
        """
        Parse news article sentiment.

        Args:
            articles: List of article dicts with sentiment field
            sentiment_field: Field name for sentiment score

        Returns:
            List of SentimentSource objects
        """
        sources = []

        for article in articles:
            raw_sentiment = article.get(sentiment_field, 0.0)
            timestamp = (
                datetime.fromisoformat(article["published_at"])
                if "published_at" in article
                else datetime.now()
            )

            # Normalize from [0, 1] to [-1, 1] if needed
            if 0 <= raw_sentiment <= 1:
                normalized = raw_sentiment * 2 - 1
            else:
                normalized = np.clip(raw_sentiment, -1, 1)

            source = SentimentSource(
                source="news",
                timestamp=timestamp,
                raw_sentiment=raw_sentiment,
                normalized=normalized,
                confidence=article.get("confidence", 0.7),
                metadata={"article_id": article.get("id")},
            )
            sources.append(source)

        return sources

    @staticmethod
    def parse_social_media_sentiment(posts: list[dict]) -> list[SentimentSource]:
        """
        Parse social media (Weibo, Dongfang Caifu Guba) sentiment.

        Args:
            posts: List of post dicts

        Returns:
            List of SentimentSource objects
        """
        sources = []

        for post in posts:
            raw_sentiment = post.get("sentiment", 0.0)
            timestamp = (
                datetime.fromisoformat(post["created_at"])
                if "created_at" in post
                else datetime.now()
            )

            # Normalize
            normalized = np.clip(raw_sentiment, -1, 1)

            source = SentimentSource(
                source="social",
                timestamp=timestamp,
                raw_sentiment=raw_sentiment,
                normalized=normalized,
                confidence=post.get("confidence", 0.6),
                metadata={"platform": post.get("platform", "unknown"), "post_id": post.get("id")},
            )
            sources.append(source)

        return sources

    @staticmethod
    def parse_search_volume(
        search_data: list[dict], baseline_period: str = "30d"
    ) -> list[SentimentSource]:
        """
        Parse search volume data (Baidu trends).

        Search volume indicates interest, not necessarily sentiment.
        We interpret:
        - High search + declining price = panic (negative)
        - High search + rising price = hype (positive)

        Args:
            search_data: List of search volume data
            baseline_period: Baseline period for comparison

        Returns:
            List of SentimentSource objects
        """
        sources = []

        if not search_data:
            return sources

        # Calculate baseline
        volumes = [d["volume"] for d in search_data]
        baseline = np.mean(volumes)

        for data in search_data:
            volume = data["volume"]
            price_change = data.get("price_change", 0.0)  # Daily price change

            # Normalize volume: volume_ratio > 1 = higher than baseline
            volume_ratio = volume / (baseline + 1e-8)

            # Sentiment from search volume interpretation
            if volume_ratio > 1.5:
                # High search volume
                if price_change < -0.02:
                    # Panic selling
                    sentiment = -0.7
                elif price_change > 0.02:
                    # FOMO buying
                    sentiment = 0.7
                else:
                    # High interest but neutral price action
                    sentiment = 0.3
            else:
                # Normal or low search volume
                sentiment = 0.0

            timestamp = datetime.fromisoformat(data["date"]) if "date" in data else datetime.now()

            source = SentimentSource(
                source="search",
                timestamp=timestamp,
                raw_sentiment=sentiment,
                normalized=sentiment,
                confidence=0.5,
                metadata={
                    "volume": volume,
                    "volume_ratio": volume_ratio,
                    "price_change": price_change,
                },
            )
            sources.append(source)

        return sources


def load_config(config_path: str) -> SentimentConfig:
    """
    Load sentiment configuration from JSON file.

    The config file has a nested structure with sentiment settings under
    the "sentiment" key. This function parses the nested structure correctly.

    Expected config.json structure:
    {
        "sentiment": {
            "weights": {
                "news": 0.40,
                "social": 0.35,
                "search": 0.15,
                "forum": 0.10
            },
            "ema_alpha": 0.2,
            "roc_threshold": 1.0,
            "min_score": -5.0,
            "max_score": 5.0,
            "extreme_bearish": -3.0,
            "bearish": -1.5,
            "bullish": 1.5,
            "extreme_bullish": 3.0
        }
    }

    Args:
        config_path: Path to config JSON file

    Returns:
        SentimentConfig instance
    """
    with open(config_path) as f:
        config_dict = json.load(f)

    # Parse nested structure
    if "sentiment" in config_dict:
        sentiment_config = config_dict["sentiment"]
    else:
        # Fallback: assume flat structure for backward compatibility
        sentiment_config = config_dict

    # Extract weights from nested structure
    weights = sentiment_config.get("weights", {})

    return SentimentConfig(
        news_weight=weights.get("news", 0.40),
        social_weight=weights.get("social", 0.35),
        search_weight=weights.get("search", 0.15),
        forum_weight=weights.get("forum", 0.10),
        ema_alpha=sentiment_config.get("ema_alpha", 0.2),
        roc_threshold=sentiment_config.get("roc_threshold", 1.0),
        min_score=sentiment_config.get("min_score", -5.0),
        max_score=sentiment_config.get("max_score", 5.0),
        extreme_bearish=sentiment_config.get("extreme_bearish", -3.0),
        bearish=sentiment_config.get("bearish", -1.5),
        bullish=sentiment_config.get("bullish", 1.5),
        extreme_bullish=sentiment_config.get("extreme_bullish", 3.0),
        min_observations_for_stats=sentiment_config.get("min_observations_for_stats", 10),
        fallback_threshold_abs=sentiment_config.get("fallback_threshold_abs", 2.0),
    )


# Example usage and testing
if __name__ == "__main__":
    # Test with example data
    analyzer = SentimentAnalyzer()

    # Example sentiment sources for a stock
    sources = [
        SentimentSource(
            source="news",
            timestamp=datetime.now(),
            raw_sentiment=-0.3,  # Bearish news
            normalized=-0.3,
            confidence=0.8,
            metadata={"article_count": 5},
        ),
        SentimentSource(
            source="social",
            timestamp=datetime.now(),
            raw_sentiment=-0.5,  # Very bearish social media
            normalized=-0.5,
            confidence=0.7,
            metadata={"platform": "weibo", "post_count": 100},
        ),
        SentimentSource(
            source="search",
            timestamp=datetime.now(),
            raw_sentiment=-0.7,  # Panic selling
            normalized=-0.7,
            confidence=0.6,
            metadata={"volume_ratio": 2.0, "price_change": -0.05},
        ),
        SentimentSource(
            source="forum",
            timestamp=datetime.now(),
            raw_sentiment=-0.4,
            normalized=-0.4,
            confidence=0.5,
            metadata={"post_count": 50},
        ),
    ]

    result = analyzer.calculate_sentiment("600519.SH", sources)

    print("=== Sentiment Analysis ===")
    print(f"Symbol: {result.symbol}")
    print(f"Timestamp: {result.timestamp}")
    print("\nScores:")
    print(f"  Total Score: {result.total_score:.2f}")
    print(f"  Smoothed Score: {result.smoothed_score:.2f}")
    print(f"  Rate of Change: {result.roc:.2f}")
    print(f"\nInterpretation: {result.interpretation}")
    print("\nSource Scores:")
    for source, score in result.source_scores.items():
        print(f"  {source}: {score:.2f}")
    print("\nConfidences:")
    for source, conf in result.confidences.items():
        print(f"  {source}: {conf:.2f}")
    print("\nSignals:")
    for signal, value in result.signals.items():
        if value:
            print(f"  [OK] {signal}")
