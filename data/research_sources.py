#!/usr/bin/env python3
"""
Research script to evaluate Chinese stock data sources.
Tests Tushare, akshare, and baostock for:
- Data availability
- API ease of use
- Cost/access requirements
- Data quality
"""

import sys
from datetime import datetime, timedelta
import traceback

print("=" * 80)
print("Chinese Stock Data Sources Research")
print("=" * 80)
print()

# Test results storage
results = {
    'tushare': {'available': False, 'notes': []},
    'akshare': {'available': False, 'notes': []},
    'baostock': {'available': False, 'notes': []}
}

# ============================================
# 1. TUSHARE TEST
# ============================================
print("\n" + "=" * 80)
print("1. TESTING TUSHARE")
print("=" * 80)

try:
    import tushare as ts
    results['tushare']['available'] = True
    print("✓ tushare installed successfully")

    # Check if API token is available
    import os
    ts_token = os.environ.get('TUSHARE_TOKEN')
    if ts_token:
        print(f"✓ TUSHARE_TOKEN found in environment")
        ts.set_token(ts_token)
        pro = ts.pro_api()

        # Test basic data fetch
        try:
            df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name')
            print(f"✓ Retrieved {len(df)} listed stocks from Tushare")
            print(f"  Sample: {df.head(3).to_dict('records')}")
        except Exception as e:
            print(f"✗ API test failed: {e}")
            results['tushare']['notes'].append(f"API error: {e}")
    else:
        print("⚠ TUSHARE_TOKEN not set - requires free registration at tushare.pro")
        results['tushare']['notes'].append("Requires API token (free tier available)")

    # Documentation notes
    print("\nTushare Key Features:")
    print("- Official interface to China stock market data")
    print("- Comprehensive coverage: A-shares, funds, futures, options")
    print("- Free tier: 120 requests/minute, limited data access")
    print("- Pro tier: 2000 requests/minute, full access (¥600-2000/year)")
    print("- Python pandas DataFrame output")
    results['tushare']['notes'].append("Free tier: limited historical data")
    results['tushare']['notes'].append("Pro tier recommended for backtesting")

except ImportError as e:
    print(f"✗ tushare not installed: pip install tushare")
    results['tushare']['notes'].append("Not installed")
except Exception as e:
    print(f"✗ Tushare test error: {e}")
    traceback.print_exc()

# ============================================
# 2. AKSHARE TEST
# ============================================
print("\n" + "=" * 80)
print("2. TESTING AKSHARE")
print("=" * 80)

try:
    import akshare as ak
    results['akshare']['available'] = True
    print("✓ akshare installed successfully")

    # Test basic data fetch (no API token required)
    try:
        # Get stock list
        df = ak.stock_info_a_code_name()
        print(f"✓ Retrieved {len(df)} A-share stocks from akshare")
        print(f"  Sample: {df.head(3).to_dict('records')}")

        # Test CSI 300
        try:
            df_csi300 = ak.index_stock_cons(index="000300")
            print(f"✓ Retrieved {len(df_csi300)} CSI 300 constituents")
            print(f"  Sample: {df_csi300.head(3).to_dict('records')}")
            results['akshare']['csi300_test'] = True
        except Exception as e:
            print(f"⚠ CSI 300 fetch failed: {e}")

        # Test historical price
        try:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
            end_date = datetime.now().strftime('%Y%m%d')
            df_price = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date=start_date, end_date=end_date)
            print(f"✓ Retrieved {len(df_price)} days of price data for 000001")
            print(f"  Columns: {list(df_price.columns)}")
            results['akshare']['price_test'] = True
        except Exception as e:
            print(f"⚠ Price data fetch failed: {e}")

    except Exception as e:
        print(f"✗ Basic data fetch failed: {e}")
        results['akshare']['notes'].append(f"Data fetch error: {e}")

    # Documentation notes
    print("\nAkshare Key Features:")
    print("- 100% free and open source")
    print("- No API token required")
    print("- Scrapes public data sources (Sina, Eastmoney, etc.)")
    print("- Comprehensive: stocks, funds, futures, macro, options")
    print("- Active community, frequent updates")
    print("- Potential limitations: scraping may be rate-limited or blocked")
    results['akshare']['notes'].append("100% free, no API token needed")
    results['akshare']['notes'].append("Scrapes public sources - potential stability issues")
    results['akshare']['notes'].append("Good for research and prototyping")

except ImportError as e:
    print(f"✗ akshare not installed: pip install akshare")
    results['akshare']['notes'].append("Not installed")
except Exception as e:
    print(f"✗ Akshare test error: {e}")
    traceback.print_exc()

# ============================================
# 3. BAOSTOCK TEST
# ============================================
print("\n" + "=" * 80)
print("3. TESTING BAOSTOCK")
print("=" * 80)

try:
    import baostock as bs
    results['baostock']['available'] = True
    print("✓ baostock installed successfully")

    # Test connection
    lg = bs.login()
    print(f"Login response: {lg.error_msg}")

    if lg.error_code == '0':
        print("✓ Connected to baostock server")

        # Test stock list
        try:
            rs = bs.query_all_stock(day=datetime.now().strftime('%Y-%m-%d'))
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            print(f"✓ Retrieved {len(data_list)} stocks from baostock")
        except Exception as e:
            print(f"✗ Stock list fetch failed: {e}")

        # Test historical price
        try:
            rs = bs.query_history_k_data_plus("sh.600000",
                "date,code,open,high,low,close,volume,amount",
                start_date='2025-01-01', end_date=datetime.now().strftime('%Y-%m-%d'),
                frequency="d", adjustflag="3")
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            print(f"✓ Retrieved {len(data_list)} days of price data for sh.600000")
            print(f"  Sample: {data_list[:3]}")
            results['baostock']['price_test'] = True
        except Exception as e:
            print(f"✗ Price data fetch failed: {e}")

        bs.logout()
    else:
        print(f"✗ Login failed: {lg.error_msg}")
        results['baostock']['notes'].append(f"Login error: {lg.error_msg}")

    # Documentation notes
    print("\nBaostock Key Features:")
    print("- Free,证券级金融数据")
    print("- No API token required")
    print("- Focus on A-shares and index data")
    print("- Clean, structured data format")
    print("- Less comprehensive than akshare but more stable")
    print("- Good for backtesting with historical data")
    results['baostock']['notes'].append("100% free, no API token needed")
    results['baostock']['notes'].append("More stable than scraping-based solutions")
    results['baostock']['notes'].append("Focused on A-shares (good for our use case)")

except ImportError as e:
    print(f"✗ baostock not installed: pip install baostock")
    results['baostock']['notes'].append("Not installed")
except Exception as e:
    print(f"✗ Baostock test error: {e}")
    traceback.print_exc()

# ============================================
# SUMMARY
# ============================================
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

print("\nData Source Availability:")
for source, data in results.items():
    status = "✓ AVAILABLE" if data['available'] else "✗ NOT INSTALLED"
    print(f"  {source.upper():12} {status}")
    for note in data['notes']:
        print(f"      - {note}")

print("\n\nRecommendation for Chinese Stock Sentiment Trading System:")
print("  PRIMARY:   Akshare (free, comprehensive, no token needed)")
print("  BACKUP:    Baostock (stable, good A-share coverage)")
print("  PRODUCTION: Tushare Pro (reliable, but requires paid tier for full access)")
