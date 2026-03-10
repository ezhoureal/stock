#!/usr/bin/env python3
"""
Initialize DuckDB database for Chinese Stock Trading System

Usage:
    python init_db.py
"""

import json
import os
from datetime import datetime

# Load configuration
CONFIG_PATH = "/home/zireael/trade/stocks/data/config.json"

def load_config():
    """Load configuration from config.json"""
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def main():
    print("=" * 80)
    print("Initializing Chinese Stock Trading System Database")
    print("=" * 80)
    print()

    config = load_config()
    db_path = config['database']['path']

    print(f"Database path: {db_path}")
    print()

    try:
        import duckdb
        print("✓ DuckDB imported successfully")
    except ImportError:
        print("✗ DuckDB not installed. Install with:")
        print("  pip install duckdb --break-system-packages")
        return False

    # Connect to database (will create if not exists)
    conn = duckdb.connect(db_path)
    print(f"✓ Connected to database: {db_path}")
    print()

    # Define SQL schema
    schemas = {
        'stocks': """
            CREATE TABLE IF NOT EXISTS stocks (
                stock_id VARCHAR(20) PRIMARY KEY,
                ts_code VARCHAR(20),
                akshare_code VARCHAR(20),
                baostock_code VARCHAR(20),
                name VARCHAR(100),
                industry VARCHAR(100),
                sector VARCHAR(100),
                list_date DATE,
                is_csi300 BOOLEAN,
                is_active BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """,

        'daily_prices': """
            CREATE TABLE IF NOT EXISTS daily_prices (
                id INTEGER PRIMARY KEY,
                stock_id VARCHAR(20),
                trade_date DATE,
                open DECIMAL(15,4),
                high DECIMAL(15,4),
                low DECIMAL(15,4),
                close DECIMAL(15,4),
                volume BIGINT,
                amount DECIMAL(20,2),
                pct_chg DECIMAL(10,4),
                adj_factor DECIMAL(15,8),
                data_source VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(stock_id, trade_date, data_source)
            );
        """,

        'fundamentals': """
            CREATE TABLE IF NOT EXISTS fundamentals (
                id INTEGER PRIMARY KEY,
                stock_id VARCHAR(20),
                report_date DATE,
                end_date DATE,
                pe DECIMAL(15,4),
                pe_ttm DECIMAL(15,4),
                pb DECIMAL(15,4),
                ps DECIMAL(15,4),
                ps_ttm DECIMAL(15,4),
                total_mv DECIMAL(20,2),
                circ_mv DECIMAL(20,2),
                roe DECIMAL(10,4),
                roa DECIMAL(10,4),
                gross_margin DECIMAL(10,4),
                revenue DECIMAL(20,2),
                net_profit DECIMAL(20,2),
                eps DECIMAL(15,4),
                bps DECIMAL(15,4),
                data_source VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(stock_id, report_date)
            );
        """,

        'sentiment_scores': """
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
            );
        """,

        'news_raw': """
            CREATE TABLE IF NOT EXISTS news_raw (
                id INTEGER PRIMARY KEY,
                stock_id VARCHAR(20),
                title TEXT,
                content TEXT,
                summary TEXT,
                source VARCHAR(100),
                url TEXT,
                publish_time TIMESTAMP,
                author VARCHAR(100),
                sentiment_raw DECIMAL(5,4),
                keywords TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """,

        'csi300_history': """
            CREATE TABLE IF NOT EXISTS csi300_history (
                id INTEGER PRIMARY KEY,
                stock_id VARCHAR(20),
                entry_date DATE,
                exit_date DATE,
                weight DECIMAL(8,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """,
    }

    indexes = {
        'idx_stocks_csi300': "CREATE INDEX IF NOT EXISTS idx_stocks_csi300 ON stocks(is_csi300);",
        'idx_stocks_active': "CREATE INDEX IF NOT EXISTS idx_stocks_active ON stocks(is_active);",
        'idx_daily_prices_stock_date': "CREATE INDEX IF NOT EXISTS idx_daily_prices_stock_date ON daily_prices(stock_id, trade_date);",
        'idx_daily_prices_date': "CREATE INDEX IF NOT EXISTS idx_daily_prices_date ON daily_prices(trade_date);",
        'idx_fundamentals_stock_date': "CREATE INDEX IF NOT EXISTS idx_fundamentals_stock_date ON fundamentals(stock_id, report_date);",
        'idx_sentiment_stock_time': "CREATE INDEX IF NOT EXISTS idx_sentiment_stock_time ON sentiment_scores(stock_id, timestamp);",
        'idx_sentiment_date': "CREATE INDEX IF NOT EXISTS idx_sentiment_date ON sentiment_scores(sentiment_date);",
        'idx_news_stock': "CREATE INDEX IF NOT EXISTS idx_news_stock ON news_raw(stock_id);",
        'idx_news_time': "CREATE INDEX IF NOT EXISTS idx_news_time ON news_raw(publish_time);",
        'idx_news_source': "CREATE INDEX IF NOT EXISTS idx_news_source ON news_raw(source);",
        'idx_csi300_stock': "CREATE INDEX IF NOT EXISTS idx_csi300_stock ON csi300_history(stock_id);",
        'idx_csi300_date': "CREATE INDEX IF NOT EXISTS idx_csi300_date ON csi300_history(entry_date);",
    }

    # Create tables
    print("Creating tables...")
    for table_name, schema_sql in schemas.items():
        try:
            conn.execute(schema_sql)
            print(f"  ✓ Table '{table_name}' created")
        except Exception as e:
            print(f"  ✗ Error creating table '{table_name}': {e}")
            return False

    print()

    # Create indexes
    print("Creating indexes...")
    for idx_name, idx_sql in indexes.items():
        try:
            conn.execute(idx_sql)
            print(f"  ✓ Index '{idx_name}' created")
        except Exception as e:
            print(f"  ✗ Error creating index '{idx_name}': {e}")

    print()

    # Verify tables
    print("Verifying database structure...")
    tables = conn.execute("SHOW TABLES").fetchall()
    print(f"  ✓ Found {len(tables)} tables:")
    for table in tables:
        print(f"      - {table[0]}")

    print()

    # Insert metadata
    try:
        conn.execute("""
            INSERT OR REPLACE INTO stocks (stock_id, name, is_active, is_csi300)
            VALUES ('SYSTEM', 'System Metadata', TRUE, FALSE)
        """)
        print("✓ System metadata initialized")
    except Exception as e:
        print(f"⚠ Could not insert system metadata: {e}")

    print()
    print("=" * 80)
    print("Database initialization complete!")
    print("=" * 80)
    print()
    print(f"Database location: {db_path}")
    print()
    print("Next steps:")
    print("  1. Run collection scripts to populate data:")
    print("     python collect_csi300.py")
    print("     python collect_historical_prices.py")
    print("  2. Export to Parquet for analysis:")
    print("     python export_data.py")

    conn.close()
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
