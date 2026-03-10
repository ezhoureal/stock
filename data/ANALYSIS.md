# Chinese Stock Sentiment Trading System - Data Analysis

**Date:** 2026-03-08
**Role:** Data Analyst
**Status:** Phase 1 Complete - Research & Design

---

## 1. Data Source Evaluation

### Tushare (https://tushare.pro)

**Pros:**
- Official interface to China stock market data
- Comprehensive coverage: A-shares, funds, futures, options
- Python pandas DataFrame output
- Well-maintained and documented

**Cons:**
- **Free tier limitations:** 120 requests/minute, limited historical data access
- **Pro tier required for full access:** ¥600-2000/year
- Requires API token registration
- May have strict rate limits for data collection

**Coverage:**
- ✓ CSI 300 constituents
- ✓ Daily OHLCV (historical: free tier limited, full access with Pro)
- ✓ Fundamental indicators (P/E, P/B, ROE, etc.)
- ✓ Real-time market data
- ✓ News/announcements
- ⚠ Sentiment data: Not directly available, requires separate API

**Verdict:** Good for production, but requires Pro tier (¥600+/year) for sufficient historical data.

---

### Akshare (https://akshare.akfamily.xyz)

**Pros:**
- **100% FREE and open source**
- **No API token required**
- Scrapes public data sources (Sina Finance, Eastmoney, etc.)
- Comprehensive coverage: stocks, funds, futures, macro, options
- Active community, frequent updates
- Good for research and prototyping

**Cons:**
- Scraping-based - may be rate-limited or blocked by data sources
- Less stable than official APIs
- Data format may vary between updates
- No SLA or support guarantee

**Coverage:**
- ✓ CSI 300 constituents
- ✓ Daily OHLCV (historical via public sources)
- ✓ Fundamental indicators (P/E, P/B, ROE, etc.)
- ✓ Real-time market data
- ✓ News/announcements (from multiple sources)
- ⚠ Sentiment data: Can scrape news headlines/comments for sentiment analysis

**Verdict:** **RECOMMENDED for development and initial backtesting** - Free, comprehensive, no barriers.

---

### Baostock (https://baostock.com)

**Pros:**
- **100% FREE**
- **No API token required**
- Stable, structured API (not scraping-based)
- Good A-share focus
- Historical data quality is good
- Suitable for backtesting

**Cons:**
- Less comprehensive than Akshare
- Limited to A-shares and index data
- Fewer data fields available
- Smaller community

**Coverage:**
- ✓ CSI 300 constituents
- ✓ Daily OHLCV (historical available)
- ✓ Basic fundamental indicators
- ✗ Limited real-time data
- ✗ Limited news/sentiment data

**Verdict:** **RECOMMENDED as backup/secondary source** - Stable, good for price data, but less comprehensive.

---

## 2. Recommended Data Strategy

### Primary Source: Akshare
- Use for CSI 300 constituent list
- Use for daily OHLCV historical data
- Use for fundamental indicators
- Use for news/announcement scraping (for sentiment)

### Secondary Source: Baostock
- Use to verify/validate Akshare data
- Use as backup if Akshare scraping is blocked
- Use for consistent historical price data

### Future Consideration: Tushare Pro
- For production deployment if budget allows
- More reliable API with guaranteed uptime
- Wider range of data fields

---

## 3. Database Schema Design

### Recommended Database: DuckDB
**Why DuckDB over PostgreSQL?**
- ✅ Zero-setup, embedded database (no server required)
- ✅ Excellent SQL support with columnar storage
- ✅ Fast analytical queries (perfect for backtesting)
- ✅ Native Python integration
- ✅ Single-file storage (easy to backup/move)
- ✅ No additional infrastructure needed
- ✅ Great for time-series data with Parquet support

**Note:** Can migrate to PostgreSQL later if multi-user access or web services are needed.

---

### Schema Tables

#### 3.1 Stock Metadata Table
```sql
CREATE TABLE stocks (
    stock_id VARCHAR(20) PRIMARY KEY,
    ts_code VARCHAR(20),      -- Tushare code (e.g., 600000.SH)
    akshare_code VARCHAR(20), -- Akshare code (e.g., sh600000)
    baostock_code VARCHAR(20), -- Baostock code (e.g., sh.600000)
    name VARCHAR(100),
    industry VARCHAR(100),
    sector VARCHAR(100),
    list_date DATE,
    is_csi300 BOOLEAN,
    is_active BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stocks_csi300 ON stocks(is_csi300);
CREATE INDEX idx_stocks_active ON stocks(is_active);
```

#### 3.2 Daily Price Data (OHLCV)
```sql
CREATE TABLE daily_prices (
    id INTEGER PRIMARY KEY,
    stock_id VARCHAR(20),
    trade_date DATE,
    open DECIMAL(15,4),
    high DECIMAL(15,4),
    low DECIMAL(15,4),
    close DECIMAL(15,4),
    volume BIGINT,
    amount DECIMAL(20,2),        -- Turnover amount
    pct_chg DECIMAL(10,4),      -- Percent change
    adj_factor DECIMAL(15,8),   -- Adjust close factor
    data_source VARCHAR(20),    -- 'akshare' or 'baostock'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_id, trade_date, data_source)
);

CREATE INDEX idx_daily_prices_stock_date ON daily_prices(stock_id, trade_date);
CREATE INDEX idx_daily_prices_date ON daily_prices(trade_date);
```

#### 3.3 Fundamental Indicators
```sql
CREATE TABLE fundamentals (
    id INTEGER PRIMARY KEY,
    stock_id VARCHAR(20),
    report_date DATE,
    end_date DATE,
    pe DECIMAL(15,4),           -- P/E ratio
    pe_ttm DECIMAL(15,4),       -- P/E TTM
    pb DECIMAL(15,4),           -- P/B ratio
    ps DECIMAL(15,4),           -- P/S ratio
    ps_ttm DECIMAL(15,4),       -- P/S TTM
    total_mv DECIMAL(20,2),     -- Total market value (million)
    circ_mv DECIMAL(20,2),      -- Circulating market value (million)
    roe DECIMAL(10,4),          -- Return on Equity
    roa DECIMAL(10,4),          -- Return on Assets
    gross_margin DECIMAL(10,4), -- Gross profit margin
    revenue DECIMAL(20,2),      -- Total revenue
    net_profit DECIMAL(20,2),   -- Net profit
    eps DECIMAL(15,4),          -- Earnings per share
    bps DECIMAL(15,4),          -- Book value per share
    data_source VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_id, report_date)
);

CREATE INDEX idx_fundamentals_stock_date ON fundamentals(stock_id, report_date);
```

#### 3.4 Sentiment Scores
```sql
CREATE TABLE sentiment_scores (
    id INTEGER PRIMARY KEY,
    stock_id VARCHAR(20),
    timestamp TIMESTAMP,
    sentiment_date DATE,        -- The date the sentiment applies to
    overall_score DECIMAL(5,4), -- -1.0 (bearish) to +1.0 (bullish)
    news_count INTEGER,
    news_score DECIMAL(5,4),   -- Sentiment from news
    social_count INTEGER,       -- Social media mentions
    social_score DECIMAL(5,4),  -- Sentiment from social media
    source VARCHAR(50),         -- 'news', 'social', 'combined'
    model_version VARCHAR(50),  -- Model used to compute score
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_id, timestamp, source)
);

CREATE INDEX idx_sentiment_stock_time ON sentiment_scores(stock_id, timestamp);
CREATE INDEX idx_sentiment_date ON sentiment_scores(sentiment_date);
```

#### 3.5 News/Social Media Raw Data (for sentiment analysis)
```sql
CREATE TABLE news_raw (
    id INTEGER PRIMARY KEY,
    stock_id VARCHAR(20),       -- NULL if not stock-specific
    title TEXT,
    content TEXT,
    summary TEXT,
    source VARCHAR(100),        -- Source website/platform
    url TEXT,
    publish_time TIMESTAMP,
    author VARCHAR(100),
    sentiment_raw DECIMAL(5,4), -- Raw sentiment if pre-tagged
    keywords TEXT,              -- Comma-separated keywords
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_news_stock ON news_raw(stock_id);
CREATE INDEX idx_news_time ON news_raw(publish_time);
CREATE INDEX idx_news_source ON news_raw(source);
```

#### 3.6 CSI 300 Constituents History
```sql
CREATE TABLE csi300_history (
    id INTEGER PRIMARY KEY,
    stock_id VARCHAR(20),
    entry_date DATE,
    exit_date DATE,            -- NULL if currently in index
    weight DECIMAL(8,4),        -- Index weight (if available)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_csi300_stock ON csi300_history(stock_id);
CREATE INDEX idx_csi300_date ON csi300_history(entry_date);
```

---

## 4. Data Collection Pipeline Design

### 4.1 Directory Structure
```
~/trade/stocks/
├── data/
│   ├── stocks.duckdb          # Main DuckDB database
│   ├── exports/               # Parquet exports for analysis
│   ├── logs/                  # Collection logs
│   ├── config.json            # Configuration
│   └── ANALYSIS.md           # This file
├── scripts/
│   ├── init_db.py            # Initialize database schema
│   ├── collect_prices.py     # Daily price data collection
│   ├── collect_fundamentals.py # Fundamental data collection
│   ├── collect_news.py       # News data collection
│   ├── compute_sentiment.py  # Sentiment analysis pipeline
│   └── export_data.py        # Export to Parquet
└── venv/                     # Python virtual environment
```

### 4.2 Collection Strategy

#### Phase 1: Historical Data (Initial Setup)
1. **CSI 300 Constituents:**
   - Fetch current list from Akshare
   - Store in `stocks` table and `csi300_history` table

2. **Historical Prices:**
   - Download 1 year of daily OHLCV for all CSI 300 stocks
   - Source: Akshare (primary), Baostock (backup/verification)
   - Store in `daily_prices` table

3. **Fundamental Data:**
   - Fetch latest P/E, P/B, ROE for all CSI 300 stocks
   - Store in `fundamentals` table

#### Phase 2: Daily Updates (Ongoing)
1. **Daily Price Update:** After market close (15:00+)
   - Fetch today's OHLCV for CSI 300
   - Update `daily_prices` table

2. **Fundamental Update:** Weekly or quarterly
   - Fetch updated fundamental indicators
   - Update `fundamentals` table

3. **CSI 300 Changes:** Monthly
   - Check for changes in constituent list
   - Update `stocks` and `csi300_history` tables

#### Phase 3: Sentiment Pipeline (Future)
1. **News Collection:**
   - Scrape news headlines daily from Sina Finance, Eastmoney
   - Store in `news_raw` table

2. **Sentiment Analysis:**
   - Process news to extract sentiment scores
   - Store aggregated daily sentiment in `sentiment_scores` table

---

## 5. Data Quality Checks

### 5.1 Validation Rules
- **Price data:** Open ≤ High, Low ≤ High, Low ≤ Close (within reasonable range)
- **Volume:** Non-negative
- **P/E, P/B:** Reasonable ranges (e.g., P/E: 0-1000, but flag outliers)
- **Date consistency:** Trade dates should be trading days (skip weekends/holidays)

### 5.2 Data Consistency
- Cross-validate between Akshare and Baostock for subset of data
- Check for missing data gaps
- Flag suspicious values for manual review

### 5.3 Monitoring
- Log all data collection runs
- Track missing data and failed fetches
- Send alerts if data quality degrades

---

## 6. Next Steps

### Immediate (To Do):
1. [ ] Install Python dependencies: akshare, baostock, pandas, duckdb
2. [ ] Create database initialization script (`scripts/init_db.py`)
3. [ ] Implement CSI 300 constituent fetcher
4. [ ] Implement historical price data fetcher (1 year)
5. [ ] Implement fundamental data fetcher
6. [ ] Create configuration file (`config.json`)

### Short-term (This Week):
1. [ ] Complete initial data collection for CSI 300
2. [ ] Set up daily update cron jobs
3. [ ] Create data export utilities (to Parquet)
4. [ ] Set up logging and monitoring

### Medium-term (Next Month):
1. [ ] Implement news collection pipeline
2. [ ] Implement sentiment analysis (Chinese NLP)
3. [ ] Create data quality dashboard
4. [ ] Document API usage and data refresh schedule

---

## 7. Data Source API Notes

### Akshare Key Functions
```python
import akshare as ak

# CSI 300 constituents
df_csi300 = ak.index_stock_cons(index="000300")

# Stock list
df_stocks = ak.stock_info_a_code_name()

# Historical daily prices
df_price = ak.stock_zh_a_hist(
    symbol="000001",  # Stock code
    period="daily",
    start_date="20250308",
    end_date="20260308",
    adjust=""         # "" = not adjusted, "hfq" = forward adjust
)

# Real-time quotes
df_realtime = ak.stock_zh_a_spot_em()

# Stock fundamentals (individual)
df_fundamental = ak.stock_a_indicator(symbol="000001")
```

### Baostock Key Functions
```python
import baostock as bs

# Login
lg = bs.login()

# Stock list
rs = bs.query_all_stock(day="2026-03-08")

# Historical prices
rs = bs.query_history_k_data_plus(
    "sh.600000",
    "date,code,open,high,low,close,volume,amount",
    start_date="2025-03-08",
    end_date="2026-03-08",
    frequency="d",
    adjustflag="3"  # 1=后复权, 2=前复权, 3=不复权
)

# Logout
bs.logout()
```

---

## 8. Known Limitations

1. **Akshare scraping reliability:**
   - Public sources may rate-limit or block automated access
   - Data format may change without notice
   - Mitigation: Use Baostock as backup, implement retry logic

2. **Sentiment data availability:**
   - No direct API for stock sentiment scores
   - Need to build custom NLP pipeline from news
   - Requires Chinese NLP libraries (jieba, transformers, etc.)

3. **Fundamental data frequency:**
   - Some metrics (ROE, revenue) only updated quarterly
   - Need to handle missing interim periods

4. **Market holidays:**
   - China market holidays differ from other markets
   - Need holiday calendar to avoid collection errors

---

## 9. Recommendations

### For Strategy Development:
- **Start with Akshare** - Free, comprehensive, no setup needed
- **Use DuckDB** - Simple, fast, great for analytics
- **Focus on price data first** - Get 1 year of CSI 300 daily OHLCV
- **Add fundamentals next** - P/E, P/B, ROE for all 300 stocks
- **Build sentiment later** - Requires NLP infrastructure

### For Production:
- **Consider Tushare Pro** - More reliable, better SLA (¥600+/year)
- **Consider PostgreSQL** - Better for multi-user, web services
- **Implement caching** - Reduce API calls
- **Set up monitoring** - Data quality alerts
- **Have backup data sources** - Redundancy is critical

---

**Analysis completed by:** Data Analyst (stocks-data-analyst subagent)
**Next action:** Implement database initialization and data collection scripts
