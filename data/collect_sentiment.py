#!/usr/bin/env python3
"""
Production-ready sentiment data collection for Chinese stocks.
Collects sentiment data from multiple sources:
1. News articles (Eastmoney, Sina)
2. AKShare market data (hot rank, fund flow, northbound capital, etc.)

Usage:
    python collect_sentiment.py --source eastmoney --days 7
    python collect_sentiment.py --source sina --days 7
    python collect_sentiment.py --source akshare --symbols 600519,000001
    python collect_sentiment.py --source all --days 7
"""

import hashlib
import json
import logging
import random
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Configure logging - use relative path that works on both systems
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "sentiment_collection.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Try to import akshare
try:
    import akshare as ak

    AKSHARE_AVAILABLE = True
except ImportError:
    ak = None
    AKSHARE_AVAILABLE = False
    logger.warning("akshare not installed. AKShare sentiment sources will be unavailable.")


# ============================================================================
# Exceptions
# ============================================================================


class SentimentCollectionError(Exception):
    """Base exception for sentiment collection errors"""

    pass


class RateLimitError(SentimentCollectionError):
    """Rate limit hit on API"""

    pass


class DataQualityError(SentimentCollectionError):
    """Data quality issue detected"""

    pass


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class NewsArticle:
    """Represents a news article"""

    title: str
    url: str
    publish_time: datetime
    content: str | None = None
    source: str = ""
    stock_symbols: list[str] = field(default_factory=list)

    def __repr__(self):
        return f"NewsArticle(title={self.title[:50]}, url={self.url[:50]})"

    def to_dict(self):
        return {
            "title": self.title,
            "url": self.url,
            "publish_time": self.publish_time.isoformat(),
            "content": self.content,
            "source": self.source,
            "stock_symbols": ",".join(self.stock_symbols),
        }


@dataclass
class SentimentDataPoint:
    """Single sentiment data point from AKShare"""

    source: str  # Source identifier
    symbol: str  # Stock symbol
    timestamp: datetime  # When data was fetched
    raw_value: float  # Raw value from API
    normalized: float  # Normalized to [-1, 1]
    confidence: float  # Confidence in this data point [0, 1]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "raw_value": self.raw_value,
            "normalized": self.normalized,
            "confidence": self.confidence,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
        }


# ============================================================================
# AKShare Sentiment Configuration
# ============================================================================


@dataclass
class AKShareSentimentConfig:
    """Configuration for AKShare sentiment data fetching"""

    # Source weights (should sum to 1.0)
    hot_rank_weight: float = 0.15
    comment_weight: float = 0.20
    fund_flow_weight: float = 0.25
    northbound_weight: float = 0.15
    long_hub_weight: float = 0.10
    margin_weight: float = 0.10
    market_activity_weight: float = 0.05

    # Normalization parameters
    hot_rank_top_n: int = 100
    fund_flow_window: int = 5
    northbound_window: int = 5

    # Sentiment thresholds
    extreme_hot_rank: int = 10
    cold_rank_threshold: int = 90

    # Cache settings
    cache_ttl_seconds: int = 300

    # Rate limiting (to avoid triggering anti-bot protection)
    request_delay_seconds: float = 0.3  # Delay between API calls
    max_retries: int = 3  # Max retries on connection errors
    retry_delay_seconds: float = 1.0  # Base delay for retries


# ============================================================================
# AKShare Sentiment Fetcher
# ============================================================================


class AKShareSentimentFetcher:
    """
    Fetches sentiment data from AKShare APIs and normalizes them.

    Data Sources:
    1. Stock Hot Rank (股票热度) - East Money hot rank
    2. 千股千评 (Stock Comments) - Institution participation, comprehensive score
    3. Fund Flow (资金流向) - Main force net inflow
    4. Northbound Capital (北向资金) - Foreign capital holdings change
    5. Long Hub (龙虎榜) - Institution trading activity
    6. Margin Trading (融资融券) - Leverage sentiment
    7. Market Activity (赚钱效应) - Overall market sentiment
    """

    def __init__(self, config: AKShareSentimentConfig | None = None):
        if not AKSHARE_AVAILABLE:
            raise ImportError(
                "akshare is required for AKShareSentimentFetcher. "
                "Install with: uv pip install akshare"
            )
        self.config = config or AKShareSentimentConfig()
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._lock = threading.Lock()
        self.logger = logger

        # Rate limiting state
        self._last_request_time: float = 0.0
        self._request_count: int = 0

    def _get_cached(self, key: str) -> Any | None:
        """Get cached data if still valid."""
        with self._lock:
            if key in self._cache:
                timestamp, data = self._cache[key]
                age = (datetime.now() - timestamp).total_seconds()
                if age < self.config.cache_ttl_seconds:
                    return data
        return None

    def _set_cache(self, key: str, data: Any) -> None:
        """Cache data with current timestamp."""
        with self._lock:
            self._cache[key] = (datetime.now(), data)

    def _rate_limit(self) -> None:
        """Enforce minimum delay between API requests to avoid rate limiting."""
        import time

        with self._lock:
            elapsed = time.time() - self._last_request_time
            delay = self.config.request_delay_seconds
            if elapsed < delay:
                time.sleep(delay - elapsed)
            self._last_request_time = time.time()
            self._request_count += 1

    def _retry_with_backoff(self, func: callable, *args, **kwargs) -> Any:
        """
        Execute function with exponential backoff retry for connection errors.

        Args:
            func: Function to execute
            *args, **kwargs: Arguments to pass to function

        Returns:
            Function result

        Raises:
            Exception: After max retries exceeded
        """
        import time

        max_retries = self.config.max_retries
        base_delay = self.config.retry_delay_seconds

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                # Check if it's a connection/proxy error
                is_connection_error = any(
                    keyword in error_msg
                    for keyword in [
                        "proxy",
                        "connection",
                        "remotedisconnected",
                        "max retries exceeded",
                        "timeout",
                    ]
                )

                if not is_connection_error or attempt == max_retries - 1:
                    raise

                # Exponential backoff with jitter
                delay = base_delay * (2**attempt) + (hash(str(args)) % 10) / 10
                self.logger.warning(
                    "Request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    max_retries,
                    delay,
                    e,
                )
                time.sleep(delay)

        return None  # Should never reach here

    # ==================== Hot Rank Data ====================

    def get_hot_rank_data(self) -> pd.DataFrame | None:
        """Fetch stock hot rank data from East Money."""
        cache_key = "hot_rank_em"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.stock_hot_rank_em()
            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self.logger.error("Failed to fetch hot rank data: %s", e)
            return None

    def get_hot_rank_sentiment(self, symbol: str) -> SentimentDataPoint | None:
        """Get sentiment based on stock hot rank."""
        code = symbol.replace("SH", "").replace("SZ", "").replace("BJ", "")

        df = self.get_hot_rank_data()
        if df is None or df.empty:
            return None

        rank_row = df[df["代码"] == code]
        if rank_row.empty:
            return SentimentDataPoint(
                source="hot_rank",
                symbol=symbol,
                timestamp=datetime.now(),
                raw_value=100.0,
                normalized=-0.3,
                confidence=0.5,
                metadata={"rank": None, "in_top_100": False},
            )

        rank = int(rank_row["当前排名"].values[0])
        price_change = float(rank_row["涨跌幅"].values[0])

        # Normalize rank to sentiment
        if rank <= self.config.extreme_hot_rank:
            normalized = 0.7 + 0.3 * (1 - rank / self.config.extreme_hot_rank)
        elif rank <= 50:
            normalized = 0.3 + 0.4 * (1 - (rank - 10) / 40)
        else:
            normalized = 0.3 * (1 - (rank - 50) / 50)

        # Adjust based on price change
        if price_change < -3.0:
            normalized *= -0.5
        elif price_change < 0:
            normalized *= 0.7

        normalized = float(np.clip(normalized, -1.0, 1.0))

        return SentimentDataPoint(
            source="hot_rank",
            symbol=symbol,
            timestamp=datetime.now(),
            raw_value=rank,
            normalized=normalized,
            confidence=0.7,
            metadata={
                "rank": rank,
                "price_change_pct": price_change,
                "in_top_100": True,
            },
        )

    # ==================== 千股千评 Data ====================

    def get_stock_comment_data(self) -> pd.DataFrame | None:
        """Fetch 千股千评 data from East Money."""
        cache_key = "stock_comment_em"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.stock_comment_em()
            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self.logger.error("Failed to fetch stock comment data: %s", e)
            return None

    def get_stock_comment_sentiment(self, symbol: str) -> SentimentDataPoint | None:
        """Get sentiment from 千股千评 data."""
        code = symbol.replace("SH", "").replace("SZ", "").replace("BJ", "")

        df = self.get_stock_comment_data()
        if df is None or df.empty:
            return None

        row = df[df["代码"] == code]
        if row.empty:
            return None

        comprehensive_score = float(row["综合得分"].values[0])
        institution_participation = float(row["机构参与度"].values[0])
        attention_index = float(row["关注指数"].values[0])

        # Normalize comprehensive score (typically 0-100)
        score_normalized = (comprehensive_score - 50) / 25
        score_normalized = float(np.clip(score_normalized, -1.0, 1.0))

        # Institution participation factor
        inst_factor = (institution_participation - 15) / 15
        inst_factor = float(np.clip(inst_factor, -0.3, 0.3))

        combined = score_normalized + inst_factor
        combined = float(np.clip(combined, -1.0, 1.0))

        confidence = min(attention_index / 100, 1.0) * 0.8

        return SentimentDataPoint(
            source="stock_comment",
            symbol=symbol,
            timestamp=datetime.now(),
            raw_value=comprehensive_score,
            normalized=combined,
            confidence=confidence,
            metadata={
                "comprehensive_score": comprehensive_score,
                "institution_participation": institution_participation,
                "attention_index": attention_index,
            },
        )

    # ==================== Fund Flow Data ====================

    def get_fund_flow_data(self, symbol: str, market: str = "auto") -> pd.DataFrame | None:
        """Fetch individual stock fund flow data with rate limiting and retries."""
        code = symbol.replace("SH", "").replace("SZ", "").replace("BJ", "")

        if market == "auto":
            if symbol.startswith("6") or symbol.startswith("SH"):
                market = "sh"
            elif symbol.startswith("0") or symbol.startswith("3") or symbol.startswith("SZ"):
                market = "sz"
            elif symbol.startswith("4") or symbol.startswith("8") or symbol.startswith("BJ"):
                market = "bj"
            else:
                market = "sz"

        cache_key = f"fund_flow_{code}_{market}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            df = self._retry_with_backoff(ak.stock_individual_fund_flow, stock=code, market=market)
            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self.logger.debug("Failed to fetch fund flow data for %s: %s", symbol, e)
            return None

    def get_fund_flow_sentiment(self, symbol: str) -> SentimentDataPoint | None:
        """Get sentiment from fund flow data."""
        df = self.get_fund_flow_data(symbol)
        if df is None or df.empty:
            return None

        window = min(self.config.fund_flow_window, len(df))
        recent = df.tail(window)

        main_inflow = recent["主力净流入-净额"].values
        main_inflow_pct = recent["主力净流入-净占比"].values
        super_large_inflow = recent["超大单净流入-净额"].values

        total_main_inflow = float(np.sum(main_inflow))
        avg_main_inflow_pct = float(np.mean(main_inflow_pct))

        if abs(avg_main_inflow_pct) < 1.0:
            normalized = avg_main_inflow_pct / 5.0
        else:
            normalized = float(
                np.sign(avg_main_inflow_pct) * min(abs(avg_main_inflow_pct) / 10.0, 1.0)
            )

        if len(main_inflow) >= 3:
            recent_trend = float(np.mean(main_inflow[-2:]) - np.mean(main_inflow[:-2]))
            if recent_trend > 0:
                normalized += 0.2
            elif recent_trend < 0:
                normalized -= 0.2

        normalized = float(np.clip(normalized, -1.0, 1.0))

        consistency = 1.0 - float(np.std(main_inflow_pct)) / (abs(np.mean(main_inflow_pct)) + 1.0)
        confidence = max(0.4, min(0.9, consistency))

        return SentimentDataPoint(
            source="fund_flow",
            symbol=symbol,
            timestamp=datetime.now(),
            raw_value=total_main_inflow,
            normalized=normalized,
            confidence=confidence,
            metadata={
                "total_main_inflow": total_main_inflow,
                "avg_main_inflow_pct": avg_main_inflow_pct,
                "super_large_inflow": float(np.sum(super_large_inflow)),
            },
        )

    # ==================== Northbound Capital Data ====================

    def get_northbound_data(self, symbol: str) -> pd.DataFrame | None:
        """Fetch northbound capital holdings data for a stock with rate limiting."""
        code = symbol.replace("SH", "").replace("SZ", "").replace("BJ", "")

        cache_key = f"northbound_{code}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            df = self._retry_with_backoff(ak.stock_hsgt_individual_em, symbol=code)
            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self.logger.debug("Failed to fetch northbound data for %s: %s", symbol, e)
            return None

    def get_northbound_sentiment(self, symbol: str) -> SentimentDataPoint | None:
        """Get sentiment from northbound capital holdings change."""
        df = self.get_northbound_data(symbol)
        if df is None or df.empty:
            return None

        window = min(self.config.northbound_window, len(df))
        recent = df.tail(window)

        holdings_change = recent["今日增持股数"].values
        holdings_pct = recent["持股数量占A股百分比"].values

        total_change = float(np.sum(holdings_change))
        holdings_change_rate = 0.0
        if len(holdings_pct) >= 2:
            holdings_change_rate = float(holdings_pct[-1] - holdings_pct[0])

        if abs(holdings_change_rate) < 0.01:
            normalized = 0.0
        else:
            normalized = float(
                np.sign(holdings_change_rate) * min(abs(holdings_change_rate) * 10, 1.0)
            )

        if len(holdings_change) >= 3:
            recent_changes = holdings_change[-2:]
            earlier_changes = holdings_change[:-2]
            if np.mean(recent_changes) > np.mean(earlier_changes):
                normalized += 0.15
            elif np.mean(recent_changes) < np.mean(earlier_changes):
                normalized -= 0.15

        normalized = float(np.clip(normalized, -1.0, 1.0))

        avg_holdings_pct = float(np.mean(holdings_pct))
        confidence = min(0.5 + avg_holdings_pct * 10, 0.9)

        return SentimentDataPoint(
            source="northbound",
            symbol=symbol,
            timestamp=datetime.now(),
            raw_value=total_change,
            normalized=normalized,
            confidence=confidence,
            metadata={
                "total_holdings_change": total_change,
                "holdings_change_rate": holdings_change_rate,
                "avg_holdings_pct": avg_holdings_pct,
            },
        )

    # ==================== Long Hub Data ====================

    def get_long_hub_stock_stats(self, period: str = "近一月") -> pd.DataFrame | None:
        """Fetch Long Hub statistics with rate limiting."""
        cache_key = f"long_hub_stats_{period}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            df = self._retry_with_backoff(ak.stock_lhb_stock_statistic_em, symbol=period)
            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self.logger.debug("Failed to fetch Long Hub data: %s", e)
            return None

    def get_long_hub_sentiment(self, symbol: str) -> SentimentDataPoint | None:
        """Get sentiment from Long Hub activity."""
        code = symbol.replace("SH", "").replace("SZ", "").replace("BJ", "")

        df = self.get_long_hub_stock_stats(period="近一月")
        if df is None or df.empty:
            return None

        row = df[df["代码"] == code]
        if row.empty:
            return SentimentDataPoint(
                source="long_hub",
                symbol=symbol,
                timestamp=datetime.now(),
                raw_value=0,
                normalized=0.0,
                confidence=0.3,
                metadata={"on_list": False},
            )

        inst_buy_count = int(row["买方机构次数"].values[0])
        inst_sell_count = int(row["卖方机构次数"].values[0])
        inst_net_buy = float(row["机构买入净额"].values[0])
        list_count = int(row["上榜次数"].values[0])

        if inst_buy_count + inst_sell_count == 0:
            normalized = 0.0
        else:
            buy_ratio = (inst_buy_count - inst_sell_count) / (inst_buy_count + inst_sell_count)
            normalized = buy_ratio * 0.8

        if abs(inst_net_buy) > 1e8:
            normalized += float(np.sign(inst_net_buy)) * 0.2

        normalized = float(np.clip(normalized, -1.0, 1.0))
        confidence = min(0.4 + list_count * 0.05, 0.85)

        return SentimentDataPoint(
            source="long_hub",
            symbol=symbol,
            timestamp=datetime.now(),
            raw_value=inst_net_buy,
            normalized=normalized,
            confidence=confidence,
            metadata={
                "inst_buy_count": inst_buy_count,
                "inst_sell_count": inst_sell_count,
                "inst_net_buy": inst_net_buy,
                "list_count": list_count,
                "on_list": True,
            },
        )

    # ==================== Margin Trading Data ====================

    def get_margin_account_data(self) -> pd.DataFrame | None:
        """Fetch margin trading account statistics."""
        cache_key = "margin_account"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.stock_margin_account_info()
            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self.logger.error("Failed to fetch margin account data: %s", e)
            return None

    def get_margin_sentiment(self) -> SentimentDataPoint | None:
        """Get overall market sentiment from margin trading data."""
        df = self.get_margin_account_data()
        if df is None or df.empty:
            return None

        recent = df.tail(10)
        margin_balance = recent["融资余额"].values
        margin_buy = recent["融资买入额"].values

        if len(margin_balance) >= 5:
            balance_change = float(margin_balance[-1] - margin_balance[-5])
            balance_change_pct = balance_change / margin_balance[-5]

            if abs(balance_change_pct) < 0.01:
                normalized = 0.0
            else:
                normalized = float(
                    np.sign(balance_change_pct) * min(abs(balance_change_pct) * 20, 1.0)
                )

            avg_buy = float(np.mean(margin_buy))
            confidence = min(0.5 + avg_buy / 5000, 0.8)
        else:
            normalized = 0.0
            confidence = 0.3

        return SentimentDataPoint(
            source="margin",
            symbol="MARKET",
            timestamp=datetime.now(),
            raw_value=float(margin_balance[-1]) if len(margin_balance) > 0 else 0,
            normalized=normalized,
            confidence=confidence,
            metadata={
                "margin_balance": float(margin_balance[-1]) if len(margin_balance) > 0 else 0,
            },
        )

    # ==================== Market Activity Data ====================

    def get_market_activity_data(self) -> pd.DataFrame | None:
        """Fetch market activity data."""
        cache_key = "market_activity"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.stock_market_activity_legu()
            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self.logger.error("Failed to fetch market activity data: %s", e)
            return None

    def get_market_activity_sentiment(self) -> SentimentDataPoint | None:
        """Get overall market sentiment from market activity data."""
        df = self.get_market_activity_data()
        if df is None or df.empty:
            return None

        data_dict = dict(zip(df["item"], df["value"], strict=False))

        up_count = float(data_dict.get("上涨", 0))
        down_count = float(data_dict.get("下跌", 1))
        real_limit_up = float(data_dict.get("真实涨停", 0))
        real_limit_down = float(data_dict.get("真实跌停", 0))
        activity_rate = data_dict.get("活跃度", "50%")

        if isinstance(activity_rate, str):
            activity_rate = float(activity_rate.replace("%", "")) / 100
        else:
            activity_rate = float(activity_rate)

        total = up_count + down_count
        up_ratio = up_count / total if total > 0 else 0.5

        total_limit = real_limit_up + real_limit_down
        limit_ratio = (real_limit_up - real_limit_down) / total_limit if total_limit > 0 else 0.0

        normalized = (up_ratio - 0.5) * 1.5 + limit_ratio * 0.5
        normalized = float(np.clip(normalized, -1.0, 1.0))

        confidence = min(0.4 + activity_rate * 0.5, 0.9)

        return SentimentDataPoint(
            source="market_activity",
            symbol="MARKET",
            timestamp=datetime.now(),
            raw_value=activity_rate,
            normalized=normalized,
            confidence=confidence,
            metadata={
                "up_count": up_count,
                "down_count": down_count,
                "real_limit_up": real_limit_up,
                "real_limit_down": real_limit_down,
                "activity_rate": activity_rate,
            },
        )

    # ==================== Composite Sentiment ====================

    def get_composite_sentiment(
        self, symbol: str, include_market: bool = True, lightweight: bool = False
    ) -> tuple[float, dict[str, SentimentDataPoint]]:
        """
        Calculate composite sentiment for a stock from all sources.

        Args:
            symbol: Stock symbol
            include_market: Include market-wide sentiment sources
            lightweight: If True, skip per-stock API calls (fund_flow, northbound)
                        Useful for large batches to avoid rate limiting
        """
        data_points: dict[str, SentimentDataPoint] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        # Batched sources (efficient - single API call for all stocks)
        sources = [
            ("hot_rank", self.get_hot_rank_sentiment, self.config.hot_rank_weight),
            ("stock_comment", self.get_stock_comment_sentiment, self.config.comment_weight),
            ("long_hub", self.get_long_hub_sentiment, self.config.long_hub_weight),
        ]

        # Per-stock sources (expensive - one API call per stock)
        if not lightweight:
            sources.extend(
                [
                    ("fund_flow", self.get_fund_flow_sentiment, self.config.fund_flow_weight),
                    ("northbound", self.get_northbound_sentiment, self.config.northbound_weight),
                ]
            )

        for source_name, fetcher, weight in sources:
            try:
                dp = fetcher(symbol)
                if dp is not None:
                    data_points[source_name] = dp
                    weighted_sum += dp.normalized * weight * dp.confidence
                    total_weight += weight * dp.confidence
            except Exception as e:
                self.logger.warning("Failed to get %s sentiment for %s: %s", source_name, symbol, e)

        if include_market:
            market_sources = [
                ("margin", self.get_margin_sentiment, self.config.margin_weight),
                (
                    "market_activity",
                    self.get_market_activity_sentiment,
                    self.config.market_activity_weight,
                ),
            ]

            for source_name, fetcher, weight in market_sources:
                try:
                    dp = fetcher()
                    if dp is not None:
                        data_points[source_name] = dp
                        weighted_sum += dp.normalized * weight * dp.confidence
                        total_weight += weight * dp.confidence
                except Exception as e:
                    self.logger.warning("Failed to get %s sentiment: %s", source_name, e)

        composite = weighted_sum / total_weight if total_weight > 0 else 0.0

        return composite, data_points


# ============================================================================
# Main Sentiment Collector (Preserving Original Interface)
# ============================================================================


class SentimentCollector:
    """
    Robust sentiment data collector with multiple source support.
    Supports both news article collection and AKShare market sentiment.
    """

    def __init__(self, config_path: str | None = None):
        # Set logger first to avoid AttributeError during config loading
        self.logger = logger

        # Default to relative path from repo root
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.json")

        self.config = self._load_config(config_path)
        self.db_path = self.config["database"]["path"]

        # HTTP session for requests
        self.session = None
        self._init_session()

        # Rate limiting
        self.request_count = 0
        self.last_request_time = 0
        self.min_request_interval = 0.5
        self.random_delay_range = (0.5, 2.0)

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2.0
        self.retry_backoff = 2.0

        # Data quality filters
        self.min_title_length = 10
        self.min_content_length = 50
        self.max_content_length = 100000
        self.spam_keywords = [
            "广告",
            "推广",
            "AD",
            "赞助",
            "sponsored",
            "advertising",
            "点击",
            "下载",
            "安装",
            "立即购买",
            "免费领取",
        ]

        # Track processed URLs
        self.processed_urls: set[str] = set()

        # AKShare fetcher (lazy initialization)
        self._akshare_fetcher: AKShareSentimentFetcher | None = None

    @property
    def akshare_fetcher(self) -> AKShareSentimentFetcher:
        """Lazy initialization of AKShare fetcher."""
        if self._akshare_fetcher is None:
            if not AKSHARE_AVAILABLE:
                raise SentimentCollectionError("akshare not installed")
            self._akshare_fetcher = AKShareSentimentFetcher()
        return self._akshare_fetcher

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise SentimentCollectionError(f"Config load failed: {e}") from e

    def _init_session(self):
        """Initialize HTTP session with headers"""
        try:
            import requests

            self.session = requests.Session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            self.session.headers.update(headers)
            self.logger.info("HTTP session initialized")
        except ImportError:
            raise SentimentCollectionError("requests library not installed") from None

    def _rate_limit(self):
        """Apply rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)

        self.request_count += 1
        if self.request_count % 10 == 0:
            delay = random.uniform(*self.random_delay_range)
            time.sleep(delay)

        self.last_request_time = time.time()

    def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with retry logic and exponential backoff"""
        last_error = None
        delay = self.retry_delay

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.warning(f"Error on attempt {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    delay *= self.retry_backoff
                last_error = e

        raise SentimentCollectionError(f"Failed after {self.max_retries} attempts: {last_error}")

    def _is_spam(self, text: str) -> bool:
        """Check if text contains spam keywords"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.spam_keywords)

    def _validate_article(self, article: NewsArticle) -> bool:
        """Validate article data quality"""
        if not article.title or len(article.title) < self.min_title_length:
            return False
        if self._is_spam(article.title):
            return False
        if article.content and len(article.content) < self.min_content_length:
            return False
        if article.content and len(article.content) > self.max_content_length:
            return False
        return True

    def _extract_stock_symbols(self, text: str) -> list[str]:
        """Extract stock symbols from text."""
        import re

        pattern = r"(\d{6})"
        matches = re.findall(pattern, text)
        symbols = []
        for match in matches:
            if match.startswith("6") or match.startswith("0") or match.startswith("3"):
                if match not in symbols:
                    symbols.append(match)
        return symbols

    def _connect_database(self):
        """Connect to DuckDB database"""
        try:
            import duckdb

            return duckdb.connect(self.db_path)
        except Exception as e:
            raise SentimentCollectionError(f"Database connection failed: {e}") from e

    # ==================== News Collection Methods ====================

    def fetch_eastmoney_news(self, days: int = 7, max_articles: int = 1000) -> list[NewsArticle]:
        """Fetch news from Eastmoney."""
        self.logger.info(f"Fetching news from Eastmoney (last {days} days)...")
        articles = []

        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            page = 1
            page_size = 50

            while len(articles) < max_articles:
                self._rate_limit()

                url = "http://data.eastmoney.com/notices/getdata.ashx"
                params = {
                    "SecurityCode": "000001",
                    "Type": "RZLZ",
                    "PageIndex": page,
                    "PageSize": page_size,
                    "BeginDate": start_date,
                    "EndDate": end_date,
                }

                try:
                    response = self.session.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()

                    if not data or "Data" not in data:
                        break

                    news_list = data["Data"]
                    if not news_list:
                        break

                    for item in news_list:
                        title = item.get("NoticesTitle", "")
                        url = item.get("NoticesUrl", "")
                        publish_time_str = item.get("NoticesTime", "")
                        content = item.get("NoticesContent", "")

                        if not title or not url:
                            continue

                        try:
                            publish_time = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M:%S")
                        except (ValueError, TypeError):
                            publish_time = datetime.now()

                        stock_symbols = self._extract_stock_symbols(title)
                        if content:
                            stock_symbols.extend(self._extract_stock_symbols(content))

                        article = NewsArticle(
                            title=title,
                            url=url,
                            publish_time=publish_time,
                            content=content,
                            source="eastmoney",
                            stock_symbols=stock_symbols,
                        )

                        if self._validate_article(article):
                            articles.append(article)

                    page += 1

                except Exception as e:
                    self.logger.error(f"Error fetching page {page}: {e}")
                    break

            self.logger.info(f"Fetched {len(articles)} valid articles from Eastmoney")
            return articles

        except Exception as e:
            self.logger.error(f"Eastmoney news fetch failed: {e}")
            raise SentimentCollectionError(f"Eastmoney fetch failed: {e}") from e

    def fetch_sina_news(self, days: int = 7, max_articles: int = 1000) -> list[NewsArticle]:
        """Fetch news from Sina Finance."""
        self.logger.info(f"Fetching news from Sina Finance (last {days} days)...")
        articles = []

        try:
            from bs4 import BeautifulSoup

            start_date = datetime.now() - timedelta(days=days)
            page = 1

            while len(articles) < max_articles:
                self._rate_limit()

                url = "http://finance.sina.com.cn/7x24/"
                params = {"page": page}

                try:
                    response = self.session.get(url, params=params, timeout=10)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, "html.parser")
                    news_items = soup.select(".content li")

                    if not news_items:
                        break

                    for item in news_items:
                        title_elem = item.find("a")
                        time_elem = item.find("span")

                        if not title_elem:
                            continue

                        title = title_elem.get_text(strip=True)
                        url = title_elem.get("href", "")

                        time_text = time_elem.get_text(strip=True) if time_elem else ""
                        try:
                            if "小时前" in time_text:
                                hours = int(time_text.replace("小时前", "").strip())
                                publish_time = datetime.now() - timedelta(hours=hours)
                            elif "分钟前" in time_text:
                                minutes = int(time_text.replace("分钟前", "").strip())
                                publish_time = datetime.now() - timedelta(minutes=minutes)
                            else:
                                publish_time = datetime.now()
                        except (ValueError, TypeError):
                            publish_time = datetime.now()

                        if publish_time < start_date:
                            continue

                        stock_symbols = self._extract_stock_symbols(title)

                        article = NewsArticle(
                            title=title,
                            url=url,
                            publish_time=publish_time,
                            content=None,
                            source="sina",
                            stock_symbols=stock_symbols,
                        )

                        if self._validate_article(article):
                            articles.append(article)

                    page += 1

                except Exception as e:
                    self.logger.error(f"Error fetching Sina page {page}: {e}")
                    break

            self.logger.info(f"Fetched {len(articles)} valid articles from Sina Finance")
            return articles

        except ImportError:
            raise SentimentCollectionError("BeautifulSoup4 not installed") from None
        except Exception as e:
            raise SentimentCollectionError(f"Sina Finance fetch failed: {e}") from e

    def save_news_articles(self, conn, articles: list[NewsArticle]) -> int:
        """Save news articles to database."""
        inserted_count = 0

        try:
            conn.execute("BEGIN TRANSACTION")

            for article in articles:
                content_hash = hashlib.md5(f"{article.title}{article.url}".encode()).hexdigest()

                existing = conn.execute(
                    "SELECT 1 FROM news_raw WHERE content_hash = ?",
                    [content_hash],
                ).fetchone()

                if existing:
                    continue

                conn.execute(
                    """
                    INSERT INTO news_raw
                    (title, url, publish_time, content, source, stock_symbols,
                     content_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    [
                        article.title,
                        article.url,
                        article.publish_time,
                        article.content,
                        article.source,
                        ",".join(article.stock_symbols),
                        content_hash,
                    ],
                )
                inserted_count += 1

            conn.execute("COMMIT")
            self.logger.info(f"Saved {inserted_count} new news articles")
            return inserted_count

        except Exception as e:
            conn.execute("ROLLBACK")
            raise SentimentCollectionError(f"Failed to save news articles: {e}") from e

    # ==================== AKShare Sentiment Collection ====================

    def collect_akshare_sentiment(
        self,
        symbols: list[str],
        include_market: bool = True,
    ) -> dict[str, Any]:
        """
        Collect sentiment data from AKShare APIs.

        Args:
            symbols: List of stock symbols to analyze
            include_market: Whether to include market-level indicators

        Returns:
            Dict with sentiment data for each symbol
        """
        if not AKSHARE_AVAILABLE:
            raise SentimentCollectionError("akshare not installed")

        results = {}

        for symbol in symbols:
            try:
                composite, data_points = self.akshare_fetcher.get_composite_sentiment(
                    symbol, include_market=include_market
                )

                results[symbol] = {
                    "composite_sentiment": composite,
                    "sources": {k: v.to_dict() for k, v in data_points.items()},
                    "timestamp": datetime.now().isoformat(),
                }

                self.logger.info(
                    f"Collected AKShare sentiment for {symbol}: composite={composite:.3f}, "
                    f"sources={list(data_points.keys())}"
                )

            except Exception as e:
                self.logger.error(f"Failed to collect AKShare sentiment for {symbol}: {e}")
                results[symbol] = {"error": str(e)}

        return results

    def save_sentiment_data(self, conn, sentiment_data: dict[str, Any]) -> int:
        """
        Save sentiment data to database.

        Args:
            conn: DuckDB connection
            sentiment_data: Dict from collect_akshare_sentiment

        Returns:
            Number of records inserted
        """
        inserted_count = 0

        try:
            conn.execute("BEGIN TRANSACTION")

            # Get next ID
            max_id_result = conn.execute("SELECT COALESCE(MAX(id), 0) FROM sentiment_scores").fetchone()
            next_id = max_id_result[0] + 1 if max_id_result else 1

            for symbol, data in sentiment_data.items():
                if "error" in data:
                    continue

                # Save composite sentiment - use stock_id column
                from datetime import datetime
                sentiment_ts = datetime.fromisoformat(data["timestamp"])
                sentiment_date = sentiment_ts.date()
                conn.execute(
                    """
                    INSERT INTO sentiment_scores
                    (id, stock_id, timestamp, sentiment_date, overall_score, source, created_at)
                    VALUES (?, ?, ?, ?, ?, 'akshare', CURRENT_TIMESTAMP)
                    """,
                    [
                        next_id,
                        symbol,
                        sentiment_ts,
                        sentiment_date,
                        data["composite_sentiment"],
                    ],
                )
                next_id += 1
                inserted_count += 1

            conn.execute("COMMIT")
            self.logger.info(f"Saved {inserted_count} sentiment records")
            return inserted_count

        except Exception as e:
            conn.execute("ROLLBACK")
            # Table might not exist, try to create it
            self.logger.warning(f"Failed to save sentiment data, creating table: {e}")
            self._ensure_sentiment_table(conn)
            return 0

    def _ensure_sentiment_table(self, conn):
        """
        Ensure sentiment_scores table exists.

        Note: This method checks if the table exists. The table should be created
        by init_db.py with the proper schema. If the table doesn't exist, we create
        a minimal version matching the init_db.py schema.
        """
        try:
            # Check if table exists
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sentiment_scores'"
            ).fetchone()

            if result is None:
                # Table doesn't exist, create it with the same schema as init_db.py
                self.logger.info("sentiment_scores table not found, creating it...")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sentiment_scores (
                        id INTEGER PRIMARY KEY,
                        stock_id VARCHAR(20),
                        timestamp TIMESTAMP,
                        sentiment_date DATE,
                        overall_score DECIMAL(5,4),
                        news_count INTEGER,
                        news_score DECIMAL(5,4),
                        social_count INTEGER,
                        social_score DECIMAL(5,4),
                        source VARCHAR(50),
                        model_version VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(stock_id, timestamp, source)
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sentiment_stock_time ON sentiment_scores(stock_id, timestamp)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sentiment_date ON sentiment_scores(sentiment_date)"
                )
                self.logger.info("Created sentiment_scores table")
            else:
                self.logger.debug("sentiment_scores table already exists")
        except Exception:
            # DuckDB uses different system tables
            try:
                result = conn.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_name='sentiment_scores'"
                ).fetchone()

                if result is None:
                    self.logger.info("sentiment_scores table not found, creating it...")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS sentiment_scores (
                            id INTEGER PRIMARY KEY,
                            stock_id VARCHAR(20),
                            timestamp TIMESTAMP,
                            sentiment_date DATE,
                            overall_score DECIMAL(5,4),
                            news_count INTEGER,
                            news_score DECIMAL(5,4),
                            social_count INTEGER,
                            social_score DECIMAL(5,4),
                            source VARCHAR(50),
                            model_version VARCHAR(50),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(stock_id, timestamp, source)
                        )
                    """)
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_sentiment_stock_time ON sentiment_scores(stock_id, timestamp)"
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_sentiment_date ON sentiment_scores(sentiment_date)"
                    )
                    self.logger.info("Created sentiment_scores table")
                else:
                    self.logger.debug("sentiment_scores table already exists")
            except Exception as e2:
                self.logger.error(f"Failed to create sentiment_scores table: {e2}")

    # ==================== Main Collection Method ====================

    def collect_sentiment(
        self,
        source: str = "all",
        days: int = 7,
        max_articles: int = 1000,
        symbols: list[str] | None = None,
    ):
        """
        Collect sentiment data from specified sources.

        Args:
            source: 'eastmoney', 'sina', 'akshare', or 'all'
            days: Number of days to look back (for news)
            max_articles: Maximum articles per source
            symbols: List of symbols for AKShare collection

        Returns:
            Summary statistics dict
        """
        conn = self._connect_database()

        try:
            stats = {"sources": {}, "total_articles": 0, "new_articles": 0, "sentiment_records": 0}

            # Determine sources to fetch
            if source == "all":
                sources_to_fetch = ["eastmoney", "sina", "akshare"]
            else:
                sources_to_fetch = [source]

            # Collect news articles
            news_sources = [s for s in sources_to_fetch if s in ["eastmoney", "sina"]]
            all_articles = []

            for src in news_sources:
                try:
                    self.logger.info(f"Collecting news from {src}...")
                    articles = self._retry_with_backoff(
                        self.fetch_eastmoney_news if src == "eastmoney" else self.fetch_sina_news,
                        days=days,
                        max_articles=max_articles,
                    )
                    all_articles.extend(articles)
                    stats["sources"][src] = len(articles)
                    self.logger.info(f"✓ Collected {len(articles)} articles from {src}")
                except SentimentCollectionError as e:
                    self.logger.error(f"Failed to collect from {src}: {e}")
                    stats["sources"][src] = 0

            # Save news articles
            stats["total_articles"] = len(all_articles)
            if all_articles:
                stats["new_articles"] = self.save_news_articles(conn, all_articles)

            # Collect AKShare sentiment
            if "akshare" in sources_to_fetch:
                try:
                    self.logger.info("Collecting AKShare sentiment data...")

                    # Default to CSI 300 symbols if not provided
                    if symbols is None:
                        symbols = self._get_default_symbols(conn)

                    if symbols:
                        sentiment_data = self.collect_akshare_sentiment(symbols)
                        self._ensure_sentiment_table(conn)
                        stats["sentiment_records"] = self.save_sentiment_data(conn, sentiment_data)
                        stats["sources"]["akshare"] = stats["sentiment_records"]
                        self.logger.info(f"✓ Collected sentiment for {len(symbols)} symbols")
                    else:
                        self.logger.warning("No symbols available for AKShare collection")
                        stats["sources"]["akshare"] = 0

                except Exception as e:
                    self.logger.error(f"Failed to collect AKShare sentiment: {e}")
                    stats["sources"]["akshare"] = 0

            # Print summary
            self.logger.info("=" * 80)
            self.logger.info("Sentiment Collection Summary")
            self.logger.info("=" * 80)
            for src, count in stats["sources"].items():
                self.logger.info(f"  {src}: {count}")
            self.logger.info(f"Total articles: {stats['total_articles']}")
            self.logger.info(f"New articles saved: {stats['new_articles']}")
            self.logger.info(f"Sentiment records: {stats['sentiment_records']}")

            return stats

        finally:
            conn.close()

    def _get_default_symbols(self, conn) -> list[str]:
        """Get default symbols from database (CSI 300 constituents)."""
        try:
            result = conn.execute("""
                SELECT DISTINCT symbol FROM stock_constituents
                WHERE index_code = '000300'
                ORDER BY symbol
                LIMIT 50
            """).fetchall()
            return [row[0] for row in result]
        except Exception:
            # Fallback to some popular stocks
            return ["600519", "000001", "601318", "600036", "000858"]


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Collect sentiment data for Chinese stocks")
    parser.add_argument(
        "--source",
        choices=["all", "eastmoney", "sina", "akshare"],
        default="all",
        help="Data source to use",
    )
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back")
    parser.add_argument(
        "--max-articles", type=int, default=1000, help="Maximum articles per source"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated list of symbols for AKShare collection",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.json (default: data/config.json)",
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Parse symbols if provided
    symbols = None
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]

    try:
        collector = SentimentCollector(config_path=args.config)

        collector.collect_sentiment(
            source=args.source,
            days=args.days,
            max_articles=args.max_articles,
            symbols=symbols,
        )

        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
