# Data Collection Module

Sentiment data collection module for Chinese A-share stocks using AKShare APIs.

## Overview

This module collects market sentiment indicators by deriving them from market behavior proxies, since direct sentiment APIs (舆情) are not available for Chinese A-shares. The sentiment data feeds the `sentiment_strategy` module for trading decisions.

## Architecture

```
data/
├── __init__.py              # Module exports (lazy imports)
├── config.json              # Configuration (weights, rate limits, etc.)
├── sentiment_collector.py   # Main orchestrator
├── providers.py              # 4 sentiment source providers
├── storage.py                # DuckDB persistence layer
└── API/                      # AKShare API documentation
```

## Sentiment Sources

The system aggregates sentiment from 4 sources, each with configurable weights:

| Source | Weight | AKShare APIs | Derivation Formula |
|--------|--------|--------------|-------------------|
| **social** | 35% | `stock_hot_rank_em` | Popularity rank + price movement |
| **news** | 40% | `stock_lhb_stock_statistic_em` + `stock_hsgt_hold_stock_em` | Dragon-tiger net buy + Northbound holdings |
| **forum** | 10% | `stock_market_fund_flow` + `stock_margin_detail_*` | Main force flow + Margin balance |
| **search** | 15% | `stock_margin_detail_*` + `stock_zh_a_spot_em` | Margin change + Trading volume |

### Social Sentiment (35%)
Derived from `stock_hot_rank_em` which shows the top 100 stocks by popularity ranking:
- **Top 10% popular + price drop < -2%**: -0.6 (panic selling)
- **Top 10% popular + price rise > 2%**: +0.6 (FOMO buying)
- **Top 10% popular + moderate change**: +0.3 (curiosity)
- **Others**: `rank_percentile × 0.2`

### News Sentiment (40%)
Derived from dragon-tiger list and Northbound holdings:
```
sentiment = 0.6 × dragon_tiger_ratio + 0.4 × northbound_change
```

### Forum Sentiment (10%)
Derived from fund flow and margin trading:
```
sentiment = 0.6 × main_force_ratio + 0.4 × margin_change
```

### Search Sentiment (15%)
Derived from margin balance and volume:
```
sentiment = 0.6 × margin_change + 0.4 × (volume_ratio - 1)
```

## Usage

### Command Line

```bash
# Run daily collection for all stocks
uv run python -m data.sentiment_collector

# Query latest sentiment for specific stocks
uv run python -m data.sentiment_collector --symbols 600519,000001

# Verbose mode
uv run python -m data.sentiment_collector --verbose
```

### Python API

```python
from data import SentimentCollector, SentimentStorage

# Create collector
collector = SentimentCollector()

# Run daily collection
counts = collector.run_collection()
print(f"Stored {counts['raw']} raw and {counts['composite']} composite scores")

# Get latest sentiment
latest = collector.get_latest_sentiment(["600519", "000001"])
for symbol, score in latest.items():
    print(f"{symbol}: {score.score:+.3f} (confidence: {score.confidence:.2f})")

# Get historical sentiment
from datetime import datetime, timedelta
end = datetime.now()
start = end - timedelta(days=30)
history = collector.get_sentiment_history(["600519"], start, end, source="news")
```

### Storage API

```python
from data.storage import SentimentStorage

# Open database
storage = SentimentStorage("data/sentiment.db")

# Store raw scores
storage.store_raw_scores(sentiment_scores)

# Store composite scores
storage.store_composite_score(
    symbol="600519",
    timestamp=datetime.now(),
    score=0.5,
    confidence=0.8,
    source_scores={"news": 0.6, "social": 0.4}
)

# Query data
latest = storage.get_latest_composite(["600519"])
history = storage.get_sentiment(["600519"], start, end, source="news")
```

## Database Schema

### sentiment_raw
Raw sentiment scores by source:
- `id`: Auto-increment primary key
- `symbol`: Stock code (e.g., "600519")
- `timestamp`: Collection time
- `source`: "news", "social", "search", or "forum"
- `score`: Sentiment score (-1 to 1)
- `confidence`: Confidence level (0 to 1)
- `raw_data`: JSON with metadata
- `created_at`: Record creation time

### sentiment_composite
Aggregated composite scores:
- `id`: Auto-increment primary key
- `symbol`: Stock code
- `timestamp`: Collection time
- `score`: Weighted composite score
- `confidence`: Average confidence
- `source_scores`: JSON with individual source scores

## Configuration

Edit `data/config.json` to customize:

```json
{
  "database": {
    "path": "data/sentiment.db",
    "batch_size": 1000
  },
  "collection": {
    "daily_batch_enabled": true,
    "trading_days_only": true,
    "max_retries": 3,
    "retry_delay_seconds": 2
  },
  "sentiment": {
    "weights": {
      "news": 0.40,
      "social": 0.35,
      "search": 0.15,
      "forum": 0.10
    }
  }
}
```

## AKShare API Queries

This module uses batch-friendly AKShare APIs that return all stocks at once:

| API | Description | Frequency |
|-----|-------------|-----------|
| `stock_zh_a_spot_em` | All A-share real-time quotes (~5000 stocks) | Daily |
| `stock_hot_rank_em` | Top 100 popularity ranking | Daily |
| `stock_market_fund_flow` | Market-wide fund flow | Daily |
| `stock_hsgt_hold_stock_em` | Northbound holdings ranking | Daily |
| `stock_lhb_stock_statistic_em` | Dragon-tiger statistics | Daily |
| `stock_margin_detail_sse` | SSE margin trading details | Daily |
| `stock_margin_detail_szse` | SZSE margin trading details | Daily |

> **Note**: Use the `/akshare` skill to search for AKShare API documentation:
> ```
> User: What's the AKShare function for dragon-tiger list?
> Assistant: /akshare 龙虎榜
> ```

## Testing

Run the test suite:

```bash
# Run all data module tests
uv run pytest tests/data/ -v

# Run specific test file
uv run pytest tests/data/test_providers.py -v

# Run with coverage
uv run pytest tests/data/ --cov=data --cov-report=html
```

### Test Coverage

- `test_storage.py`: DuckDB CRUD operations (11 tests)
- `test_providers.py`: Sentiment calculation logic (9 tests)
- `test_collector.py`: Orchestration and aggregation (10 tests)

All tests pass: **32/32 ✅**

## Integration with Trading System

The sentiment data integrates with the `sentiment_strategy` module:

```python
from sentiment_strategy import SentimentStrategy
from data.storage import SentimentStorage

# Get sentiment data provider
storage = SentimentStorage("data/sentiment.db")

# Create strategy with sentiment data
strategy = SentimentStrategy(config)
strategy.set_data_provider(storage)

# Generate signals using sentiment
signals = strategy.generate(["600519", "000001"])
```

## Notes

### Network Limitations

AKShare APIs may be rate-limited or blocked depending on your network. If you encounter connection errors:
1. Try again later (rate limits reset daily)
2. Use a VPN if accessing from outside China
3. The module implements retry logic with `max_retries` config

### Data Quality

Sentiment scores are derived from market behavior proxies, not direct sentiment measures (news analysis, social media scraping). The accuracy depends on:
- Market efficiency (how quickly prices reflect sentiment)
- Liquidity (more traded stocks have better signals)
- Trading volume (higher volume = more reliable signals)

## License

Part of the Chinese Stock Trading System. See main project LICENSE.