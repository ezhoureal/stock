"""
News Scraper Module for Sentiment Arbitrage System

Provides robust news scraping from multiple Chinese financial sources:
- Eastmoney (www.eastmoney.com)
- Sina Finance (finance.sina.com.cn)
- China Times (www.chinatimes.com)
- Snowball (雪球) for social sentiment

Features:
- Multi-source scraping with fallback
- Rate limiting and politeness
- Anti-scraping measures (user agents, delays)
- Text extraction and metadata
- Database storage with deduplication
- Async support for high throughput
"""

import asyncio
import hashlib
import logging
import random
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import aiohttp
import pandas as pd
from bs4 import BeautifulSoup
from pydantic import BaseModel, validator
from tenacity import (
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_exponential,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# User agent rotation list
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0",
]


@dataclass
class NewsScraperConfig:
    """Configuration for news scraper"""

    # Database settings
    db_path: str = "data/stocks.db"

    # Rate limiting
    requests_per_second: float = 1.0
    min_delay: float = 0.5
    max_delay: float = 2.0

    # Retry settings
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay_retry: float = 30.0

    # Content extraction
    min_text_length: int = 100
    max_text_length: int = 10000

    # Deduplication
    use_content_hash: bool = True

    # Source-specific settings
    eastmoney_enabled: bool = True
    sina_enabled: bool = True
    snowball_enabled: bool = True

    # Async settings
    max_concurrent_requests: int = 5
    timeout: int = 30


class NewsArticle(BaseModel):
    """Data model for news article"""

    url: str
    title: str
    content: str
    source: str
    publish_time: str | None = None
    author: str | None = None
    stock_codes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @validator("content")
    def validate_content_length(cls, v):
        if len(v) < 100:
            raise ValueError("Content too short")
        if len(v) > 50000:
            raise ValueError("Content too long")
        return v

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return self.dict()

    def get_content_hash(self) -> str:
        """Generate hash of content for deduplication"""
        return hashlib.md5(self.content.encode()).hexdigest()


class SourceScraper:
    """Base class for source-specific scrapers"""

    def __init__(self, config: NewsScraperConfig):
        self.config = config
        self.session: aiohttp.ClientSession | None = None

        # Rate limiting
        self.last_request_time = 0.0
        self.min_interval = 1.0 / config.requests_per_second

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            headers=self._get_random_headers(),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    def _get_random_headers(self) -> dict[str, str]:
        """Get random headers for request"""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    async def _rate_limit(self):
        """Apply rate limiting"""
        now = time.time()
        time_since_last = now - self.last_request_time

        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last + random.uniform(0, 0.5)
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def fetch_page(self, url: str) -> str:
        """Fetch page content with retry logic"""
        await self._rate_limit()

        headers = self._get_random_headers()

        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.warning(f"HTTP {response.status} for {url}")
                    response.raise_for_status()

                # Detect encoding
                content = await response.text()
                return content

        except aiohttp.ClientError as e:
            logger.error(f"Error fetching {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            raise

    async def scrape_article(self, url: str) -> NewsArticle | None:
        """Scrape a single article (to be implemented by subclasses)"""
        raise NotImplementedError


class EastmoneyScraper(SourceScraper):
    """Scraper for Eastmoney (www.eastmoney.com)"""

    BASE_URL = "https://www.eastmoney.com"

    def __init__(self, config: NewsScraperConfig):
        super().__init__(config)

    async def scrape_article(self, url: str) -> NewsArticle | None:
        """Scrape article from Eastmoney"""
        try:
            html = await self.fetch_page(url)
            soup = BeautifulSoup(html, "lxml")

            # Extract title
            title_elem = soup.find("h1") or soup.find(class_="title")
            title = title_elem.get_text(strip=True) if title_elem else ""

            # Extract content
            content_elem = soup.find("div", class_="Body") or soup.find("article")
            if content_elem:
                # Remove script and style elements
                for script in content_elem(["script", "style"]):
                    script.decompose()
                content = content_elem.get_text(separator="\n", strip=True)
            else:
                content = ""

            # Extract publish time
            time_elem = soup.find(class_="time") or soup.find("time")
            publish_time = time_elem.get_text(strip=True) if time_elem else None

            # Extract stock codes from title/content
            stock_codes = self._extract_stock_codes(title + content)

            if len(content) < self.config.min_text_length:
                logger.warning(f"Content too short for {url}")
                return None

            article = NewsArticle(
                url=url,
                title=title,
                content=content,
                source="eastmoney",
                publish_time=publish_time,
                stock_codes=stock_codes,
            )

            logger.debug(f"Scraped article from Eastmoney: {title[:50]}...")
            return article

        except Exception as e:
            logger.error(f"Error scraping Eastmoney article {url}: {e}")
            return None

    async def get_latest_news(self, limit: int = 50) -> list[NewsArticle]:
        """Get latest news from Eastmoney homepage"""
        try:
            url = f"{self.BASE_URL}"
            html = await self.fetch_page(url)
            soup = BeautifulSoup(html, "lxml")

            articles = []

            # Find article links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if href.startswith("/") and ("news" in href or "article" in href):
                    full_url = urljoin(self.BASE_URL, href)
                    articles.append(full_url)
                    if len(articles) >= limit:
                        break

            # Scrape articles in parallel
            tasks = [self.scrape_article(url) for url in articles]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            valid_articles = [r for r in results if isinstance(r, NewsArticle)]
            logger.info(f"Scraped {len(valid_articles)}/{len(articles)} articles from Eastmoney")

            return valid_articles

        except Exception as e:
            logger.error(f"Error getting latest news from Eastmoney: {e}")
            return []

    def _extract_stock_codes(self, text: str) -> list[str]:
        """Extract stock codes from text (e.g., 000001, 600000)"""
        import re

        pattern = r"\b(600\d{3}|000\d{3}|002\d{3}|300\d{3})\b"
        codes = re.findall(pattern, text)
        return codes


class SinaFinanceScraper(SourceScraper):
    """Scraper for Sina Finance (finance.sina.com.cn)"""

    BASE_URL = "http://finance.sina.com.cn"

    def __init__(self, config: NewsScraperConfig):
        super().__init__(config)

    async def scrape_article(self, url: str) -> NewsArticle | None:
        """Scrape article from Sina Finance"""
        try:
            html = await self.fetch_page(url)
            soup = BeautifulSoup(html, "lxml")

            # Extract title
            title_elem = soup.find("h1") or soup.find(class_="article-title")
            title = title_elem.get_text(strip=True) if title_elem else ""

            # Extract content
            content_elem = soup.find("div", class_="article-content") or soup.find("article")
            if content_elem:
                for script in content_elem(["script", "style"]):
                    script.decompose()
                content = content_elem.get_text(separator="\n", strip=True)
            else:
                content = ""

            # Extract publish time
            time_elem = soup.find(class_="article-time") or soup.find("time")
            publish_time = time_elem.get_text(strip=True) if time_elem else None

            # Extract author
            author_elem = soup.find(class_="article-author")
            author = author_elem.get_text(strip=True) if author_elem else None

            stock_codes = self._extract_stock_codes(title + content)

            if len(content) < self.config.min_text_length:
                logger.warning(f"Content too short for {url}")
                return None

            article = NewsArticle(
                url=url,
                title=title,
                content=content,
                source="sina_finance",
                publish_time=publish_time,
                author=author,
                stock_codes=stock_codes,
            )

            logger.debug(f"Scraped article from Sina Finance: {title[:50]}...")
            return article

        except Exception as e:
            logger.error(f"Error scraping Sina Finance article {url}: {e}")
            return None

    async def get_latest_news(self, limit: int = 50) -> list[NewsArticle]:
        """Get latest news from Sina Finance"""
        try:
            url = f"{self.BASE_URL}/roll/"
            html = await self.fetch_page(url)
            soup = BeautifulSoup(html, "lxml")

            articles = []

            # Find article links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "finance.sina.com.cn" in href and ("/stock/" in href or "/news/" in href):
                    articles.append(href)
                    if len(articles) >= limit:
                        break

            # Scrape articles in parallel
            tasks = [self.scrape_article(url) for url in articles]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            valid_articles = [r for r in results if isinstance(r, NewsArticle)]
            logger.info(f"Scraped {len(valid_articles)}/{len(articles)} articles from Sina Finance")

            return valid_articles

        except Exception as e:
            logger.error(f"Error getting latest news from Sina Finance: {e}")
            return []

    def _extract_stock_codes(self, text: str) -> list[str]:
        """Extract stock codes from text"""
        import re

        pattern = r"\b(600\d{3}|000\d{3}|002\d{3}|300\d{3})\b"
        codes = re.findall(pattern, text)
        return codes


class SnowballScraper(SourceScraper):
    """Scraper for Snowball (雪球) - Social sentiment platform"""

    BASE_URL = "https://xueqiu.com"

    def __init__(self, config: NewsScraperConfig):
        super().__init__(config)

    async def scrape_post(self, url: str) -> NewsArticle | None:
        """Scrape post from Snowball"""
        try:
            html = await self.fetch_page(url)
            soup = BeautifulSoup(html, "lxml")

            # Extract title/content
            title_elem = soup.find("h1") or soup.find(class_="status-title")
            content_elem = soup.find("div", class_="status-content") or soup.find("article")

            if content_elem:
                for script in content_elem(["script", "style"]):
                    script.decompose()
                content = content_elem.get_text(separator="\n", strip=True)
            else:
                content = ""

            title = title_elem.get_text(strip=True) if title_elem else ""

            # Extract author
            author_elem = soup.find(class_="status-author")
            author = author_elem.get_text(strip=True) if author_elem else None

            # Extract publish time
            time_elem = soup.find(class_="status-time")
            publish_time = time_elem.get_text(strip=True) if time_elem else None

            stock_codes = self._extract_stock_codes(title + content)

            if len(content) < self.config.min_text_length:
                logger.warning(f"Content too short for {url}")
                return None

            article = NewsArticle(
                url=url,
                title=title,
                content=content,
                source="snowball",
                publish_time=publish_time,
                author=author,
                stock_codes=stock_codes,
            )

            logger.debug(f"Scraped post from Snowball: {title[:50]}...")
            return article

        except Exception as e:
            logger.error(f"Error scraping Snowball post {url}: {e}")
            return None

    async def get_latest_posts(self, limit: int = 50) -> list[NewsArticle]:
        """Get latest posts from Snowball"""
        try:
            # Snowball API requires authentication, so we'll scrape the homepage
            url = f"{self.BASE_URL}"
            html = await self.fetch_page(url)
            soup = BeautifulSoup(html, "lxml")

            posts = []

            # Find post links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "/status/" in href:
                    full_url = urljoin(self.BASE_URL, href)
                    posts.append(full_url)
                    if len(posts) >= limit:
                        break

            # Scrape posts in parallel
            tasks = [self.scrape_post(url) for url in posts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            valid_articles = [r for r in results if isinstance(r, NewsArticle)]
            logger.info(f"Scraped {len(valid_articles)}/{len(posts)} posts from Snowball")

            return valid_articles

        except Exception as e:
            logger.error(f"Error getting latest posts from Snowball: {e}")
            return []

    def _extract_stock_codes(self, text: str) -> list[str]:
        """Extract stock codes from text"""
        import re

        pattern = r"\b(600\d{3}|000\d{3}|002\d{3}|300\d{3})\b"
        codes = re.findall(pattern, text)
        return codes


class NewsManager:
    """
    Manager class for news scraping from multiple sources
    """

    def __init__(self, config: NewsScraperConfig | None = None):
        self.config = config or NewsScraperConfig()
        self._init_database()

        # Initialize scrapers
        self.eastmoney_scraper = (
            EastmoneyScraper(self.config) if self.config.eastmoney_enabled else None
        )
        self.sina_scraper = SinaFinanceScraper(self.config) if self.config.sina_enabled else None
        self.snowball_scraper = (
            SnowballScraper(self.config) if self.config.snowball_enabled else None
        )

    def _init_database(self):
        """Initialize database schema for news"""
        db_path = Path(self.config.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create news table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                publish_time TEXT,
                author TEXT,
                stock_codes TEXT,
                content_hash TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(url)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_source ON news(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_publish_time ON news(publish_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_content_hash ON news(content_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_stock_codes ON news(stock_codes)")

        conn.commit()
        conn.close()

        logger.info(f"News database initialized: {db_path}")

    async def scrape_all_sources(self, limit_per_source: int = 50) -> list[NewsArticle]:
        """Scrape news from all enabled sources"""
        all_articles = []

        tasks = []

        if self.eastmoney_scraper:
            tasks.append(self.eastmoney_scraper.get_latest_news(limit_per_source))

        if self.sina_scraper:
            tasks.append(self.sina_scraper.get_latest_news(limit_per_source))

        if self.snowball_scraper:
            tasks.append(self.snowball_scraper.get_latest_posts(limit_per_source))

        # Run all scrapers in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
            else:
                logger.error(f"Error during scraping: {result}")

        logger.info(f"Total articles scraped: {len(all_articles)}")
        return all_articles

    def save_articles(self, articles: list[NewsArticle]) -> int:
        """Save articles to database with deduplication"""
        if not articles:
            return 0

        conn = sqlite3.connect(self.config.db_path)
        cursor = conn.cursor()

        saved_count = 0
        skipped_count = 0

        for article in articles:
            try:
                # Check for duplicates by URL
                cursor.execute("SELECT id FROM news WHERE url = ?", (article.url,))
                if cursor.fetchone():
                    skipped_count += 1
                    continue

                # Check for duplicates by content hash if enabled
                if self.config.use_content_hash:
                    content_hash = article.get_content_hash()
                    cursor.execute("SELECT id FROM news WHERE content_hash = ?", (content_hash,))
                    if cursor.fetchone():
                        skipped_count += 1
                        continue
                else:
                    content_hash = None

                # Insert article
                cursor.execute(
                    """
                    INSERT INTO news (url, title, content, source, publish_time, author, stock_codes, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        article.url,
                        article.title,
                        article.content,
                        article.source,
                        article.publish_time,
                        article.author,
                        ",".join(article.stock_codes) if article.stock_codes else None,
                        article.get_content_hash(),
                    ),
                )

                saved_count += 1

            except Exception as e:
                logger.error(f"Error saving article {article.url}: {e}")

        conn.commit()
        conn.close()

        logger.info(f"Saved {saved_count} articles, skipped {skipped_count} duplicates")
        return saved_count

    def get_news_by_stock(self, stock_code: str, limit: int = 100) -> pd.DataFrame:
        """Get news articles for a specific stock"""
        conn = sqlite3.connect(self.config.db_path)

        query = """
            SELECT * FROM news
            WHERE stock_codes LIKE ?
            ORDER BY publish_time DESC
            LIMIT ?
        """

        df = pd.read_sql_query(query, conn, params=(f"%{stock_code}%", limit))

        conn.close()

        return df

    def get_recent_news(self, hours: int = 24, limit: int = 100) -> pd.DataFrame:
        """Get recent news from the last N hours"""
        conn = sqlite3.connect(self.config.db_path)

        cutoff_time = datetime.now() - timedelta(hours=hours)

        query = """
            SELECT * FROM news
            WHERE scraped_at >= ?
            ORDER BY publish_time DESC
            LIMIT ?
        """

        df = pd.read_sql_query(query, conn, params=(cutoff_time.isoformat(), limit))

        conn.close()

        return df

    async def run_scraper(self, limit_per_source: int = 50) -> dict[str, int]:
        """Run the full scraper pipeline"""
        logger.info("Starting news scraper...")

        # Scrape articles from all sources
        articles = await self.scrape_all_sources(limit_per_source)

        # Save to database
        saved_count = self.save_articles(articles)

        results = {
            "scraped": len(articles),
            "saved": saved_count,
            "duplicates": len(articles) - saved_count,
        }

        logger.info(f"Scraper completed: {results}")
        return results


async def main():
    """Main function for testing"""
    config = NewsScraperConfig(requests_per_second=1.0, max_concurrent_requests=5)

    manager = NewsManager(config)

    # Run scraper
    results = await manager.run_scraper(limit_per_source=20)
    print(f"Results: {results}")

    # Get recent news
    recent_news = manager.get_recent_news(hours=24, limit=10)
    print("\nRecent news:")
    print(recent_news[["title", "source", "publish_time"]])


if __name__ == "__main__":
    asyncio.run(main())
