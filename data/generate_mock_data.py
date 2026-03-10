#!/usr/bin/env python3
"""
Simple mock data generator for backtesting testing

Creates simulated historical price data when API collection is blocked.
This allows strategy testing without waiting for data issues to resolve.
"""

import random
import duckdb
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

DB_PATH = "/home/zireael/trade/stocks/data/stocks.duckdb"

def generate_random_walk(start_price: float, days: int, volatility: float = 0.02) -> list[float]:
    """Generate random walk price data"""
    prices = [start_price]
    returns = np.random.normal(0, volatility, days)
    
    for i in range(1, days):
        daily_return = returns[i]
        new_price = prices[-1] * (1 + daily_return)
        prices.append(new_price)
    
    return prices

def generate_mock_data():
    """Generate mock price data for backtesting"""
    print("Generating mock historical price data...")
    
    conn = duckdb.connect(DB_PATH)
    
    # Get CSI 300 stocks
    stocks = conn.execute("""
        SELECT stock_id, ts_code, name
        FROM stocks
        WHERE is_csi300 = TRUE
    """).fetchall()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    total_records = 0
    stock_list = []
    
    for stock_id, ts_code, name in stocks[:10]:  # Just do first 10 for testing
        print(f"Generating data for {stock_id} ({name})...", end='', flush=True)
        
        # Generate random price walk
        start_price = random.uniform(10, 100)
        prices = generate_random_walk(start_price, 365)
        
        for day, price in enumerate(prices, 1):
            open_price = price * random.uniform(0.995, 1.005)
            high_price = price * random.uniform(1.005, 1.015)
            low_price = price * random.uniform(0.985, 0.995)
            close_price = price * random.uniform(0.995, 1.005)
            volume = int(random.uniform(1000000, 10000000))
            amount = close_price * volume
            
            trade_date = start_date + timedelta(days=day)
            
            # Insert
            try:
                conn.execute("""
                    INSERT INTO daily_prices
                    (stock_id, trade_date, open, high, low, close, volume, amount, pct_chg, data_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 'mock')
                """, [
                    stock_id, trade_date, open_price, high_price, low_price, 
                    close_price, volume, amount, 'mock'
                ])
                total_records += 1
            except Exception as e:
                print(f"  ✗ Error: {e}")
    
        stock_list.append({
            'stock_id': stock_id,
            'name': name,
            'records': 365
        })
    
    print(f"\nGenerated {total_records} price records for {len(stock_list)} stocks")
    print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Generate some mock fundamentals
    print("\nGenerating mock fundamentals...")
    fundamental_records = 0
    
    for stock_id, ts_code, name in stocks:
        pe = random.uniform(5, 50)
        pb = random.uniform(0.8, 8)
        roe = random.uniform(-10, 30)
        
        try:
            conn.execute("""
                INSERT INTO fundamentals
                (stock_id, report_date, pe, pb, roe, revenue, net_profit, eps, bps, dividend_yield)
                VALUES (?, CURRENT_DATE, ?, ?, ?, ?, 1000000000, 50000000, ?, 10.0, 3.0)
            """, [
                stock_id, pe, pb, roe
            ])
            fundamental_records += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print(f"Generated {fundamental_records} fundamental records")
    
    # Verify
    price_count = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    fundamental_count = conn.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]
    stock_count = conn.execute("SELECT COUNT(*) FROM stocks WHERE is_csi300 = TRUE").fetchone()[0]
    
    print(f"\nVerification:")
    print(f"  Stocks: {stock_count}")
    print(f"  Price records: {price_count}")
    print(f"  Fundamental records: {fundamental_count}")
    
    print("\n✓ Mock data generation complete!")
    
    conn.close()

if __name__ == "__main__":
    generate_mock_data()
