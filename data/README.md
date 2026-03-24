# Data Collection Module

Data collection and analysis module for Chinese A-share stocks using AKShare APIs.

## Overview

This module provides:
1. **Sentiment data collection** - Derives market sentiment from behavior proxies
2. **Verdict analysis** - Combines sentiment + valuation for trading signals
3. **DuckDB storage** - Persists sentiment data for strategy consumption

## Architecture

```
data/
├── __init__.py              # Module exports (lazy imports)
├── config.json              # Configuration (weights, rate limits)
├── sentiment_collector.py   # Sentiment collection orchestrator
├── providers.py             # Sentiment data providers (4 sources)
├── storage.py               # DuckDB persistence layer
└── verdict.py               # Sentiment + Valuation analysis
```

## Module Exports

```python
from data import SentimentCollector, SentimentStorage, SentimentDataProvider, VerdictCalculator
```

---

## Sentiment Collection

Collects market sentiment by deriving it from behavior proxies (direct sentiment APIs unavailable for A-shares).

### Sentiment Sources

| Source | Weight | AKShare APIs | Derivation |
|--------|--------|--------------|------------|
| **social** | 35% | `stock_hot_rank_em` | Popularity rank + price movement |
| **news** | 40% | `stock_lhb_stock_statistic_em` + `stock_hsgt_hold_stock_em` | Dragon-tiger + Northbound holdings |
| **forum** | 10% | `stock_market_fund_flow` + `stock_margin_detail_*` | Main force flow + Margin |
| **search** | 15% | `stock_margin_detail_*` + `stock_zh_a_spot_em` | Margin + Volume |

### Usage

```bash
# Run daily collection
uv run python -m data.sentiment_collector

# Query specific stocks
uv run python -m data.sentiment_collector --symbols 600519,000001
```

```python
from data import SentimentCollector, SentimentStorage

collector = SentimentCollector()
counts = collector.run_collection()
print(f"Stored {counts['raw']} raw and {counts['composite']} composite scores")

# Get latest sentiment
latest = collector.get_latest_sentiment(["600519", "000001"])
```

---

## Verdict Analysis

Combines sentiment scores with valuation metrics to generate trading signals using contrarian logic:
- **BUY**: Bearish sentiment + Undervalued fundamentals
- **SELL**: Bullish sentiment + Overvalued fundamentals

### Usage

```bash
# Bottom 10 (contrarian buy candidates - bearish + undervalued)
uv run python data/verdict.py --bottom-n 10

# Top 10 (potential sell candidates - bullish + overvalued)
uv run python data/verdict.py --top-n 10

# Custom output format
uv run python data/verdict.py --bottom-n 20 --output csv

# Adjust sentiment weight
uv run python data/verdict.py --bottom-n 10 --weight-sentiment 0.6
```

### Output

```
----------------------------------------------------------------------------------------------------
 Rank | Symbol   | Name       | Sentiment | V Score  | Combined | Verdict |       PE |     PB |   Div%
----------------------------------------------------------------------------------------------------
    1 | 600519   | 贵州茅台    |     -2.15 |    0.250 |     72.5 | BUY     |    25.3 |   8.12 |   1.62
    2 | 000858   | 五粮液      |     -1.89 |    0.180 |     68.3 | BUY     |    18.5 |   4.25 |   2.10
```

### Python API

```python
from data import VerdictCalculator

calculator = VerdictCalculator(weight_sentiment=0.5)

# Get bottom N (bearish) stocks
stocks = calculator.get_bottom_n_sentiment(10)
results = calculator.analyze_stocks(stocks, is_bottom_n=True)

for r in results:
    print(f"{r.symbol}: sentiment={r.sentiment_score:.2f}, V={r.valuation_score:.3f}, verdict={r.verdict.value}")

calculator.close()
```

---

## Storage API

```python
from data.storage import SentimentStorage

storage = SentimentStorage("data/sentiment.db")

# Store composite score
storage.store_composite_score(
    symbol="600519",
    timestamp=datetime.now(),
    score=0.5,
    confidence=0.8,
    source_scores={"news": 0.6, "social": 0.4}
)

# Query latest scores
latest = storage.get_latest_composite(["600519"])

# Get stock names (cached)
names = storage.get_stock_names(["600519", "000001"])
```

---

## Database Schema

### sentiment_raw
Raw sentiment scores by source:
- `symbol`, `timestamp`, `source`, `score`, `confidence`, `raw_data`

### sentiment_composite
Aggregated composite scores:
- `symbol`, `timestamp`, `score`, `confidence`, `source_scores`

### stock_names
Stock name cache:
- `symbol`, `name`, `updated_at`

---

## AKShare APIs Used

| API | Description | Use Case |
|-----|-------------|----------|
| `stock_zh_a_spot_em` | All A-share real-time quotes | PE, PB, price data |
| `stock_hot_rank_em` | Top 100 popularity ranking | Social sentiment |
| `stock_market_fund_flow` | Market-wide fund flow | Forum sentiment |
| `stock_hsgt_hold_stock_em` | Northbound holdings | News sentiment |
| `stock_lhb_stock_statistic_em` | Dragon-tiger statistics | News sentiment |
| `stock_margin_detail_sse/szse` | Margin trading | Forum/Search sentiment |
| `stock_history_dividend` | Dividend history | Dividend yield |

---

## Configuration

Edit `data/config.json`:

```json
{
  "database": {
    "path": "data/sentiment.db",
    "batch_size": 1000
  },
  "collection": {
    "daily_batch_enabled": true,
    "trading_days_only": true,
    "max_retries": 3
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
