#!/usr/bin/env python3
"""
Collect CSI 300 constituent stocks from Akshare

Usage:
    python collect_csi300.py
"""

import json

# Load configuration
CONFIG_PATH = "/home/zireael/trade/stocks/data/config.json"


def load_config():
    """Load configuration from config.json"""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def main():
    print("=" * 80)
    print("Collecting CSI 300 Constituent Stocks")
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
    db_path = config["database"]["path"]
    index_code = config["data_collection"]["csi300_index"]

    print(f"Database path: {db_path}")
    print(f"CSI 300 Index: {index_code}")
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

    # Fetch CSI 300 constituents from Akshare
    print("\nFetching CSI 300 constituents from Akshare...")
    try:
        df_csi300 = ak.index_stock_cons(symbol=index_code)
        print(f"✓ Retrieved {len(df_csi300)} stocks")

        # Display sample
        print("\nSample data:")
        print(df_csi300.head(10).to_string())

    except Exception as e:
        print(f"✗ Error fetching CSI 300: {e}")
        conn.close()
        return False

    # Process data
    print("\nProcessing data...")
    records = []

    for _, row in df_csi300.iterrows():
        # Extract stock ID from various formats
        stock_code = row.get("品种代码", row.get("code", ""))
        stock_name = row.get("品种名称", row.get("name", ""))

        if not stock_code:
            continue

        # Determine code formats
        if stock_code.startswith("6"):
            ts_code = f"{stock_code}.SH"
            akshare_code = stock_code
            baostock_code = f"sh.{stock_code}"
        else:
            ts_code = f"{stock_code}.SZ"
            akshare_code = stock_code
            baostock_code = f"sz.{stock_code}"

        records.append(
            {
                "stock_id": stock_code,
                "ts_code": ts_code,
                "akshare_code": akshare_code,
                "baostock_code": baostock_code,
                "name": stock_name,
                "industry": "",
                "sector": "",
                "list_date": None,
                "is_csi300": True,
                "is_active": True,
            }
        )

    print(f"✓ Processed {len(records)} stocks")

    # Insert into database
    print("\nInserting into database...")
    try:
        # Create DataFrame
        df_stocks = pd.DataFrame(records)

        # Insert using DuckDB
        conn.execute("BEGIN TRANSACTION")

        for _, row in df_stocks.iterrows():
            conn.execute(
                """
                INSERT OR REPLACE INTO stocks
                (stock_id, ts_code, akshare_code, baostock_code, name,
                 industry, sector, list_date, is_csi300, is_active, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                [
                    row["stock_id"],
                    row["ts_code"],
                    row["akshare_code"],
                    row["baostock_code"],
                    row["name"],
                    row["industry"],
                    row["sector"],
                    row["list_date"],
                    row["is_csi300"],
                    row["is_active"],
                ],
            )

        conn.execute("COMMIT")
        print(f"✓ Inserted {len(records)} stocks into database")

    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"✗ Error inserting data: {e}")
        conn.close()
        return False

    # Verify
    print("\nVerifying data...")
    count = conn.execute("SELECT COUNT(*) FROM stocks WHERE is_csi300 = TRUE").fetchone()[0]
    print(f"✓ CSI 300 stocks in database: {count}")

    # Show sample
    print("\nSample stocks in database:")
    sample = conn.execute("""
        SELECT stock_id, name, ts_code, baostock_code
        FROM stocks
        WHERE is_csi300 = TRUE
        LIMIT 10
    """).fetchall()

    for row in sample:
        print(f"  {row[0]}: {row[1]} ({row[2]}, {row[3]})")

    print()
    print("=" * 80)
    print("CSI 300 collection complete!")
    print("=" * 80)

    conn.close()
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
