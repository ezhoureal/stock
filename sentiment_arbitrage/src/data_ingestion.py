"""
Stock Data Ingestion Module for Sentiment Arbitrage System

Provides robust data ingestion for CSI 300 stocks using Akshare and Baostock.
Features:
- Multi-source data fetching (Akshare primary, Baostock backup)
- Exponential backoff retry logic
- Local SQLite caching
- Comprehensive data validation
- Real-time and historical data support
- Graceful error handling and recovery
"""

import asyncio
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import akshare as ak
import baostock as bs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class DataIngestionConfig:
    """Configuration for data ingestion"""
    # Cache settings
    cache_dir: str = "data/cache"
    db_path: str = "data/stocks.db"
    
    # Retry settings
    max_retries: int = 5
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    
    # Rate limiting
    requests_per_second: float = 2.0
    batch_size: int = 50
    
    # Data quality
    min_data_points: int = 100
    max_missing_ratio: float = 0.1
    outlier_std_threshold: float = 3.0
    
    # API preferences
    use_akshare_primary: bool = True
    fallback_on_error: bool = True
    
    # Validation
    validate_ohlcv: bool = True
    validate_fundamentals: bool = True


class DataValidationError(Exception):
    """Custom exception for data validation errors"""
    pass


class APIError(Exception):
    """Custom exception for API errors"""
    pass


class StockDataIngestion:
    """
    Main class for stock data ingestion from multiple sources
    
    Supports:
    - Akshare (primary source)
    - Baostock (backup source)
    - Local SQLite caching
    - Data validation and cleaning
    """
    
    def __init__(self, config: Optional[DataIngestionConfig] = None):
        self.config = config or DataIngestionConfig()
        self._init_cache_dir()
        self._init_database()
        self._executor = ThreadPoolExecutor(max_workers=10)
        
        # Baostock login (lazy initialization)
        self._bs_logged_in = False
        
        logger.info("StockDataIngestion initialized")
    
    def _init_cache_dir(self):
        """Initialize cache directory"""
        cache_path = Path(self.config.cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cache directory: {cache_path}")
    
    def _init_database(self):
        """Initialize SQLite database with schema"""
        db_path = Path(self.config.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create stocks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                ts_code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                industry TEXT,
                market TEXT,
                list_date TEXT,
                delist_date TEXT,
                is_active INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create ohlcv table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                amount REAL,
                adj_factor REAL DEFAULT 1.0,
                UNIQUE(ts_code, trade_date),
                FOREIGN KEY (ts_code) REFERENCES stocks(ts_code)
            )
        """)
        
        # Create fundamentals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fundamentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                ann_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                report_type TEXT,
                pe REAL,
                pe_ttm REAL,
                pb REAL,
                ps REAL,
                ps_ttm REAL,
                dv_ratio REAL,
                dv_ttm REAL,
                total_share REAL,
                float_share REAL,
                total_assets REAL,
                total_liab REAL,
                net_assets REAL,
                eps REAL,
                eps_ttm REAL,
                roe REAL,
                roa REAL,
                UNIQUE(ts_code, ann_date, end_date, report_type),
                FOREIGN KEY (ts_code) REFERENCES stocks(ts_code)
            )
        """)
        
        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_ts_code ON ohlcv(ts_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_trade_date ON ohlcv(trade_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fundamentals_ts_code ON fundamentals(ts_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fundamentals_end_date ON fundamentals(end_date)")
        
        conn.commit()
        conn.close()
        
        logger.info(f"Database initialized: {db_path}")
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception_type((APIError, Exception)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _fetch_csi300_list(self) -> pd.DataFrame:
        """
        Fetch CSI 300 stock list from Akshare
        
        Returns:
            DataFrame with stock codes and names
        """
        try:
            logger.info("Fetching CSI 300 stock list from Akshare")
            df = ak.index_stock_cons(symbol="000300")
            
            if df.empty:
                raise APIError("Empty response from Akshare CSI 300 API")
            
            # Rename columns to standard format
            df.columns = ['ts_code', 'name']
            df['ts_code'] = df['ts_code'].str.lower()
            
            logger.info(f"Fetched {len(df)} CSI 300 stocks")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching CSI 300 list: {e}")
            raise APIError(f"Failed to fetch CSI 300 list: {e}")
    
    def _fetch_stock_list_baostock(self) -> pd.DataFrame:
        """
        Fetch stock list from Baostock as backup
        
        Returns:
            DataFrame with stock codes and names
        """
        try:
            if not self._bs_logged_in:
                lg = bs.login()
                if lg.error_code != '0':
                    raise APIError(f"Baostock login failed: {lg.error_msg}")
                self._bs_logged_in = True
            
            logger.info("Fetching stock list from Baostock")
            rs = bs.query_all_stock(day=datetime.now().strftime("%Y-%m-%d"))
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                raise APIError("Empty response from Baostock")
            
            df = pd.DataFrame(data_list, columns=rs.fields)
            df = df[['code', 'code_name']]
            df.columns = ['ts_code', 'name']
            df['ts_code'] = df['ts_code'].str.lower()
            
            logger.info(f"Fetched {len(df)} stocks from Baostock")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching stock list from Baostock: {e}")
            raise APIError(f"Failed to fetch stock list from Baostock: {e}")
    
    def update_stock_list(self) -> int:
        """
        Update stock list in database
        
        Returns:
            Number of stocks updated
        """
        try:
            # Try Akshare first, fallback to Baostock
            if self.config.use_akshare_primary:
                try:
                    stock_df = self._fetch_csi300_list()
                except Exception as e:
                    logger.warning(f"Akshare failed, trying Baostock: {e}")
                    if self.config.fallback_on_error:
                        stock_df = self._fetch_stock_list_baostock()
                    else:
                        raise
            else:
                stock_df = self._fetch_stock_list_baostock()
            
            # Store in database
            conn = sqlite3.connect(self.config.db_path)
            
            for _, row in stock_df.iterrows():
                conn.execute("""
                    INSERT OR REPLACE INTO stocks 
                    (ts_code, name, updated_at)
                    VALUES (?, ?, ?)
                """, (row['ts_code'], row['name'], datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Updated {len(stock_df)} stocks in database")
            return len(stock_df)
            
        except Exception as e:
            logger.error(f"Error updating stock list: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _fetch_stock_history_akshare(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        period: str = "daily"
    ) -> pd.DataFrame:
        """
        Fetch historical stock data from Akshare
        
        Args:
            ts_code: Stock code (e.g., "000001.sz")
            start_date: Start date (YYYYMMDD)
            end_date: End date (YYYYMMDD)
            period: Data period ("daily", "weekly", "monthly")
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            logger.debug(f"Fetching {ts_code} history from Akshare: {start_date} to {end_date}")
            
            # Akshare uses different API for different exchanges
            if ts_code.endswith('.sh') or ts_code.startswith('6'):
                df = ak.stock_zh_a_hist(
                    symbol=ts_code.split('.')[0],
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=""
                )
            else:
                df = ak.stock_zh_a_hist(
                    symbol=ts_code.split('.')[0],
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=""
                )
            
            if df.empty:
                logger.warning(f"No data for {ts_code}")
                return pd.DataFrame()
            
            # Standardize column names
            df = df.rename(columns={
                '日期': 'trade_date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount'
            })
            
            # Add ts_code
            df['ts_code'] = ts_code.lower()
            
            # Convert date format
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')
            
            logger.debug(f"Fetched {len(df)} records for {ts_code}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching {ts_code} from Akshare: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _fetch_stock_history_baostock(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        frequency: str = "d"
    ) -> pd.DataFrame:
        """
        Fetch historical stock data from Baostock
        
        Args:
            ts_code: Stock code (e.g., "sz.000001")
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            frequency: Data frequency ("d", "w", "m")
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Login if needed
            if not self._bs_logged_in:
                lg = bs.login()
                if lg.error_code != '0':
                    raise APIError(f"Baostock login failed: {lg.error_msg}")
                self._bs_logged_in = True
            
            # Convert ts_code format
            if '.' in ts_code:
                code = ts_code.split('.')[1].lower() + '.' + ts_code.split('.')[0].lower()
            else:
                code = ts_code
            
            logger.debug(f"Fetching {code} from Baostock: {start_date} to {end_date}")
            
            rs = bs.query_history_k_data_plus(
                code,
                "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST",
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                adjustflag="3"
            )
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                logger.warning(f"No data for {code}")
                return pd.DataFrame()
            
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            # Standardize column names
            df = df.rename(columns={
                'date': 'trade_date',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
                'amount': 'amount'
            })
            
            # Convert types
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')
            df['ts_code'] = ts_code.lower()
            
            logger.debug(f"Fetched {len(df)} records for {ts_code}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching {ts_code} from Baostock: {e}")
            raise
    
    def fetch_stock_history(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Fetch historical stock data with caching and fallback
        
        Args:
            ts_code: Stock code (e.g., "000001.sz")
            start_date: Start date (YYYYMMDD)
            end_date: End date (YYYYMMDD)
            use_cache: Whether to use cached data
        
        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"{ts_code}_{start_date}_{end_date}"
        cache_file = Path(self.config.cache_dir) / f"{cache_key}.parquet"
        
        # Check cache
        if use_cache and cache_file.exists():
            logger.debug(f"Loading from cache: {cache_file}")
            return pd.read_parquet(cache_file)
        
        # Try Akshare first
        try:
            df = self._fetch_stock_history_akshare(ts_code, start_date, end_date)
        except Exception as e:
            logger.warning(f"Akshare failed for {ts_code}, trying Baostock: {e}")
            if self.config.fallback_on_error:
                # Convert date format for Baostock
                start_date_bs = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
                end_date_bs = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
                df = self._fetch_stock_history_baostock(ts_code, start_date_bs, end_date_bs)
            else:
                raise
        
        # Validate data
        if self.config.validate_ohlcv:
            df = self._validate_ohlcv_data(df, ts_code)
        
        # Save to cache
        if use_cache and not df.empty:
            df.to_parquet(cache_file, index=False)
            logger.debug(f"Saved to cache: {cache_file}")
        
        return df
    
    def batch_fetch_stock_history(
        self,
        ts_codes: List[str],
        start_date: str,
        end_date: str,
        batch_size: Optional[int] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical data for multiple stocks in parallel
        
        Args:
            ts_codes: List of stock codes
            start_date: Start date (YYYYMMDD)
            end_date: End date (YYYYMMDD)
            batch_size: Batch size for parallel processing
        
        Returns:
            Dictionary mapping stock codes to DataFrames
        """
        batch_size = batch_size or self.config.batch_size
        results = {}
        
        logger.info(f"Fetching history for {len(ts_codes)} stocks")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(
                    self.fetch_stock_history,
                    ts_code,
                    start_date,
                    end_date
                ): ts_code
                for ts_code in ts_codes
            }
            
            for future in as_completed(futures):
                ts_code = futures[future]
                try:
                    results[ts_code] = future.result()
                    logger.debug(f"Fetched {ts_code}")
                except Exception as e:
                    logger.error(f"Failed to fetch {ts_code}: {e}")
                    results[ts_code] = pd.DataFrame()
        
        success_count = sum(1 for df in results.values() if not df.empty)
        logger.info(f"Completed: {success_count}/{len(ts_codes)} successful")
        
        return results
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _fetch_fundamentals_akshare(
        self,
        ts_code: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetch fundamental indicators from Akshare
        
        Args:
            ts_code: Stock code (e.g., "000001.sz")
            start_date: Start date (YYYYMMDD)
            end_date: End date (YYYYMMDD)
        
        Returns:
            DataFrame with fundamental data
        """
        try:
            logger.debug(f"Fetching fundamentals for {ts_code}")
            
            # Fetch stock indicators
            df = ak.stock_individual_fund_indicator(
                symbol=ts_code.split('.')[0]
            )
            
            if df.empty:
                logger.warning(f"No fundamentals for {ts_code}")
                return pd.DataFrame()
            
            df['ts_code'] = ts_code.lower()
            
            logger.debug(f"Fetched {len(df)} fundamental records for {ts_code}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {ts_code}: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _fetch_fundamentals_baostock(
        self,
        ts_code: str,
        year: int,
        quarter: int
    ) -> pd.DataFrame:
        """
        Fetch fundamental data from Baostock
        
        Args:
            ts_code: Stock code (e.g., "000001.sz")
            year: Year
            quarter: Quarter (1-4)
        
        Returns:
            DataFrame with fundamental data
        """
        try:
            # Convert ts_code format
            if '.' in ts_code:
                code = ts_code.split('.')[1].lower() + '.' + ts_code.split('.')[0].lower()
            else:
                code = ts_code
            
            logger.debug(f"Fetching fundamentals for {code} {year}Q{quarter}")
            
            rs = bs.query_performance_data(
                code,
                year,
                quarter
            )
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                return pd.DataFrame()
            
            df = pd.DataFrame(data_list, columns=rs.fields)
            df['ts_code'] = ts_code.lower()
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {ts_code}: {e}")
            raise
    
    def fetch_fundamentals(
        self,
        ts_code: str,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        Fetch fundamental data for a stock
        
        Args:
            ts_code: Stock code
            start_date: Start date (YYYYMMDD)
            end_date: End date (YYYYMMDD)
        
        Returns:
            DataFrame with fundamental data
        """
        try:
            df = self._fetch_fundamentals_akshare(ts_code, start_date, end_date)
            
            if self.config.validate_fundamentals and not df.empty:
                df = self._validate_fundamentals_data(df, ts_code)
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {ts_code}: {e}")
            return pd.DataFrame()
    
    def _validate_ohlcv_data(self, df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
        """
        Validate and clean OHLCV data
        
        Args:
            df: DataFrame with OHLCV data
            ts_code: Stock code for logging
        
        Returns:
            Cleaned DataFrame
        """
        if df.empty:
            return df
        
        original_count = len(df)
        
        # Check required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise DataValidationError(f"Missing required columns: {missing_cols}")
        
        # Remove rows with all NaN values
        df = df.dropna(subset=required_cols, how='all')
        
        # Check for negative prices
        for col in ['open', 'high', 'low', 'close']:
            negative_count = (df[col] < 0).sum()
            if negative_count > 0:
                logger.warning(f"{ts_code}: Found {negative_count} negative {col} values, removing")
                df = df[df[col] >= 0]
        
        # Check OHLC relationships: Low <= Open, High, Close <= High
        valid_rows = (
            (df['low'] <= df['open']) &
            (df['low'] <= df['close']) &
            (df['high'] >= df['open']) &
            (df['high'] >= df['close'])
        )
        invalid_count = (~valid_rows).sum()
        if invalid_count > 0:
            logger.warning(f"{ts_code}: Found {invalid_count} rows with invalid OHLC relationships, removing")
            df = df[valid_rows]
        
        # Detect and handle outliers using z-score
        for col in ['close', 'volume']:
            if col in df.columns and len(df) > self.config.min_data_points:
                mean = df[col].mean()
                std = df[col].std()
                if std > 0:
                    z_scores = np.abs((df[col] - mean) / std)
                    outlier_mask = z_scores > self.config.outlier_std_threshold
                    outlier_count = outlier_mask.sum()
                    if outlier_count > 0:
                        logger.warning(f"{ts_code}: Found {outlier_count} outliers in {col}, applying winsorization")
                        df.loc[outlier_mask, col] = mean + std * self.config.outlier_std_threshold * np.sign(
                            df.loc[outlier_mask, col] - mean
                        )
        
        # Check for missing data ratio
        if len(df) < self.config.min_data_points:
            logger.warning(f"{ts_code}: Insufficient data points ({len(df)} < {self.config.min_data_points})")
        
        cleaned_count = len(df)
        removed_count = original_count - cleaned_count
        if removed_count > 0:
            logger.info(f"{ts_code}: Cleaned {removed_count} rows ({removed_count/original_count:.1%} removal rate)")
        
        return df
    
    def _validate_fundamentals_data(self, df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
        """
        Validate and clean fundamental data
        
        Args:
            df: DataFrame with fundamental data
            ts_code: Stock code for logging
        
        Returns:
            Cleaned DataFrame
        """
        if df.empty:
            return df
        
        # Validate PE ratio (reasonable range)
        if 'pe' in df.columns:
            invalid_pe = (df['pe'] < 0) | (df['pe'] > 1000)
            if invalid_pe.any():
                logger.warning(f"{ts_code}: Found {invalid_pe.sum()} invalid PE values, removing")
                df = df[~invalid_pe]
        
        # Validate PB ratio (reasonable range)
        if 'pb' in df.columns:
            invalid_pb = (df['pb'] < 0) | (df['pb'] > 100)
            if invalid_pb.any():
                logger.warning(f"{ts_code}: Found {invalid_pb.sum()} invalid PB values, removing")
                df = df[~invalid_pb]
        
        # Validate ROE (reasonable range)
        if 'roe' in df.columns:
            invalid_roe = (df['roe'] < -100) | (df['roe'] > 100)
            if invalid_roe.any():
                logger.warning(f"{ts_code}: Found {invalid_roe.sum()} invalid ROE values, removing")
                df = df[~invalid_roe]
        
        return df
    
    def save_to_database(self, df: pd.DataFrame, table_name: str):
        """
        Save DataFrame to database
        
        Args:
            df: DataFrame to save
            table_name: Name of the table ('ohlcv' or 'fundamentals')
        """
        if df.empty:
            logger.warning(f"Empty DataFrame, skipping save to {table_name}")
            return
        
        try:
            conn = sqlite3.connect(self.config.db_path)
            
            # Insert or replace
            if table_name == 'ohlcv':
                df.to_sql(
                    table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi'
                )
            elif table_name == 'fundamentals':
                df.to_sql(
                    table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi'
                )
            
            conn.commit()
            conn.close()
            
            logger.info(f"Saved {len(df)} records to {table_name}")
            
        except Exception as e:
            logger.error(f"Error saving to database: {e}")
            raise
    
    def get_stock_data_from_db(
        self,
        ts_code: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Retrieve stock data from database
        
        Args:
            ts_code: Stock code
            start_date: Start date (YYYYMMDD)
            end_date: End date (YYYYMMDD)
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            conn = sqlite3.connect(self.config.db_path)
            
            query = """
                SELECT ts_code, trade_date, open, high, low, close, volume, amount
                FROM ohlcv
                WHERE ts_code = ? AND trade_date BETWEEN ? AND ?
                ORDER BY trade_date ASC
            """
            
            df = pd.read_sql_query(
                query,
                conn,
                params=(ts_code, start_date, end_date)
            )
            
            conn.close()
            
            return df
            
        except Exception as e:
            logger.error(f"Error retrieving data from database: {e}")
            return pd.DataFrame()
    
    def clear_cache(self, older_than_days: int = 30):
        """
        Clear old cache files
        
        Args:
            older_than_days: Delete files older than this many days
        """
        cache_path = Path(self.config.cache_dir)
        cutoff_time = datetime.now() - timedelta(days=older_than_days)
        
        deleted_count = 0
        for cache_file in cache_path.glob("*.parquet"):
            if datetime.fromtimestamp(cache_file.stat().st_mtime) < cutoff_time:
                cache_file.unlink()
                deleted_count += 1
        
        logger.info(f"Cleared {deleted_count} cache files older than {older_than_days} days")
    
    def __del__(self):
        """Cleanup on deletion"""
        if hasattr(self, '_bs_logged_in') and self._bs_logged_in:
            try:
                bs.logout()
                logger.info("Logged out from Baostock")
            except:
                pass
        
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)


def main():
    """Main function for testing"""
    config = DataIngestionConfig()
    ingestion = StockDataIngestion(config)
    
    # Update stock list
    print("Updating stock list...")
    count = ingestion.update_stock_list()
    print(f"Updated {count} stocks")
    
    # Fetch historical data for a sample stock
    print("\nFetching historical data for 000001.sz...")
    df = ingestion.fetch_stock_history(
        "000001.sz",
        "20230101",
        "20231231"
    )
    print(df.head())
    print(f"\nTotal records: {len(df)}")
    
    # Save to database
    print("\nSaving to database...")
    ingestion.save_to_database(df, 'ohlcv')
    
    # Retrieve from database
    print("\nRetrieving from database...")
    df_db = ingestion.get_stock_data_from_db("000001.sz", "20230101", "20231231")
    print(df_db.head())


if __name__ == "__main__":
    main()
