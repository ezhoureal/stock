#!/usr/bin/env python3
"""
Collect ALL A-share stocks from East Money via AKShare

This script fetches all A-share stocks (approximately 5,000+ stocks) from
East Money and stores them in the DuckDB database. Stocks that are also
CSI 300 constituents are marked accordingly.

Usage:
    python collect_all_ashare.py
"""

import json
from pathlib import Path

# Configuration path - try Linux server path first, then local
CONFIG_PATHS = [
    "/home/zireael/trade/stocks/data/config.json",  # Linux server
    Path(__file__).parent / "config.json",  # Local (same directory as script)
]


def load_config():
    """Load configuration from config.json"""
    for config_path in CONFIG_PATHS:
        if Path(config_path).exists():
            with open(config_path) as f:
                config = json.load(f)
                # If database path is on Linux server but we're running locally,
                # adjust to local path
                db_path = config.get("database", {}).get("path", "")
                if db_path.startswith("/home/zireael/") and not Path(db_path).exists():
                    # Use local database path
                    config["database"]["path"] = str(Path(__file__).parent / "stocks.duckdb")
                return config
    raise FileNotFoundError(f"Config file not found in any of: {CONFIG_PATHS}")


def main():
    print("=" * 80)
    print("Collecting ALL A-Share Stocks from East Money")
    print("=" * 80)
    print()

    try:
        import duckdb
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        print("\nInstall required packages:")
        print("  pip install duckdb pandas akshare")
        return False

    config = load_config()
    db_path = config["database"]["path"]

    print(f"Database path: {db_path}")
    print()

    # Connect to database
    conn = duckdb.connect(db_path)

    try:
        import akshare as ak

        print("✓ Akshare imported")
    except ImportError:
        print("✗ Akshare not installed")
        print("\nInstall with:")
        print("  pip install akshare")
        conn.close()
        return False

    # Get existing CSI 300 stocks to mark them properly
    print("\nFetching existing CSI 300 stocks from database...")
    try:
        csi300_stocks = conn.execute(
            "SELECT stock_id FROM stocks WHERE is_csi300 = TRUE"
        ).fetchall()
        csi300_set = {row[0] for row in csi300_stocks}
        print(f"✓ Found {len(csi300_set)} CSI 300 stocks in database")
    except Exception as e:
        print(f"⚠ Could not fetch CSI 300 stocks: {e}")
        csi300_set = set()

    # Fetch all A-share stocks from East Money
    print("\nFetching ALL A-share stocks from East Money via AKShare...")
    print("  (This may take 10-30 seconds depending on network speed)")
    try:
        df_all = ak.stock_zh_a_spot_em()
        print(f"✓ Retrieved {len(df_all)} stocks")

        # Display columns for debugging
        print(f"\nColumns returned: {list(df_all.columns)}")

        # Display sample
        print("\nSample data:")
        print(df_all.head(10).to_string())

    except Exception as e:
        print(f"✗ Error fetching A-share stocks: {e}")
        conn.close()
        return False

    # Process data
    print("\nProcessing data...")
    records = []
    skipped = 0

    # Column names from East Money (ak.stock_zh_a_spot_em):
    # 序号, 代码, 名称, 最新价, 涨跌幅, 涨跌额, 成交量, 成交额, 振幅, 最高, 最低, 今开, 昨收,
    # 换手率, 市盈率-动态, 市净率, 总市值, 流通市值, 涨速, 5分钟涨跌, 60日涨跌幅, 年初至今涨跌幅
    for _, row in df_all.iterrows():
        stock_code = str(row.get("代码", "")).strip()
        stock_name = str(row.get("名称", "")).strip()

        # Skip invalid or non-stock entries
        if not stock_code or not stock_name:
            skipped += 1
            continue

        # Skip special entries like indices, bonds, funds
        # A-share stock codes are 6 digits starting with 0, 3, 6, or 688 (STAR Market)
        if not stock_code.isdigit() or len(stock_code) != 6:
            skipped += 1
            continue

        # Skip delisted stocks or special treatment stocks if needed
        # (keeping ST stocks as they are still tradeable)

        # Determine code formats
        if stock_code.startswith("6"):
            ts_code = f"{stock_code}.SH"
            akshare_code = stock_code
            baostock_code = f"sh.{stock_code}"
        else:
            # 0xxx, 3xxx (Shenzhen main board and ChiNext)
            ts_code = f"{stock_code}.SZ"
            akshare_code = stock_code
            baostock_code = f"sz.{stock_code}"

        # Check if this stock is in CSI 300
        is_csi300 = stock_code in csi300_set

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
                "is_csi300": is_csi300,
                "is_active": True,
            }
        )

    print(f"✓ Processed {len(records)} valid stocks")
    if skipped > 0:
        print(f"  Skipped {skipped} invalid/non-stock entries")

    # Insert into database
    print("\nInserting into database...")
    try:
        conn.execute("BEGIN TRANSACTION")

        inserted = 0
        updated = 0

        for record in records:
            # Check if stock already exists
            existing = conn.execute(
                "SELECT is_csi300 FROM stocks WHERE stock_id = ?",
                [record["stock_id"]],
            ).fetchone()

            if existing:
                # Update existing record, preserve CSI 300 status if already set
                new_is_csi300 = existing[0] or record["is_csi300"]
                conn.execute(
                    """
                    UPDATE stocks SET
                        ts_code = ?,
                        akshare_code = ?,
                        baostock_code = ?,
                        name = ?,
                        is_csi300 = ?,
                        is_active = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE stock_id = ?
                """,
                    [
                        record["ts_code"],
                        record["akshare_code"],
                        record["baostock_code"],
                        record["name"],
                        new_is_csi300,
                        record["is_active"],
                        record["stock_id"],
                    ],
                )
                updated += 1
            else:
                # Insert new record
                conn.execute(
                    """
                    INSERT INTO stocks
                    (stock_id, ts_code, akshare_code, baostock_code, name,
                     industry, sector, list_date, is_csi300, is_active, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    [
                        record["stock_id"],
                        record["ts_code"],
                        record["akshare_code"],
                        record["baostock_code"],
                        record["name"],
                        record["industry"],
                        record["sector"],
                        record["list_date"],
                        record["is_csi300"],
                        record["is_active"],
                    ],
                )
                inserted += 1

        conn.execute("COMMIT")
        print(f"✓ Inserted {inserted} new stocks")
        print(f"✓ Updated {updated} existing stocks")
        print(f"✓ Total stocks in database: {len(records)}")

    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"✗ Error inserting data: {e}")
        conn.close()
        return False

    # Verify
    print("\nVerifying data...")
    total_count_result = conn.execute(
        "SELECT COUNT(*) FROM stocks WHERE stock_id != 'SYSTEM'"
    ).fetchone()
    total_count = total_count_result[0] if total_count_result else 0
    csi300_count_result = conn.execute(
        "SELECT COUNT(*) FROM stocks WHERE is_csi300 = TRUE"
    ).fetchone()
    csi300_count = csi300_count_result[0] if csi300_count_result else 0
    non_csi300_count_result = conn.execute(
        "SELECT COUNT(*) FROM stocks WHERE is_csi300 = FALSE AND stock_id != 'SYSTEM'"
    ).fetchone()
    non_csi300_count = non_csi300_count_result[0] if non_csi300_count_result else 0

    print(f"✓ Total stocks in database: {total_count}")
    print(f"✓ CSI 300 stocks: {csi300_count}")
    print(f"✓ Non-CSI 300 stocks: {non_csi300_count}")

    # Show sample of non-CSI 300 stocks
    print("\nSample non-CSI 300 stocks in database:")
    sample = conn.execute("""
        SELECT stock_id, name, ts_code
        FROM stocks
        WHERE is_csi300 = FALSE AND stock_id != 'SYSTEM'
        ORDER BY stock_id
        LIMIT 10
    """).fetchall()

    for row in sample:
        print(f"  {row[0]}: {row[1]} ({row[2]})")

    # Show market distribution
    print("\nMarket distribution:")
    sh_count_result = conn.execute(
        "SELECT COUNT(*) FROM stocks WHERE ts_code LIKE '%.SH' AND stock_id != 'SYSTEM'"
    ).fetchone()
    sh_count = sh_count_result[0] if sh_count_result else 0
    sz_count_result = conn.execute(
        "SELECT COUNT(*) FROM stocks WHERE ts_code LIKE '%.SZ' AND stock_id != 'SYSTEM'"
    ).fetchone()
    sz_count = sz_count_result[0] if sz_count_result else 0
    print(f"  Shanghai (SH): {sh_count}")
    print(f"  Shenzhen (SZ): {sz_count}")

    print()
    print("=" * 80)
    print("A-Share collection complete!")
    print("=" * 80)

    conn.close()
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
