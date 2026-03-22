"""
Sentiment data providers using AKShare APIs.

Derives sentiment scores from market behavior proxies since direct
sentiment APIs are not available for Chinese A-shares.
"""

from __future__ import annotations

import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from common.types import SentimentScore

logger = logging.getLogger(__name__)


class SentimentDataProvider:
    """
    Provides sentiment scores derived from AKShare market data.

    Maps 4 sentiment sources to available AKShare APIs:
    - social: stock_hot_rank_em (popularity + price movement)
    - news: dragon-tiger + northbound holdings
    - forum: fund flow + margin balance
    - search: margin + volume
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize the sentiment data provider."""
        self.config = config or {}

    def get_social_sentiment(
        self, hot_rank_df: pd.DataFrame, spot_df: pd.DataFrame
    ) -> list[SentimentScore]:
        """
        Derive social sentiment from hot rank and price movement.

        Uses stock_hot_rank_em which provides popularity ranking.
        High popularity + price movement = social sentiment.

        Sentiment formula:
        - Top 10% popular with price drop < -2%: -0.6 (panic selling)
        - Top 10% popular with price rise > 2%: 0.6 (FOMO buying)
        - Top 10% popular with moderate change: 0.3 (curiosity)
        - Bottom 10% popular: 0.0 (ignored = neutral)
        - Others: rank_percentile * 0.2

        Args:
            hot_rank_df: DataFrame from stock_hot_rank_em
            spot_df: DataFrame from stock_zh_a_spot_em

        Returns:
            List of SentimentScore objects with source='social'
        """
        scores: list[SentimentScore] = []
        timestamp = datetime.now()

        if hot_rank_df.empty:
            logger.warning("Empty hot rank DataFrame for social sentiment")
            return scores

        total_stocks = len(hot_rank_df)
        spot_dict: dict[str, dict[str, float]] = {}

        if not spot_df.empty and "代码" in spot_df.columns:
            for _, row in spot_df.iterrows():
                symbol = str(row["代码"])
                price_change = row.get("涨跌幅", 0)
                # Type narrowing: ensure we have a float
                if price_change is None:
                    price_change = 0
                elif not isinstance(price_change, (int, float)):
                    try:
                        price_change = float(price_change)
                    except (ValueError, TypeError):
                        price_change = 0
                spot_dict[symbol] = {
                    "price_change_pct": float(price_change),
                }

        for i, (_, row) in enumerate(hot_rank_df.iterrows()):
            try:
                # Extract symbol - AKShare may use different column names
                symbol = str(row.get("代码", row.get("股票代码", "")))
                if not symbol or symbol == "nan":
                    continue

                rank_percentile = 1 - (i / total_stocks) if total_stocks > 0 else 0

                # Get price change from spot data
                spot_data = spot_dict.get(symbol, {})
                price_change_pct = spot_data.get("price_change_pct", 0)

                # Apply sentiment formula
                if rank_percentile > 0.9:  # Top 10% popular
                    if price_change_pct < -2:
                        sentiment = -0.6  # Panic selling
                    elif price_change_pct > 2:
                        sentiment = 0.6  # FOMO buying
                    else:
                        sentiment = 0.3  # Curiosity
                elif rank_percentile < 0.1:
                    sentiment = 0.0  # Ignored = neutral
                else:
                    sentiment = rank_percentile * 0.2

                confidence = min(rank_percentile, 0.8)

                scores.append(
                    SentimentScore(
                        symbol=symbol,
                        timestamp=timestamp,
                        score=sentiment,
                        confidence=confidence,
                        source="social",
                        raw_score=sentiment,
                        metadata={
                            "rank_percentile": rank_percentile,
                            "price_change_pct": price_change_pct,
                        },
                    )
                )
            except Exception as e:
                logger.debug(f"Error processing social sentiment for row {i}: {e}")

        return scores

    def get_news_sentiment(
        self,
        dt_list_df: pd.DataFrame,
        hsgt_df: pd.DataFrame,
    ) -> list[SentimentScore]:
        """
        Derive news sentiment from dragon-tiger and northbound data.

        Uses:
        - stock_lhb_stock_statistic_em: Dragon-tiger list (龙虎榜) net buy/sell
        - stock_hsgt_hold_stock_em: Northbound holdings change

        Sentiment formula:
        sentiment = 0.6 * dt_net_ratio + 0.4 * northbound_change

        where dt_net_ratio = net_buy_amount / (abs(net_buy_amount) + epsilon)

        Args:
            dt_list_df: DataFrame from stock_lhb_stock_statistic_em
            hsgt_df: DataFrame from stock_hsgt_hold_stock_em

        Returns:
            List of SentimentScore objects with source='news'
        """
        scores: list[SentimentScore] = []
        timestamp = datetime.now()

        # Process dragon-tiger data
        dt_data: dict[str, dict[str, float]] = {}
        if not dt_list_df.empty:
            for _, row in dt_list_df.iterrows():
                symbol = str(row.get("代码", row.get("股票代码", "")))
                if not symbol or symbol == "nan":
                    continue

                net_buy = row.get("净买入", 0)
                if isinstance(net_buy, str):
                    try:
                        net_buy = float(net_buy.replace(",", ""))
                    except ValueError:
                        net_buy = 0
                elif net_buy is None:
                    net_buy = 0

                net_buy_float = float(net_buy)
                dt_net_ratio = net_buy_float / (abs(net_buy_float) + 1e-8)
                dt_data[symbol] = {"dt_net_ratio": dt_net_ratio, "has_dt": True}

        # Process northbound data
        hsgt_data: dict[str, float] = {}
        if not hsgt_df.empty:
            for _, row in hsgt_df.iterrows():
                symbol = str(row.get("代码", row.get("股票代码", "")))
                if not symbol or symbol == "nan":
                    continue

                holding_change = row.get("持股变动", 0)
                if isinstance(holding_change, str):
                    try:
                        holding_change = float(holding_change.replace("%", ""))
                    except ValueError:
                        holding_change = 0
                elif holding_change is None:
                    holding_change = 0

                hsgt_data[symbol] = float(holding_change) / 100  # Convert to ratio

        # Combine data
        all_symbols = set(dt_data.keys()) | set(hsgt_data.keys())

        for symbol in all_symbols:
            try:
                dt_info = dt_data.get(symbol, {"dt_net_ratio": 0, "has_dt": False})
                northbound_change = hsgt_data.get(symbol, 0)

                dt_net_ratio = dt_info["dt_net_ratio"]
                has_dt = dt_info["has_dt"]

                sentiment = 0.6 * dt_net_ratio + 0.4 * northbound_change
                sentiment = max(-1.0, min(1.0, sentiment))  # Clamp to [-1, 1]

                confidence = 0.7 if has_dt else 0.4

                scores.append(
                    SentimentScore(
                        symbol=symbol,
                        timestamp=timestamp,
                        score=sentiment,
                        confidence=confidence,
                        source="news",
                        raw_score=sentiment,
                        metadata={
                            "dt_net_ratio": dt_net_ratio,
                            "northbound_change": northbound_change,
                        },
                    )
                )
            except Exception as e:
                logger.debug(f"Error processing news sentiment for {symbol}: {e}")

        return scores

    def get_forum_sentiment(
        self,
        fund_flow_df: pd.DataFrame,
        margin_df: pd.DataFrame,
    ) -> list[SentimentScore]:
        """
        Derive forum sentiment from fund flow and margin data.

        Uses:
        - stock_market_fund_flow: Main vs retail fund flow
        - stock_margin_detail_*: Margin trading balance changes

        Sentiment formula:
        sentiment = 0.6 * main_force_ratio + 0.4 * margin_change

        where main_force_ratio = main_net_inflow / (abs(main_net_inflow) + retail_inflow + epsilon)

        Args:
            fund_flow_df: DataFrame from stock_market_fund_flow
            margin_df: DataFrame from stock_margin_detail_sse or szse

        Returns:
            List of SentimentScore objects with source='forum'
        """
        scores: list[SentimentScore] = []
        timestamp = datetime.now()

        # Process fund flow data
        flow_data: dict[str, dict[str, float]] = {}
        if not fund_flow_df.empty:
            for _, row in fund_flow_df.iterrows():
                symbol = str(row.get("代码", row.get("股票代码", "")))
                if not symbol or symbol == "nan":
                    continue

                main_net = row.get("主力净流入", 0)
                retail_inflow = row.get("散户净流入", 0)

                if isinstance(main_net, str):
                    try:
                        main_net = float(main_net.replace(",", ""))
                    except ValueError:
                        main_net = 0
                elif main_net is None:
                    main_net = 0

                if isinstance(retail_inflow, str):
                    try:
                        retail_inflow = float(retail_inflow.replace(",", ""))
                    except ValueError:
                        retail_inflow = 0
                elif retail_inflow is None:
                    retail_inflow = 0

                main_force_ratio = float(main_net) / (
                    abs(float(main_net)) + abs(float(retail_inflow)) + 1e-8
                )
                flow_data[symbol] = {"main_force_ratio": main_force_ratio}

        # Process margin data for change calculation
        margin_data: dict[str, float] = {}
        if not margin_df.empty and "融资余额" in margin_df.columns:
            for _, row in margin_df.iterrows():
                symbol = str(row.get("代码", row.get("股票代码", "")))
                if not symbol or symbol == "nan":
                    continue

                margin_balance = row.get("融资余额", 0)
                if isinstance(margin_balance, str):
                    try:
                        margin_balance = float(margin_balance.replace(",", ""))
                    except ValueError:
                        margin_balance = 0
                elif margin_balance is None:
                    margin_balance = 0

                # For margin change, we'd need historical data - using balance as proxy
                # Normalize by assuming average balance around 10M for scale
                margin_change = (float(margin_balance) - 10_000_000) / (10_000_000 + 1e-8)
                margin_change = max(-1.0, min(1.0, margin_change))
                margin_data[symbol] = margin_change

        # Combine data
        all_symbols = set(flow_data.keys()) | set(margin_data.keys())

        for symbol in all_symbols:
            try:
                flow_info = flow_data.get(symbol, {"main_force_ratio": 0})
                margin_change = margin_data.get(symbol, 0)

                main_force_ratio = flow_info["main_force_ratio"]

                sentiment = 0.6 * main_force_ratio + 0.4 * margin_change
                sentiment = max(-1.0, min(1.0, sentiment))  # Clamp to [-1, 1]

                scores.append(
                    SentimentScore(
                        symbol=symbol,
                        timestamp=timestamp,
                        score=sentiment,
                        confidence=0.6,
                        source="forum",
                        raw_score=sentiment,
                        metadata={
                            "main_force_ratio": main_force_ratio,
                            "margin_change": margin_change,
                        },
                    )
                )
            except Exception as e:
                logger.debug(f"Error processing forum sentiment for {symbol}: {e}")

        return scores

    def get_search_sentiment(
        self,
        margin_df: pd.DataFrame,
        spot_df: pd.DataFrame,
    ) -> list[SentimentScore]:
        """
        Derive search sentiment from margin and volume data.

        Uses:
        - stock_margin_detail_*: Margin trading balance changes
        - stock_zh_a_spot_em: Trading volume

        Sentiment formula:
        sentiment = 0.6 * margin_change + 0.4 * (volume_ratio - 1)

        where volume_ratio = current_volume / avg_volume

        Args:
            margin_df: DataFrame from stock_margin_detail_sse or szse
            spot_df: DataFrame from stock_zh_a_spot_em

        Returns:
            List of SentimentScore objects with source='search'
        """
        scores: list[SentimentScore] = []
        timestamp = datetime.now()

        # Process margin data
        margin_data: dict[str, float] = {}
        if not margin_df.empty and "融资余额" in margin_df.columns:
            for _, row in margin_df.iterrows():
                symbol = str(row.get("代码", row.get("股票代码", "")))
                if not symbol or symbol == "nan":
                    continue

                margin_balance = row.get("融资余额", 0)
                if isinstance(margin_balance, str):
                    try:
                        margin_balance = float(margin_balance.replace(",", ""))
                    except ValueError:
                        margin_balance = 0
                elif margin_balance is None:
                    margin_balance = 0

                # Normalize change
                margin_change = (float(margin_balance) - 10_000_000) / (10_000_000 + 1e-8)
                margin_change = max(-1.0, min(1.0, margin_change))
                margin_data[symbol] = margin_change

        # Process spot data for volume
        spot_data: dict[str, dict[str, float]] = {}
        if not spot_df.empty:
            for _, row in spot_df.iterrows():
                symbol = str(row.get("代码", ""))
                if not symbol or symbol == "nan":
                    continue

                volume = row.get("成交量", 0)
                if isinstance(volume, str):
                    try:
                        volume = float(volume.replace(",", ""))
                    except ValueError:
                        volume = 0
                elif volume is None:
                    volume = 0

                # Assume average daily volume of 10M shares as baseline
                avg_volume = 10_000_000
                volume_ratio = float(volume) / (avg_volume + 1e-8)
                # Clamp to reasonable range
                volume_ratio = max(0.1, min(10.0, volume_ratio))

                spot_data[symbol] = {"volume_ratio": volume_ratio}

        # Combine data
        all_symbols = set(margin_data.keys()) | set(spot_data.keys())

        for symbol in all_symbols:
            try:
                margin_change = margin_data.get(symbol, 0)
                spot_info = spot_data.get(symbol, {"volume_ratio": 1.0})
                volume_ratio = spot_info["volume_ratio"]

                sentiment = 0.6 * margin_change + 0.4 * (volume_ratio - 1)
                sentiment = max(-1.0, min(1.0, sentiment))  # Clamp to [-1, 1]

                scores.append(
                    SentimentScore(
                        symbol=symbol,
                        timestamp=timestamp,
                        score=sentiment,
                        confidence=0.5,
                        source="search",
                        raw_score=sentiment,
                        metadata={
                            "margin_change": margin_change,
                            "volume_ratio": volume_ratio,
                        },
                    )
                )
            except Exception as e:
                logger.debug(f"Error processing search sentiment for {symbol}: {e}")

        return scores

    def fetch_hot_rank(self) -> pd.DataFrame:
        """Fetch hot rank data from AKShare."""
        try:
            df = ak.stock_hot_rank_em()
            logger.info(f"Fetched {len(df)} hot rank records")
            return df
        except Exception as e:
            logger.error(f"Error fetching hot rank: {e}")
            return pd.DataFrame()

    def fetch_spot_data(self) -> pd.DataFrame:
        """Fetch all A-share spot data from AKShare."""
        try:
            df = ak.stock_zh_a_spot_em()
            logger.info(f"Fetched {len(df)} spot records")
            return df
        except Exception as e:
            logger.error(f"Error fetching spot data: {e}")
            return pd.DataFrame()

    def fetch_dragon_tiger(self) -> pd.DataFrame:
        """Fetch dragon-tiger list statistics from AKShare."""
        try:
            df = ak.stock_lhb_stock_statistic_em()
            logger.info(f"Fetched {len(df)} dragon-tiger records")
            return df
        except Exception as e:
            logger.error(f"Error fetching dragon-tiger: {e}")
            return pd.DataFrame()

    def fetch_northbound_holdings(self) -> pd.DataFrame:
        """Fetch northbound holdings from AKShare."""
        try:
            df = ak.stock_hsgt_hold_stock_em()
            logger.info(f"Fetched {len(df)} northbound holding records")
            return df
        except Exception as e:
            logger.error(f"Error fetching northbound holdings: {e}")
            return pd.DataFrame()

    def fetch_fund_flow(self) -> pd.DataFrame:
        """Fetch market fund flow from AKShare."""
        try:
            df = ak.stock_market_fund_flow()
            logger.info(f"Fetched {len(df)} fund flow records")
            return df
        except Exception as e:
            logger.error(f"Error fetching fund flow: {e}")
            return pd.DataFrame()

    def fetch_margin_sse(self) -> pd.DataFrame:
        """Fetch SSE margin trading details from AKShare."""
        try:
            df = ak.stock_margin_detail_sse()
            logger.info(f"Fetched {len(df)} SSE margin records")
            return df
        except Exception as e:
            logger.error(f"Error fetching SSE margin: {e}")
            return pd.DataFrame()

    def fetch_margin_szse(self) -> pd.DataFrame:
        """Fetch SZSE margin trading details from AKShare."""
        try:
            df = ak.stock_margin_detail_szse()
            logger.info(f"Fetched {len(df)} SZSE margin records")
            return df
        except Exception as e:
            logger.error(f"Error fetching SZSE margin: {e}")
            return pd.DataFrame()

    def get_all_sentiment(self) -> list[SentimentScore]:
        """
        Fetch and calculate sentiment from all sources.

        Returns:
            Combined list of SentimentScore objects from all sources
        """
        all_scores: list[SentimentScore] = []

        # Fetch all data
        hot_rank_df = self.fetch_hot_rank()
        spot_df = self.fetch_spot_data()
        dt_list_df = self.fetch_dragon_tiger()
        hsgt_df = self.fetch_northbound_holdings()
        fund_flow_df = self.fetch_fund_flow()
        margin_sse_df = self.fetch_margin_sse()
        margin_szse_df = self.fetch_margin_szse()

        # Combine margin data from both exchanges
        margin_df = pd.concat([margin_sse_df, margin_szse_df], ignore_index=True)

        # Calculate sentiment for each source
        all_scores.extend(self.get_social_sentiment(hot_rank_df, spot_df))
        all_scores.extend(self.get_news_sentiment(dt_list_df, hsgt_df))
        all_scores.extend(self.get_forum_sentiment(fund_flow_df, margin_df))
        all_scores.extend(self.get_search_sentiment(margin_df, spot_df))

        logger.info(f"Generated {len(all_scores)} total sentiment scores")
        return all_scores
