# Chinese Stock Trading System - Data Pipeline

**Status:** Phase 1 Complete - Research & Design Complete
**Next Step:** Install dependencies and run data collection scripts

---

## Quick Start

### 1. Install Python Dependencies

The system requires Python 3.8+ with the following packages:

```bash
# Install pip (if not already installed)
python3 -m pip install --user --break-system-packages pip

# Install required packages
~/.local/bin/pip install -r requirements.txt --break-system-packages
```

### 2. Initialize Database

```bash
python init_db.py
```

This creates the DuckDB database at `~/trade/stocks/data/stocks.duckdb` with all required tables.

### 3. Collect CSI 300 Constituents

```bash
python collect_csi300.py
```

Fetches the current CSI 300 constituent stocks from Akshare.

### 4. Collect Historical Price Data

```bash
# Collect 1 year of historical data (default)
python collect_historical_prices.py

# Collect 3 years of historical data
python collect_historical_prices.py --years 3
```

---

## File Structure

```
~/trade/stocks/
├── data/
│   ├── stocks.duckdb          # Main database (created after init_db.py)
│   ├── exports/               # Parquet exports (create manually)
│   ├── logs/                  # Collection logs (create manually)
│   ├── config.json            # Configuration file ✓
│   ├── ANALYSIS.md            # Detailed analysis report ✓
│   ├── README.md              # This file ✓
│   ├── requirements.txt       # Python dependencies ✓
│   ├── init_db.py             # Database initialization script ✓
│   ├── collect_csi300.py      # CSI 300 collection script ✓
│   └── collect_historical_prices.py  # Price collection script ✓
```

---

## Current Status

### ✅ Completed
- [x] Data source research (Tushare, Akshare, Baostock)
- [x] Database schema design (DuckDB)
- [x] Configuration file created
- [x] Database initialization script
- [x] CSI 300 collection script
- [x] Historical price collection script
- [x] Requirements file

### ⏳ Next Steps (Dependencies Required)
- [ ] Install Python packages (`pip install -r requirements.txt`)
- [ ] Run `init_db.py` to create database
- [ ] Run `collect_csi300.py` to fetch stock list
- [ ] Run `collect_historical_prices.py` to fetch price data
- [ ] Create fundamental data collection script
- [ ] Create daily update script
- [ ] Set up cron jobs for automated updates

### 📋 Future Enhancements
- [ ] Sentiment analysis pipeline (Chinese NLP)
- [ ] News collection from multiple sources
- [ ] Data quality checks and validation
- [ ] Export utilities (to Parquet/CSV)
- [ ] Monitoring and alerting
- [ ] Web dashboard for data visualization

---

## Database Schema

The database consists of the following tables:

| Table | Purpose | Records (after init) |
|-------|---------|---------------------|
| `stocks` | Stock metadata and CSI 300 membership | 0 |
| `daily_prices` | Daily OHLCV price data | 0 |
| `fundamentals` | Fundamental indicators (P/E, P/B, ROE) | 0 |
| `sentiment_scores` | Aggregated sentiment scores | 0 |
| `news_raw` | Raw news data for sentiment analysis | 0 |
| `csi300_history` | Historical CSI 300 changes | 0 |

See `ANALYSIS.md` for detailed schema documentation.

---

## Data Sources

### Primary: Akshare
- **Cost:** Free
- **Coverage:** Comprehensive (stocks, funds, futures, news)
- **Reliability:** Good for research (scraping-based)
- **Setup:** No API token required

### Secondary: Baostock
- **Cost:** Free
- **Coverage:** A-shares focused
- **Reliability:** Stable (official API)
- **Setup:** No API token required

### Future: Tushare Pro
- **Cost:** ¥600-2000/year
- **Coverage:** Most comprehensive
- **Reliability:** High (official API)
- **Setup:** Requires API token registration

See `ANALYSIS.md` for detailed comparison.

---

## Usage Examples

### Query Database Directly

```python
import duckdb

conn = duckdb.connect('~/trade/stocks/data/stocks.duckdb')

# Get all CSI 300 stocks
stocks = conn.execute("""
    SELECT stock_id, name, ts_code
    FROM stocks
    WHERE is_csi300 = TRUE
    ORDER BY stock_id
""").fetchdf()

print(stocks)

# Get latest price for a stock
price = conn.execute("""
    SELECT *
    FROM daily_prices
    WHERE stock_id = '600000'
    ORDER BY trade_date DESC
    LIMIT 1
""").fetchdf()

print(price)

conn.close()
```

### Export to Parquet

```python
import duckdb

conn = duckdb.connect('~/trade/stocks/data/stocks.duckdb')

# Export CSI 300 prices to Parquet
conn.execute("""
    COPY (
        SELECT p.*, s.name
        FROM daily_prices p
        JOIN stocks s ON p.stock_id = s.stock_id
        WHERE s.is_csi300 = TRUE
    ) TO '~/trade/stocks/data/exports/csi300_prices.parquet'
    (FORMAT 'parquet', COMPRESSION 'snappy')
""")

print("Exported to csi300_prices.parquet")

conn.close()
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'xxx'"
**Solution:** Install the missing package:
```bash
~/.local/bin/pip install xxx --break-system-packages
```

### "externally-managed-environment" error
**Solution:** Use the `--break-system-packages` flag with pip install

### DuckDB database locked
**Solution:** Ensure no other process is using the database, then retry

### Akshare scraping errors
**Solution:**
1. Add delay between requests
2. Use Baostock as backup
3. Check if source website has changed their structure

---

## Performance Notes

### DuckDB Advantages
- **Fast queries:** Columnar storage optimized for analytics
- **Zero setup:** No server required
- **Single file:** Easy to backup and move
- **SQL support:** Standard SQL with advanced features
- **Python integration:** Native pandas DataFrame support

### Expected Data Size
- **CSI 300 stocks:** 300 records
- **1 year daily prices:** ~300 × 250 = 75,000 records
- **Database size:** ~5-10 MB (compressed)
- **Export to Parquet:** ~3-5 MB (snappy compressed)

---

## Support & Documentation

- **Detailed analysis:** See `ANALYSIS.md`
- **Schema design:** See `ANALYSIS.md` Section 3
- **API documentation:**
  - Akshare: https://akshare.akfamily.xyz
  - Baostock: https://baostock.com
  - DuckDB: https://duckdb.org/docs

---

## License & Attribution

This is a personal trading system research project.

Data sources:
- Akshare: Open source, MIT license
- Baostock: Free for personal use
- DuckDB: MIT license

---

**Last updated:** 2026-03-08
**Status:** Ready for data collection (dependencies pending)
