#!/usr/bin/env python3
"""
Production-ready sentiment data collection for Chinese stocks.
Collects news and social media data from multiple sources with robust error handling.

Usage:
    python collect_sentiment.py --source eastmoney --days 7
    python collect_sentiment.py --source sina --days 7
    python collect_sentiment.py --source all --days 7
"""

import sys
import os
import json
import logging
import time
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Set
import traceback
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/zireael/trade/stocks/data/logs/sentiment_collection.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class SentimentCollectionError(Exception):
    """Base exception for sentiment collection errors"""
    pass


class RateLimitError(SentimentCollectionError):
    """Rate limit hit on API"""
    pass


class DataQualityError(SentimentCollectionError):
    """Data quality issue detected"""
    pass


class NewsArticle:
    """Represents a news article"""

    def __init__(
        self,
        title: str,
        url: str,
        publish_time: datetime,
        content: Optional[str] = None,
        source: str = '',
        stock_symbols: Optional[List[str]] = None
    ):
        self.title = title
        self.url = url
        self.publish_time = publish_time
        self.content = content
        self.source = source
        self.stock_symbols = stock_symbols or []

    def __repr__(self):
        return f"NewsArticle(title={self.title[:50]}, url={self.url[:50]})"

    def to_dict(self):
        return {
            'title': self.title,
            'url': self.url,
            'publish_time': self.publish_time.isoformat(),
            'content': self.content,
            'source': self.source,
            'stock_symbols': ','.join(self.stock_symbols)
        }


class SentimentCollector:
    """
    Robust sentiment data collector with multiple source support.
    """

    def __init__(self, config_path: str = "/home/zireael/trade/stocks/data/config.json"):
        """
        Initialize the sentiment collector.

        Args:
            config_path: Path to configuration file
        """
        self.config = self._load_config(config_path)
        self.db_path = self.config['database']['path']
        self.logger = logger

        # HTTP session for requests
        self.session = None
        self._init_session()

        # Rate limiting
        self.request_count = 0
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 500ms between requests
        self.random_delay_range = (0.5, 2.0)  # Random delay after N requests

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2.0
        self.retry_backoff = 2.0

        # Data quality filters
        self.min_title_length = 10
        self.min_content_length = 50
        self.max_content_length = 100000
        self.spam_keywords = [
            '广告', '推广', 'AD', '赞助', 'sponsored', 'advertising',
            '点击', '下载', '安装', '立即购买', '免费领取'
        ]

        # Track processed URLs to avoid duplicates
        self.processed_urls: Set[str] = set()

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            raise SentimentCollectionError(f"Config load failed: {e}")

    def _init_session(self):
        """Initialize HTTP session with headers"""
        try:
            import requests
            self.session = requests.Session()

            # Set user agent to mimic browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            self.session.headers.update(headers)

            self.logger.info("HTTP session initialized")

        except ImportError:
            raise SentimentCollectionError("requests library not installed")

    def _rate_limit(self):
        """Apply rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)

        # Add random delay every 10 requests to avoid detection
        self.request_count += 1
        if self.request_count % 10 == 0:
            delay = random.uniform(*self.random_delay_range)
            time.sleep(delay)
            self.logger.debug(f"Random delay: {delay:.2f}s after {self.request_count} requests")

        self.last_request_time = time.time()

    def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with retry logic and exponential backoff"""
        last_error = None
        delay = self.retry_delay

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                self.logger.warning(f"Rate limit hit (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    self.logger.info(f"Waiting {delay}s before retry...")
                    time.sleep(delay)
                    delay *= self.retry_backoff
                last_error = e
            except Exception as e:
                self.logger.warning(f"Error on attempt {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    self.logger.info(f"Waiting {delay}s before retry...")
                    time.sleep(delay)
                    delay *= self.retry_backoff
                last_error = e

        raise SentimentCollectionError(f"Failed after {self.max_retries} attempts: {last_error}")

    def _is_spam(self, text: str) -> bool:
        """Check if text contains spam keywords"""
        text_lower = text.lower()
        for keyword in self.spam_keywords:
            if keyword in text_lower:
                return True
        return False

    def _validate_article(self, article: NewsArticle) -> bool:
        """Validate article data quality"""
        if not article.title or len(article.title) < self.min_title_length:
            self.logger.debug(f"Title too short: {article.title[:50]}")
            return False

        if self._is_spam(article.title):
            self.logger.debug(f"Spam detected in title: {article.title[:50]}")
            return False

        if article.content and len(article.content) < self.min_content_length:
            self.logger.debug(f"Content too short for {article.url}")
            return False

        if article.content and len(article.content) > self.max_content_length:
            self.logger.debug(f"Content too long for {article.url}")
            return False

        return True

    def _extract_stock_symbols(self, text: str) -> List[str]:
        """
        Extract stock symbols from text (e.g., "贵州茅台(600519)").

        Args:
            text: Text to extract from

        Returns:
            List of stock symbols (e.g., ['600519'])
        """
        import re

        # Pattern: 6 digits, possibly in parentheses
        pattern = r'(\d{6})'
        matches = re.findall(pattern, text)

        # Filter valid stock codes (starts with 6 for SH, 0/3 for SZ)
        symbols = []
        for match in matches:
            if match.startswith('6') or match.startswith('0') or match.startswith('3'):
                if match not in symbols:
                    symbols.append(match)

        return symbols

    def _connect_database(self):
        """Connect to DuckDB database"""
        try:
            import duckdb
            conn = duckdb.connect(self.db_path)
            return conn
        except Exception as e:
            raise SentimentCollectionError(f"Database connection failed: {e}")

    def fetch_eastmoney_news(
        self,
        days: int = 7,
        max_articles: int = 1000
    ) -> List[NewsArticle]:
        """
        Fetch news from Eastmoney (东方财富网).

        Args:
            days: Number of days to look back
            max_articles: Maximum number of articles to fetch

        Returns:
            List of NewsArticle objects
        """
        self.logger.info(f"Fetching news from Eastmoney (last {days} days)...")

        articles = []

        try:
            # Eastmoney news API
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            end_date = datetime.now().strftime('%Y%m%d')

            # Multiple pages
            page = 1
            page_size = 50

            while len(articles) < max_articles:
                self._rate_limit()

                url = f"http://data.eastmoney.com/notices/getdata.ashx"
                params = {
                    'SecurityCode': '000001',  # General market news
                    'Type': 'RZLZ',
                    'PageIndex': page,
                    'PageSize': page_size,
                    'BeginDate': start_date,
                    'EndDate': end_date
                }

                try:
                    response = self.session.get(url, params=params, timeout=10)
                    response.raise_for_status()

                    data = response.json()

                    if not data or 'Data' not in data:
                        self.logger.warning(f"No data on page {page}")
                        break

                    news_list = data['Data']

                    if not news_list:
                        self.logger.info(f"No more news articles")
                        break

                    for item in news_list:
                        try:
                            title = item.get('NoticesTitle', '')
                            url = item.get('NoticesUrl', '')
                            publish_time_str = item.get('NoticesTime', '')
                            content = item.get('NoticesContent', '')

                            if not title or not url:
                                continue

                            # Parse publish time
                            try:
                                publish_time = datetime.strptime(publish_time_str, '%Y-%m-%d %H:%M:%S')
                            except:
                                publish_time = datetime.now()

                            # Extract stock symbols
                            stock_symbols = self._extract_stock_symbols(title)
                            if content:
                                stock_symbols.extend(self._extract_stock_symbols(content))

                            # Create article
                            article = NewsArticle(
                                title=title,
                                url=url,
                                publish_time=publish_time,
                                content=content,
                                source='eastmoney',
                                stock_symbols=stock_symbols
                            )

                            # Validate
                            if self._validate_article(article):
                                articles.append(article)

                        except Exception as e:
                            self.logger.warning(f"Error parsing article: {e}")
                            continue

                    self.logger.info(f"Page {page}: fetched {len(news_list)} articles")

                    page += 1

                except Exception as e:
                    self.logger.error(f"Error fetching page {page}: {e}")
                    break

            self.logger.info(f"Fetched {len(articles)} valid articles from Eastmoney")

            return articles

        except Exception as e:
            self.logger.error(f"Eastmoney news fetch failed: {e}")
            raise SentimentCollectionError(f"Eastmoney fetch failed: {e}")

    def fetch_sina_news(
        self,
        days: int = 7,
        max_articles: int = 1000
    ) -> List[NewsArticle]:
        """
        Fetch news from Sina Finance (新浪财经).

        Args:
            days: Number of days to look back
            max_articles: Maximum number of articles to fetch

        Returns:
            List of NewsArticle objects
        """
        self.logger.info(f"Fetching news from Sina Finance (last {days} days)...")

        articles = []

        try:
            from bs4 import BeautifulSoup

            start_date = (datetime.now() - timedelta(days=days))

            # Sina finance news page
            page = 1

            while len(articles) < max_articles:
                self._rate_limit()

                url = f"http://finance.sina.com.cn/7x24/"
                params = {'page': page}

                try:
                    response = self.session.get(url, params=params, timeout=10)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, 'html.parser')

                    # Find news items (this selector may need adjustment based on actual HTML)
                    news_items = soup.select('.content li')  # Adjust as needed

                    if not news_items:
                        self.logger.info(f"No more news items on page {page}")
                        break

                    for item in news_items:
                        try:
                            title_elem = item.find('a')
                            time_elem = item.find('span')

                            if not title_elem:
                                continue

                            title = title_elem.get_text(strip=True)
                            url = title_elem.get('href', '')

                            # Parse time
                            time_text = time_elem.get_text(strip=True) if time_elem else ''
                            try:
                                # Parse relative time like "2小时前"
                                if '小时前' in time_text:
                                    hours = int(time_text.replace('小时前', '').strip())
                                    publish_time = datetime.now() - timedelta(hours=hours)
                                elif '分钟前' in time_text:
                                    minutes = int(time_text.replace('分钟前', '').strip())
                                    publish_time = datetime.now() - timedelta(minutes=minutes)
                                else:
                                    publish_time = datetime.now()
                            except:
                                publish_time = datetime.now()

                            # Filter by date
                            if publish_time < start_date:
                                continue

                            # Extract stock symbols
                            stock_symbols = self._extract_stock_symbols(title)

                            # Create article
                            article = NewsArticle(
                                title=title,
                                url=url,
                                publish_time=publish_time,
                                content=None,  # Sina 7x24 doesn't have full content
                                source='sina',
                                stock_symbols=stock_symbols
                            )

                            # Validate
                            if self._validate_article(article):
                                articles.append(article)

                        except Exception as e:
                            self.logger.warning(f"Error parsing Sina article: {e}")
                            continue

                    self.logger.info(f"Page {page}: fetched news items")

                    page += 1

                except Exception as e:
                    self.logger.error(f"Error fetching Sina page {page}: {e}")
                    break

            self.logger.info(f"Fetched {len(articles)} valid articles from Sina Finance")

            return articles

        except ImportError:
            self.logger.error("BeautifulSoup4 not installed")
            raise SentimentCollectionError("BeautifulSoup4 not installed")
        except Exception as e:
            self.logger.error(f"Sina Finance news fetch failed: {e}")
            raise SentimentCollectionError(f"Sina Finance fetch failed: {e}")

    def save_news_articles(self, conn, articles: List[NewsArticle]) -> int:
        """
        Save news articles to database.

        Args:
            conn: DuckDB connection
            articles: List of NewsArticle objects

        Returns:
            Number of articles inserted
        """
        inserted_count = 0

        try:
            conn.execute("BEGIN TRANSACTION")

            for article in articles:
                # Generate content hash for deduplication
                content_hash = hashlib.md5(
                    f"{article.title}{article.url}".encode('utf-8')
                ).hexdigest()

                # Check if already exists
                existing = conn.execute("""
                    SELECT 1 FROM news_raw
                    WHERE content_hash = ?
                """, [content_hash]).fetchone()

                if existing:
                    continue

                # Insert new article
                conn.execute("""
                    INSERT INTO news_raw
                    (title, url, publish_time, content, source, stock_symbols,
                     content_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, [
                    article.title,
                    article.url,
                    article.publish_time,
                    article.content,
                    article.source,
                    ','.join(article.stock_symbols),
                    content_hash
                ])

                inserted_count += 1

            conn.execute("COMMIT")
            self.logger.info(f"Saved {inserted_count} new news articles")

            return inserted_count

        except Exception as e:
            conn.execute("ROLLBACK")
            raise SentimentCollectionError(f"Failed to save news articles: {e}")

    def collect_sentiment(
        self,
        source: str = 'all',
        days: int = 7,
        max_articles: int = 1000
    ):
        """
        Collect sentiment data from specified sources.

        Args:
            source: 'eastmoney', 'sina', or 'all'
            days: Number of days to look back
            max_articles: Maximum articles per source

        Returns:
            Summary statistics dict
        """
        # Connect to database
        conn = self._connect_database()

        try:
            all_articles = []
            stats = {
                'sources': {},
                'total_articles': 0,
                'new_articles': 0
            }

            # Fetch from each source
            sources_to_fetch = []
            if source == 'all':
                sources_to_fetch = ['eastmoney', 'sina']
            else:
                sources_to_fetch = [source]

            for src in sources_to_fetch:
                try:
                    self.logger.info(f"Collecting from {src}...")
                    articles = self._retry_with_backoff(
                        self.fetch_eastmoney_news if src == 'eastmoney' else self.fetch_sina_news,
                        days=days,
                        max_articles=max_articles
                    )

                    all_articles.extend(articles)
                    stats['sources'][src] = len(articles)
                    self.logger.info(f"✓ Collected {len(articles)} articles from {src}")

                except SentimentCollectionError as e:
                    self.logger.error(f"Failed to collect from {src}: {e}")
                    stats['sources'][src] = 0

            # Save to database
            stats['total_articles'] = len(all_articles)
            if all_articles:
                stats['new_articles'] = self.save_news_articles(conn, all_articles)

            # Print summary
            self.logger.info("=" * 80)
            self.logger.info("Sentiment Collection Summary")
            self.logger.info("=" * 80)
            self.logger.info(f"Total sources: {len(sources_to_fetch)}")
            for src, count in stats['sources'].items():
                self.logger.info(f"  {src}: {count} articles")
            self.logger.info(f"Total articles: {stats['total_articles']}")
            self.logger.info(f"New articles saved: {stats['new_articles']}")

            return stats

        finally:
            conn.close()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Collect sentiment data for Chinese stocks")
    parser.add_argument(
        '--source',
        choices=['all', 'eastmoney', 'sina'],
        default='all',
        help='Data source to use'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to look back'
    )
    parser.add_argument(
        '--max-articles',
        type=int,
        default=1000,
        help='Maximum articles per source'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        # Create collector
        collector = SentimentCollector()

        # Collect sentiment
        stats = collector.collect_sentiment(
            source=args.source,
            days=args.days,
            max_articles=args.max_articles
        )

        # Exit with success
        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
