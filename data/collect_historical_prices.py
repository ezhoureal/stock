#!/usr/bin/env python3
"""
Collect historical daily price data for CSI 300 stocks

Usage:
    python collect_historical_prices.py [--years 1]
"""

import json
import sys
import argparse
from datetime import datetime, timedelta

# Load configuration
CONFIG_PATH = "/home/zireael/trade/stocks/data/config.json"

def load_config():
    """Load configuration from config.json"""
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def main():
    parser = argparse.ArgumentParser(description='Collect historical price data for CSI 300 stocks')
    parser.add_argument('--years', type=int, default=1, help='Number of years of historical data')
    args = parser.parse_args()

    print("=" * 80)
    print("Collecting Historical Price Data")
    print("=" * 80)
    print()

    try:
        import duckdb
        import pandas as pd
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        print("\nInstall required packages:")
        print("  ~/.local/bin/pip install duckdb pandas akshare --break-system-packages")
        return False

    config = load_config()
    db_path = config['database']['path']
    primary_source = config['data_collection']['primary_source']
    years = args.years

    print(f"Database path: {db_path}")
    print(f"Data source: {primary_source}")
    print(f"Years of data: {years}")
    print()

    # Connect to database
    conn = duckdb.connect(db_path)

    try:
        import akshare as ak
        print("✓ Akshare imported")
    except ImportError:
        print("✗ Akshare not installed")
        print("\nInstall with:")
        print("  ~/.local/bin/pip install akshare --break-system-packages")
        conn.close()
        return False

    # Get CSI 300 stocks from database
    print("\nFetching CSI 300 stocks from database...")
    stocks = conn.execute("""
        SELECT stock_id, name, akshare_code
        FROM stocks
        WHERE is_csi300 = TRUE
        ORDER BY stock_id
    """).fetchall()

    print(f"✓ Found {len(stocks)} CSI 300 stocks")

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)

    start_date_str = start_date.strftime('%Y%m%d')
    end_date_str = end_date.strftime('%Y%m%d')

    print(f"  Start date: {start_date_str}")
    print(f"  End date: {end_date_str}")
    print()

    # Collect price data for each stock
    print("Collecting price data...")
    total_records = 0
    success_count = 0
    error_stocks = []

    for i, (stock_id, name, akshare_code) in enumerate(stocks, 1):
        print(f"\r  [{i}/{len(stocks)}] Fetching {stock_id} ({name})...", end='', flush=True)

        try:
            # Fetch historical data from Akshare
            df = ak.stock_zh_a_hist(
                symbol=akshare_code,
                period="daily",
                start_date=start_date_str,
                end_date=end_date_str,
                adjust=""  # No adjustment for raw prices
            )

            if df.empty:
                error_stocks.append((stock_id, "No data"))
                continue

            # Process data
            records = []
            for _, row in df.iterrows():
                records.append({
                    'stock_id': stock_id,
                    'trade_date': pd.to_datetime(row['日期']).date(),
                    'open': float(row['开盘']),
                    'high': float(row['最高']),
                    'low': float(row['最低']),
                    'close': float(row['收盘']),
                    'volume': int(row['成交量']),
                    'amount': float(row['成交额']),
                    'pct_chg': float(row['涨跌幅']),
                    'adj_factor': 1.0,
                    'data_source': primary_source
                })

            # Insert into database
            conn.execute("BEGIN TRANSACTION")
            for rec in records:
                conn.execute("""
                    INSERT OR REPLACE INTO daily_prices
                    (stock_id, trade_date, open, high, low, close, volume,
                     amount, pct_chg, adj_factor, data_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    rec['stock_id'], rec['trade_date'], rec['open'], rec['high'],
                    rec['low'], rec['close'], rec['volume'], rec['amount'],
                    rec['pct_chg'], rec['adj_factor'], rec['data_source']
                ])
            conn.execute("COMMIT")

            total_records += len(records)
            success_count += 1

        except Exception as e:
            conn.execute("ROLLBACK")
            error_stocks.append((stock_id, str(e)[:50]))

    print()
    print()
    print(f"✓ Collected {total_records} price records")
    print(f"✓ Successfully fetched: {success_count}/{len(stocks)} stocks")

    if error_stocks:
        print(f"\n⚠ Errors with {len(error_stocks)} stocks:")
        for stock_id, error in error_stocks[:10]:
            print(f"    {stock_id}: {error}")
        if len(error_stocks) > 10:
            print(f"    ... and {len(error_stocks) - 10} more")

    # Verify
    print("\nVerifying data...")
    result = conn.execute("""
        SELECT
            COUNT(DISTINCT stock_id) as stocks,
            COUNT(*) as records,
            MIN(trade_date) as first_date,
            MAX(trade_date) as last_date
        FROM daily_prices
        WHERE data_source = ?
    """, [primary_source]).fetchone()

    print(f"  Unique stocks: {result[0]}")
    print(f"  Total records: {result[1]}")
    print(f"  Date range: {result[2]} to {result[3]}")

    print()
    print("=" * 80)
    print("Historical price collection complete!")
    print("=" * 80)

    conn.close()
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
