#!/usr/bin/env python3
"""
Collect historical daily price data from Baostock

This is a backup data source when Akshare has issues.
Baostock has a stable API (not scraping-based) and good A-share coverage.
"""

import json
from datetime import datetime, timedelta

# Load configuration
CONFIG_PATH = "/home/zireael/trade/stocks/data/config.json"


def load_config():
    """Load configuration from config.json"""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def main():
    print("=" * 80)
    print("Collecting Historical Price Data (Baostock Backup)")
    print("=" * 80)
    print()

    try:
        import baostock as bs
        import duckdb
        import pandas as pd
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        print("\nInstall required packages:")
        print("  ~/.local/bin/pip install baostock duckdb pandas --break-system-packages")
        return False

    config = load_config()
    db_path = config["database"]["path"]
    years = 1  # Default to 1 year

    # Connect to Baostock
    print(f"Database path: {db_path}")
    print(f"Years of data: {years}")
    print()

    bs.login()
    print("✓ Connected to Baostock")

    # Get CSI 300 stocks from database
    conn = duckdb.connect(db_path)

    stocks = conn.execute("""
        SELECT stock_id, baostock_code
        FROM stocks
        WHERE is_csi300 = TRUE
        """).fetchall()

    if not stocks:
        print("✗ No CSI 300 stocks found in database")
        print("\nPlease run collect_csi300.py first to populate stock list")
        conn.close()
        return False

    print(f"✓ Found {len(stocks)} CSI 300 stocks in database")

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)

    print(f"\nDate range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print()

    # Collect price data
    print("\nCollecting price data...")
    total_records = 0
    success_count = 0
    error_count = 0

    for i, (stock_id, baostock_code) in enumerate(stocks, 1):
        print(
            f"\r  [{i}/{len(stocks)}] Fetching {stock_id} ({baostock_code})...", end="", flush=True
        )

        try:
            rs = bs.query_history_k_data_plus(
                code=baostock_code,
                fields="date,code,open,high,low,close",
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="3",
                adjtype="",
                security="stock",
            )

            while rs.error_code == "0" and rs.next():
                row = rs.get_row_data()
                date_str = row.get("date", "")
                open_price = float(row.get("open", 0)) if row.get("open") else None
                high_price = float(row.get("high", 0)) if row.get("high") else None
                low_price = float(row.get("low", 0)) if row.get("low") else None
                close_price = float(row.get("close", 0)) if row.get("close") else None
                volume = int(row.get("volume", 0)) if row.get("volume") else None
                amount = float(row.get("amount", 0)) if row.get("amount") else None
                pct_chg = float(row.get("pctChg", 0)) if row.get("pctChg") else None

                if date_str and close_price:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO daily_prices
                        (stock_id, trade_date, open, high, low, close, volume, amount, pct_chg, data_source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        [
                            stock_id,
                            date_str,
                            open_price,
                            high_price,
                            low_price,
                            close_price,
                            volume,
                            amount,
                            pct_chg,
                            "baostock",
                        ],
                    )
                    total_records += 1

            if rs.error_code != "0":
                error_msg = f"{rs.error_code}: {rs.error_msg}"
                print(f"  ✗ Error: {error_msg}")
                error_count += 1
            else:
                success_count += 1

        except Exception as e:
            print(f"  ✗ Exception for {stock_id}: {e}")
            error_count += 1

        print()
        print("\nCollection summary:")
        print(f"  Total records: {total_records}")
        print(f"  Success: {success_count}/{len(stocks)}")
        print(f"  Errors: {error_count}/{len(stocks)}")

        if total_records > 0:
            print(f"\n✓ Successfully collected {total_records} price records")
        else:
            print("\n✗ No price data collected")

        # Verify
        print("\nVerifying data...")
        count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE data_source = 'baostock'"
        ).fetchone()[0]
        print(f"✓ Baostock price records in database: {count}")

        # Disconnect
        bs.logout()
        conn.close()

        print()
        print("=" * 80)
        print("Baostock price collection complete!")
        print("=" * 80)

        return total_records > 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
