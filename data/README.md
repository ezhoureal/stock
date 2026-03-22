# Chinese Stock Trading System - Data Pipeline

**Status:** Production Ready - Multi-source data collection with sector-aware valuation

---

## Quick Start

### 1. Initialize Database

```bash
uv run python data/init_db.py
```

Creates the DuckDB database with all required tables including the `sectors` table for industry classification.

### 2. Collect Stock Universe

```bash
# Collect CSI 300 constituents (300 stocks)
uv run python data/collect_csi300.py

# Collect ALL A-share stocks (5,000+ stocks)
uv run python data/collect_all_ashare.py
```

### 3. Collect Historical Prices

```bash
# Production-ready collection with automatic fallback
uv run python data/collect_prices.py --source auto

# Use specific source
uv run python data/collect_prices.py --source baostock
uv run python data/collect_prices.py --source akshare

# Custom date range
uv run python data/collect_prices.py --start-date 2023-01-01 --end-date 2024-01-01
```

### 4. Collect Fundamental Data

```bash
# Collect fundamentals with sector classification for CSI 300
uv run python data/collect_fundamentals.py --universe csi300

# Collect for all A-shares
uv run python data/collect_fundamentals.py --universe all

# Skip sector data collection
uv run python data/collect_fundamentals.py --universe csi300 --skip-sectors
```

### 5. Rank Stocks (Sentiment + Valuation)

```bash
# Rank CSI 300 stocks
uv run python data/rank_stocks.py --universe csi300 --top 20

# Rank all A-shares, show only BUY signals
uv run python data/rank_stocks.py --universe all --top 20 --signal-type BUY

# Save to custom output directory
uv run python data/rank_stocks.py --universe csi300 --output-dir /path/to/output
```

---

## File Structure

```
data/
├── stocks.duckdb                   # Main database
├── config.json                     # Configuration file
├── init_db.py                      # Database initialization
├── collect_csi300.py               # CSI 300 constituent collection
├── collect_all_ashare.py           # ALL A-share stock collection (NEW)
├── collect_prices.py               # Production price collection (recommended)
├── collect_fundamentals.py         # Fundamental data with sector classification (NEW)
├── collect_sentiment.py            # Sentiment data collection
├── rank_stocks.py                  # Stock ranking engine (NEW)
├── output/                         # Ranking output directory
│   └── stock_rankings_YYYYMMDD.csv
└── logs/                           # Collection logs
    ├── price_collection.log
    └── sentiment_collection.log
```

---

## Available Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `init_db.py` | Initialize DuckDB schema | `uv run python data/init_db.py` |
| `collect_csi300.py` | Fetch CSI 300 constituents | `uv run python data/collect_csi300.py` |
| `collect_all_ashare.py` | Fetch all A-share stocks (5,000+) | `uv run python data/collect_all_ashare.py` |
| `collect_prices.py` | Production price collection with fallback | `uv run python data/collect_prices.py --source auto` |
| `collect_fundamentals.py` | P/E, P/B, ROE with sector data | `uv run python data/collect_fundamentals.py --universe csi300` |
| `collect_sentiment.py` | News and market sentiment | `uv run python data/collect_sentiment.py --source all` |
| `rank_stocks.py` | Rank by sentiment + valuation | `uv run python data/rank_stocks.py --universe csi300 --top 20` |

---

## Database Schema

### Core Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `stocks` | Stock metadata | stock_id, name, sector, is_csi300, is_active |
| `daily_prices` | OHLCV price data | stock_id, trade_date, open, high, low, close, volume |
| `fundamentals` | Valuation metrics | stock_id, report_date, pe, pb, roe, total_mv |
| `sectors` | Industry classification | sector_code, sector_name, pe_ratio, pb_ratio |
| `sentiment_scores` | Aggregated sentiment | stock_id, timestamp, overall_score, news_score |
| `news_raw` | Raw news articles | stock_id, title, content, publish_time, sentiment_raw |
| `csi300_history` | Index membership history | stock_id, entry_date, exit_date, weight |

### Sector-Aware Valuation

The `sectors` table enables sector-relative valuation comparisons:

```sql
-- Compare stock P/E to sector average
SELECT
    s.stock_id,
    s.name,
    f.pe,
    sec.pe_ratio as sector_pe,
    (f.pe / sec.pe_ratio - 1) * 100 as pe_premium_pct
FROM stocks s
JOIN fundamentals f ON s.stock_id = f.stock_id
JOIN sectors sec ON s.sector = sec.sector_code
WHERE f.report_date = (SELECT MAX(report_date) FROM fundamentals)
```

---

## Stock Ranking System

The `rank_stocks.py` script implements a contrarian strategy:

### Signal Logic

| Signal | Conditions | Rank |
|--------|------------|------|
| **BUY** | Bearish sentiment (< -1.5) + Undervalued (V > +0.10) | HIGH |
| **SELL** | Bullish sentiment (> +1.5) + Overvalued (V < -0.10) | LOW |
| **HOLD** | Neutral sentiment or fair valuation | MEDIUM |

### Combined Strength Score

The ranking combines sentiment and valuation into a 0-100 strength score:

```
BUY Strength = (bearishness_weight + undervaluation_weight) / 2 * 100
SELL Strength = (bullishness_weight + overvaluation_weight) / 2 * 100
```

### Output Format

```
Rank   Code     Name         Sentiment   Valuation   Strength  Signal
--------------------------------------------------------------------------------
1      600519   Kweichow Moutai  -0.850      0.250      85.2    BUY
2      000001   Ping An Bank     -0.720      0.180      72.5    BUY
...
```

Results are also saved to `data/output/stock_rankings_YYYYMMDD.csv`.

---

## Data Sources

### Primary: AKShare
- **Cost:** Free
- **Coverage:** Comprehensive (stocks, funds, futures, news, sector data)
- **Reliability:** Good for research (scraping-based)
- **Setup:** No API token required

### Secondary: Baostock
- **Cost:** Free
- **Coverage:** A-shares focused
- **Reliability:** Stable (official API)
- **Setup:** No API token required

### Sector Data: Shenwan (申万)
- **Source:** AKShare `stock_industry_clf_hist_sw`
- **Coverage:** 3-level industry classification
- **Usage:** Sector-relative valuation comparisons

---

## Usage Examples

### Query Database Directly

```python
import duckdb

conn = duckdb.connect('data/stocks.duckdb')

# Get all CSI 300 stocks with sectors
stocks = conn.execute("""
    SELECT stock_id, name, sector, is_csi300
    FROM stocks
    WHERE is_csi300 = TRUE
    ORDER BY stock_id
""").fetchdf()

# Get latest fundamentals with sector comparison
fundamentals = conn.execute("""
    SELECT
        f.stock_id,
        s.name,
        s.sector,
        f.pe,
        f.pb,
        sec.pe_ratio as sector_pe
    FROM fundamentals f
    JOIN stocks s ON f.stock_id = s.stock_id
    LEFT JOIN sectors sec ON s.sector = sec.sector_code
    WHERE f.report_date = (SELECT MAX(report_date) FROM fundamentals)
""").fetchdf()

conn.close()
```

### Export Rankings to Parquet

```python
import duckdb
import pandas as pd

# Read rankings CSV and convert to Parquet
df = pd.read_csv('data/output/stock_rankings_20260314.csv')
df.to_parquet('data/output/stock_rankings_20260314.parquet', compression='snappy')
```

---

## Redundant Files (To Be Removed)

The following files are superseded by `collect_prices.py` and can be removed:

| File | Status | Replacement |
|------|--------|-------------|
| `collect_historical_prices.py` | **Deprecated** | `collect_prices.py` |
| `collect_historical_prices_baostock.py` | **Deprecated** | `collect_prices.py --source baostock` |

**Reason:** `collect_prices.py` provides:
- Automatic source fallback (Baostock -> AKShare)
- Robust error handling and retry logic
- Data validation
- Rate limiting
- Comprehensive logging
- Both single-stock and batch collection modes

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'xxx'"
**Solution:** Install the missing package:
```bash
uv pip install xxx
```

### DuckDB database locked
**Solution:** Ensure no other process is using the database, then retry

### AKShare scraping errors
**Solution:**
1. Add delay between requests (built into collect_prices.py)
2. Use Baostock as backup: `collect_prices.py --source baostock`
3. Check if source website has changed their structure

### No sector data available
**Solution:** Run `collect_fundamentals.py` with sector collection enabled (default):
```bash
uv run python data/collect_fundamentals.py --universe csi300
```

---

## Performance Notes

### Expected Data Size
- **CSI 300 stocks:** 300 records
- **All A-shares:** 5,000+ records
- **1 year daily prices:** ~300 x 250 = 75,000 records (CSI 300 only)
- **Fundamentals:** One record per stock per quarter
- **Database size:** ~10-50 MB (compressed)

### Collection Time
- `collect_csi300.py`: ~5 seconds
- `collect_all_ashare.py`: ~30 seconds
- `collect_prices.py` (CSI 300, 1 year): ~5-10 minutes
- `collect_fundamentals.py` (CSI 300): ~1 minute
- `rank_stocks.py` (CSI 300): ~2-3 minutes

---

## Development

### Code Quality

Always run linting before committing:

```bash
uv run ruff check --fix .
uv run ruff format .
```

### Testing

```bash
# Test price collection
uv run python data/collect_prices.py --source auto --stock-id 600519

# Test ranking
uv run python data/rank_stocks.py --universe csi300 --top 10
```

---

## Support & Documentation

- **AKShare docs:** https://akshare.akfamily.xyz
- **Baostock docs:** https://baostock.com
- **DuckDB docs:** https://duckdb.org/docs
- **Project CLAUDE.md:** `/Users/zireael/stock/CLAUDE.md`

---

**Last updated:** 2026-03-14
**Status:** Production Ready
