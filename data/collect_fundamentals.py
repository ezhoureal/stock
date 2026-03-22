#!/usr/bin/env python3
"""
Collect fundamental data (P/E, P/B, ROE, etc.) for A-share stocks using AKShare

Includes sector-specific data for more accurate valuation comparisons.

Usage:
    python collect_fundamentals.py --universe csi300
    python collect_fundamentals.py --universe all --batch-size 50
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Configuration paths - try Linux server first, then local
CONFIG_PATHS = [
    "/home/zireael/trade/stocks/data/config.json",
    Path(__file__).parent / "config.json",
]


def load_config():
    """Load configuration from config.json"""
    for config_path in CONFIG_PATHS:
        if Path(config_path).exists():
            with open(config_path) as f:
                return json.load(f)
    raise FileNotFoundError(f"Config file not found. Searched: {CONFIG_PATHS}")


def setup_logging(log_level: str = "INFO"):
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def fetch_sector_classifications(ak: object, logger: logging.Logger) -> dict[str, str]:
    """
    Fetch Shenwan (申万) sector classifications for all A-share stocks.

    Uses AKShare's stock_industry_clf_hist_sw to get the latest industry
    classification for each stock.

    Args:
        ak: AKShare module
        logger: Logger instance

    Returns:
        Dictionary mapping stock_id to sw_sector_code
    """
    try:
        logger.info("Fetching sector classifications from Shenwan (申万)...")
        df = ak.stock_industry_clf_hist_sw()  # type: ignore[attr-defined]

        if df is None or df.empty:
            logger.warning("No sector classification data returned")
            return {}

        # Get the most recent classification for each stock
        # Sort by symbol and start_date, then take the last entry for each stock
        df = df.sort_values(["symbol", "start_date"])
        latest_classifications = df.drop_duplicates(subset=["symbol"], keep="last")

        # Create mapping: stock_code -> industry_code
        sector_map = dict(
            zip(
                latest_classifications["symbol"],
                latest_classifications["industry_code"],
                strict=False,
            )
        )

        logger.info(f"Loaded sector classifications for {len(sector_map)} stocks")
        return sector_map

    except Exception as e:
        logger.error(f"Error fetching sector classifications: {e}")
        return {}


def fetch_sw_sector_metrics(
    ak: object, sector_map: dict[str, str], logger: logging.Logger
) -> dict[str, dict]:
    """
    Fetch Shenwan (申万) sector-level valuation metrics.

    Retrieves P/E, P/B, and dividend yield from sw_index_first_info (Level 1)
    and maps them to the sector codes used in stock_industry_clf_hist_sw
    by using the sector hierarchy (first 2 digits of level-3 code map to level-1).

    Args:
        ak: AKShare module
        sector_map: Dictionary mapping stock_id to sector_code (from stock_industry_clf_hist_sw)
        logger: Logger instance

    Returns:
        Dictionary mapping sector_code to sector metrics dict
    """
    sector_metrics = {}

    # Build mapping from level-1 prefix to level-3 codes
    # Level-3 codes from stock_industry_clf_hist_sw start with 2 digits that
    # correspond to level-1 sectors (e.g., 62xxxx = Construction/建筑装饰)
    # We need to map: 62xxxx -> 801720 (建筑装饰)

    # First, collect unique level-3 sector codes from stocks
    level3_sectors = set(sector_map.values()) if sector_map else set()
    logger.info(f"Building metrics for {len(level3_sectors)} unique sector codes from stock data")

    # Fetch Level 1 sectors for reference
    level1_metrics = {}
    try:
        logger.info("Fetching Shenwan Level 1 sector metrics for reference...")
        df_l1 = ak.sw_index_first_info()  # type: ignore[attr-defined]
        if df_l1 is not None and not df_l1.empty:
            for _, row in df_l1.iterrows():
                sector_code = str(row["行业代码"]).replace(".SI", "")
                level1_metrics[sector_code] = {
                    "sector_name": row["行业名称"],
                    "pe_ratio": _parse_float(row.get("静态市盈率")),
                    "pb_ratio": _parse_float(row.get("市净率")),
                    "dividend_yield": _parse_float(row.get("静态股息率")),
                }
    except Exception as e:
        logger.warning(f"Error fetching Level 1 sector metrics: {e}")

    # Create mapping from industry group to level-1 metrics
    # Industry groups are roughly:
    # 11-12: Agriculture/Food, 22-23: Mining, 24-27: Manufacturing,
    # 28: Auto, 33-37: Manufacturing, 41-42: Utilities/Transport,
    # 48-49: Finance, 62-64: Construction/RE, 65-66: IT/Comms,
    # 71-72: Environment, 73-75: Media/Comms

    # For each unique level-3 sector, assign appropriate level-1 metrics
    # based on industry category
    sector_name_map = {
        "11": "农林牧渔",
        "12": "食品饮料",
        "13": "纺织服饰",
        "21": "煤炭",
        "22": "石油石化",
        "23": "基础化工",
        "24": "钢铁",
        "25": "有色金属",
        "26": "建筑材料",
        "27": "机械设备",
        "28": "汽车",
        "29": "国防军工",
        "30": "房地产",
        "31": "轻工制造",
        "32": "医药生物",
        "33": "家用电器",
        "34": "商贸零售",
        "35": "社会服务",
        "36": "银行",
        "37": "非银金融",
        "38": "综合",
        "39": "建筑材料",
        "41": "公用事业",
        "42": "交通运输",
        "43": "房地产",
        "44": "建筑装饰",
        "45": "建筑材料",
        "46": "机械设备",
        "47": "国防军工",
        "48": "银行",
        "49": "非银金融",
        "51": "电子",
        "52": "计算机",
        "53": "传媒",
        "54": "通信",
        "61": "综合",
        "62": "建筑装饰",
        "63": "机械设备",
        "64": "电力设备",
        "65": "计算机",
        "66": "传媒",
        "71": "环保",
        "72": "公用事业",
        "73": "通信",
        "74": "传媒",
        "75": "综合",
        "85": "农林牧渔",
    }

    for sector_code in level3_sectors:
        if not sector_code or len(sector_code) < 2:
            continue

        # Get industry prefix (first 2 digits)
        prefix = sector_code[:2]

        # Map to level-1 sector name
        sector_name = sector_name_map.get(prefix, "Unknown")

        # Find matching level-1 metrics
        level1_match = None
        for _l1_code, l1_data in level1_metrics.items():
            if l1_data["sector_name"] == sector_name:
                level1_match = l1_data
                break

        # Default to market averages if no match
        if level1_match:
            sector_metrics[sector_code] = {
                "sector_name": sector_name,
                "sector_level": 3,
                "constituent_count": None,
                "pe_ratio": level1_match["pe_ratio"],
                "pb_ratio": level1_match["pb_ratio"],
                "dividend_yield": level1_match["dividend_yield"],
                "data_source": "sw_index_first_info_mapped",
            }
        else:
            # Use market defaults
            sector_metrics[sector_code] = {
                "sector_name": sector_name,
                "sector_level": 3,
                "constituent_count": None,
                "pe_ratio": 15.0,
                "pb_ratio": 2.0,
                "dividend_yield": 0.02,
                "data_source": "market_default",
            }

    logger.info(f"Total unique sectors loaded: {len(sector_metrics)}")
    return sector_metrics


def _parse_float(val) -> float | None:
    """Parse a value to float, returning None if invalid."""
    if val is None or val == "-" or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def get_stock_universe(conn, universe: str) -> list[tuple[str, str, str]]:
    """
    Get list of stocks to collect fundamentals for.

    Args:
        conn: DuckDB connection
        universe: "csi300" or "all"

    Returns:
        List of (stock_id, name, akshare_code) tuples
    """
    if universe == "csi300":
        query = """
            SELECT stock_id, name, akshare_code
            FROM stocks
            WHERE is_csi300 = TRUE AND is_active = TRUE
            ORDER BY stock_id
        """
    else:
        query = """
            SELECT stock_id, name, akshare_code
            FROM stocks
            WHERE is_active = TRUE
            ORDER BY stock_id
        """

    return conn.execute(query).fetchall()


def fetch_fundamentals_from_spot(
    ak: object,
    stock_codes: list[str],
    logger: logging.Logger,
    sector_map: dict[str, str] | None = None,
) -> dict:
    """
    Fetch fundamental data from real-time spot data (includes P/E, P/B, market cap).

    Uses stock_zh_a_spot_em() which returns all A-share stocks with valuation metrics.

    Args:
        ak: AKShare module
        stock_codes: List of stock codes to fetch (for filtering)
        logger: Logger instance
        sector_map: Optional dictionary mapping stock_id to sector_code

    Returns:
        Dictionary mapping stock_id to fundamental data
    """
    results = {}
    stock_codes_set = set(stock_codes)

    try:
        logger.info("Fetching real-time spot data for all A-shares...")
        df = ak.stock_zh_a_spot_em()  # type: ignore[attr-defined]

        if df is None or df.empty:
            logger.error("No data returned from AKShare")
            return results

        logger.info(f"Retrieved {len(df)} stocks from spot data")

        # Filter to only the stocks we need
        df_filtered = df[df["代码"].isin(stock_codes_set)]
        logger.info(f"Filtered to {len(df_filtered)} stocks in our universe")

        for _, row in df_filtered.iterrows():
            stock_code = row["代码"]

            # Parse numeric values, handling potential string formats
            def parse_float(val):
                if val is None:
                    return None
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None

            # Get sector code if available
            sector_code = sector_map.get(stock_code) if sector_map else None

            results[stock_code] = {
                "report_date": datetime.now().date(),
                "pe": parse_float(row.get("市盈率-动态")),
                "pe_ttm": parse_float(row.get("市盈率-动态")),  # Use dynamic PE as proxy
                "pb": parse_float(row.get("市净率")),
                "ps": None,  # Not available in spot data
                "ps_ttm": None,
                "total_mv": parse_float(row.get("总市值")),
                "circ_mv": parse_float(row.get("流通市值")),
                "roe": None,  # Not available in spot data
                "roa": None,  # Not available in spot data
                "eps": None,  # Not available in spot data
                "bps": None,  # Not available in spot data
                "revenue": None,
                "net_profit": None,
                "gross_margin": None,
                "latest_price": parse_float(row.get("最新价")),
                "change_pct": parse_float(row.get("涨跌幅")),
                "sector_code": sector_code,  # Added sector classification
            }

    except Exception as e:
        logger.error(f"Error fetching spot data: {e}")

    return results


def insert_fundamentals(
    conn,
    fundamentals: dict,
    data_source: str,
    logger: logging.Logger,
) -> int:
    """
    Insert fundamental data into database.

    Args:
        conn: DuckDB connection
        fundamentals: Dictionary of fundamental data
        data_source: Data source identifier
        logger: Logger instance

    Returns:
        Number of records inserted
    """
    inserted = 0

    # Get the max ID to generate new IDs
    try:
        max_id_result = conn.execute("SELECT COALESCE(MAX(id), 0) FROM fundamentals").fetchone()
        next_id = max_id_result[0] + 1 if max_id_result else 1
    except Exception:
        next_id = 1

    for stock_id, data in fundamentals.items():
        try:
            # Handle date conversion
            report_date = data.get("report_date")
            if isinstance(report_date, str):
                report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
            elif report_date is None:
                report_date = datetime.now().date()

            # Use DELETE + INSERT pattern to avoid conflict issues
            conn.execute(
                "DELETE FROM fundamentals WHERE stock_id = ? AND report_date = ?",
                [stock_id, report_date],
            )

            # Update the stock's sector in the stocks table
            sector_code = data.get("sector_code")
            if sector_code:
                try:
                    conn.execute(
                        "UPDATE stocks SET sector = ? WHERE stock_id = ?",
                        [sector_code, stock_id],
                    )
                except Exception:
                    pass  # Ignore errors for sector update

            conn.execute(
                """
                INSERT INTO fundamentals
                (id, stock_id, report_date, pe, pe_ttm, pb, ps, ps_ttm,
                 total_mv, circ_mv, roe, roa, gross_margin,
                 revenue, net_profit, eps, bps, data_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    next_id,
                    stock_id,
                    report_date,
                    data.get("pe"),
                    data.get("pe_ttm"),
                    data.get("pb"),
                    data.get("ps"),
                    data.get("ps_ttm"),
                    data.get("total_mv"),
                    data.get("circ_mv"),
                    data.get("roe"),
                    data.get("roa"),
                    data.get("gross_margin"),
                    data.get("revenue"),
                    data.get("net_profit"),
                    data.get("eps"),
                    data.get("bps"),
                    data_source,
                ],
            )
            next_id += 1
            inserted += 1

        except Exception as e:
            logger.warning(f"Error inserting data for {stock_id}: {e}")
            continue

    logger.info(f"Successfully inserted {inserted} records")
    return inserted


def insert_sector_metrics(
    conn,
    sector_metrics: dict[str, dict],
    data_source: str,
    logger: logging.Logger,
) -> int:
    """
    Insert sector metrics into database.

    Args:
        conn: DuckDB connection
        sector_metrics: Dictionary of sector metrics from fetch_sw_sector_metrics
        data_source: Data source identifier
        logger: Logger instance

    Returns:
        Number of records inserted/updated
    """
    inserted = 0
    report_date = datetime.now().date()

    for sector_code, metrics in sector_metrics.items():
        try:
            # Check if sector exists
            existing = conn.execute(
                "SELECT id FROM sectors WHERE sector_code = ?", [sector_code]
            ).fetchone()

            if existing:
                # Update existing sector
                conn.execute(
                    """
                    UPDATE sectors SET
                        sector_name = ?,
                        sector_level = ?,
                        parent_code = ?,
                        constituent_count = ?,
                        pe_ratio = ?,
                        pb_ratio = ?,
                        dividend_yield = ?,
                        avg_market_cap = ?,
                        report_date = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE sector_code = ?
                """,
                    [
                        metrics.get("sector_name"),
                        metrics.get("sector_level"),
                        None,  # parent_code - could be derived for L2/L3
                        metrics.get("constituent_count"),
                        metrics.get("pe_ratio"),
                        metrics.get("pb_ratio"),
                        metrics.get("dividend_yield"),
                        None,  # avg_market_cap - not available from sw_index_info
                        report_date,
                        sector_code,
                    ],
                )
            else:
                # Insert new sector - get next ID
                max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM sectors").fetchone()[0]
                next_id = max_id + 1

                conn.execute(
                    """
                    INSERT INTO sectors
                    (id, sector_code, sector_name, sector_level, parent_code,
                     constituent_count, pe_ratio, pb_ratio, dividend_yield, avg_market_cap,
                     report_date, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                    [
                        next_id,
                        sector_code,
                        metrics.get("sector_name"),
                        metrics.get("sector_level"),
                        None,  # parent_code
                        metrics.get("constituent_count"),
                        metrics.get("pe_ratio"),
                        metrics.get("pb_ratio"),
                        metrics.get("dividend_yield"),
                        None,  # avg_market_cap
                        report_date,
                    ],
                )
            inserted += 1

        except Exception as e:
            logger.warning(f"Error inserting sector {sector_code}: {e}")
            continue

    logger.info(f"Successfully inserted/updated {inserted} sector records")
    return inserted


def update_stock_sectors(
    conn,
    sector_map: dict[str, str],
    logger: logging.Logger,
) -> int:
    """
    Update stock table with sector classifications.

    Args:
        conn: DuckDB connection
        sector_map: Dictionary mapping stock_id to sector_code
        logger: Logger instance

    Returns:
        Number of stocks updated
    """
    updated = 0

    for stock_id, sector_code in sector_map.items():
        try:
            conn.execute(
                """
                UPDATE stocks
                SET sector = ?, updated_at = CURRENT_TIMESTAMP
                WHERE stock_id = ?
            """,
                [sector_code, stock_id],
            )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                updated += 1
        except Exception as e:
            logger.debug(f"Error updating sector for {stock_id}: {e}")
            continue

    logger.info(f"Updated sector classification for {updated} stocks")
    return updated


def main():
    parser = argparse.ArgumentParser(
        description="Collect fundamental data for A-share stocks with sector classification"
    )
    parser.add_argument(
        "--universe",
        choices=["csi300", "all"],
        default="csi300",
        help="Stock universe: csi300 or all (default: csi300)",
    )
    parser.add_argument(
        "--skip-sectors",
        action="store_true",
        help="Skip sector data collection",
    )
    args = parser.parse_args()

    # Setup logging
    config = load_config()
    log_level = config.get("logging", {}).get("log_level", "INFO")
    logger = setup_logging(log_level)

    print("=" * 80)
    print("Collecting Fundamental Data for A-Share Stocks")
    print("=" * 80)
    print()

    # Import dependencies
    try:
        import duckdb
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        print("\nInstall required packages:")
        print("  uv pip install duckdb akshare")
        return False

    try:
        import akshare as ak
    except ImportError:
        logger.error("AKShare not installed")
        print("\nInstall with:")
        print("  uv pip install akshare")
        return False

    # Connect to database - try configured path first, then local fallback
    db_path = config["database"]["path"]
    if not Path(db_path).exists():
        local_db_path = Path(__file__).parent / "stocks.duckdb"
        if local_db_path.exists():
            db_path = str(local_db_path)
            logger.info(f"Using local database: {db_path}")
        else:
            logger.error(f"Database not found at {db_path} or {local_db_path}")
            return False
    logger.info(f"Database path: {db_path}")
    logger.info(f"Universe: {args.universe}")

    conn = duckdb.connect(db_path)

    # Get stock universe
    stocks = get_stock_universe(conn, args.universe)
    logger.info(f"Found {len(stocks)} stocks in universe")

    if not stocks:
        logger.error("No stocks found in database. Run collect_csi300.py first.")
        conn.close()
        return False

    # Fetch sector data if not skipped
    sector_map = {}
    sector_metrics = {}
    if not args.skip_sectors:
        print("Fetching sector classifications and metrics...")
        sector_map = fetch_sector_classifications(ak, logger)
        sector_metrics = fetch_sw_sector_metrics(ak, sector_map, logger)

        # Insert sector metrics into database
        if sector_metrics:
            data_source = config["data_collection"]["primary_source"]
            insert_sector_metrics(conn, sector_metrics, data_source, logger)

    # Collect fundamentals using spot data (gets all A-shares at once)
    start_time = time.time()
    stock_codes = [s[0] for s in stocks]

    logger.info(f"Fetching fundamentals for {len(stock_codes)} stocks...")
    all_fundamentals = fetch_fundamentals_from_spot(ak, stock_codes, logger, sector_map)

    if not all_fundamentals:
        logger.error("No fundamental data collected")
        conn.close()
        return False

    logger.info(f"Collected data for {len(all_fundamentals)} stocks")

    # Insert into database
    data_source = config["data_collection"]["primary_source"]
    inserted = insert_fundamentals(conn, all_fundamentals, data_source, logger)

    # Update stock sector classifications
    if sector_map and not args.skip_sectors:
        update_stock_sectors(conn, sector_map, logger)

    elapsed_time = time.time() - start_time
    logger.info(f"Collection completed in {elapsed_time:.2f} seconds")

    # Verify and summarize
    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)

    result = conn.execute(
        """
        SELECT
            COUNT(DISTINCT stock_id) as stocks,
            COUNT(*) as records,
            MAX(report_date) as latest_date
        FROM fundamentals
        WHERE data_source = ?
    """,
        [data_source],
    ).fetchone()

    print(f"  Stocks with fundamentals: {result[0] if result else 0}")
    print(f"  Total records: {result[1] if result else 0}")
    print(f"  Latest report date: {result[2] if result else 'N/A'}")
    print(f"  Records inserted this run: {inserted}")

    # Show sector summary if sectors were collected
    if not args.skip_sectors and sector_metrics:
        print()
        print("  Sector Data:")
        sector_count_result = conn.execute("SELECT COUNT(*) FROM sectors").fetchone()
        sector_count = sector_count_result[0] if sector_count_result else 0
        stocks_with_sector_result = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM stocks WHERE sector IS NOT NULL"
        ).fetchone()
        stocks_with_sector = stocks_with_sector_result[0] if stocks_with_sector_result else 0
        print(f"    Total sectors in database: {sector_count}")
        print(f"    Stocks with sector classification: {stocks_with_sector}")
    print()

    # Show sample data with sector info
    print("Sample fundamental data:")
    sample = conn.execute("""
        SELECT f.stock_id, s.name, s.sector, f.pe, f.pb, f.total_mv, f.report_date
        FROM fundamentals f
        JOIN stocks s ON f.stock_id = s.stock_id
        ORDER BY f.report_date DESC
        LIMIT 10
    """).fetchall()

    print(
        f"  {'Stock ID':<10} {'Name':<12} {'Sector':<10} {'P/E':>8} {'P/B':>8} {'Market Cap':>12}"
    )
    print("  " + "-" * 72)
    for row in sample:
        sector_str = str(row[2])[:8] if row[2] else "N/A"
        pe_str = f"{row[3]:.2f}" if row[3] else "N/A"
        pb_str = f"{row[4]:.2f}" if row[4] else "N/A"
        mv_str = f"{row[5]:.2f}" if row[5] else "N/A"
        print(f"  {row[0]:<10} {row[1]:<12} {sector_str:<10} {pe_str:>8} {pb_str:>8} {mv_str:>12}")

    # Show sample sector metrics
    if not args.skip_sectors and sector_metrics:
        print()
        print("Sample sector metrics (Shenwan Level 1):")
        sector_sample = conn.execute("""
            SELECT sector_code, sector_name, pe_ratio, pb_ratio, constituent_count
            FROM sectors
            WHERE sector_level = 1
            ORDER BY sector_code
            LIMIT 10
        """).fetchall()

        print(f"  {'Sector Code':<12} {'Sector Name':<16} {'P/E':>8} {'P/B':>8} {'Stocks':>8}")
        print("  " + "-" * 60)
        for row in sector_sample:
            pe_str = f"{row[2]:.2f}" if row[2] else "N/A"
            pb_str = f"{row[3]:.2f}" if row[3] else "N/A"
            count_str = str(row[4]) if row[4] else "N/A"
            print(f"  {row[0]:<12} {row[1]:<16} {pe_str:>8} {pb_str:>8} {count_str:>8}")

    print()
    print("=" * 80)
    print("Fundamental data collection complete!")
    print("=" * 80)

    conn.close()
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
