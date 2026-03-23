"""
Data providers using AKShare APIs.

Includes sentiment data providers (derived from market behavior proxies)
and valuation data providers (on-demand PE/PB ratios with per-industry normalization).
"""

from __future__ import annotations

import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from common.types import SentimentScore
from sentiment_strategy.valuation import (
    SectorMetrics,
    ValuationCalculator,
    ValuationConfig,
    ValuationMetrics,
)

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

        Note: stock_hot_rank_em returns codes with market prefix (e.g., "SZ002261"),
        while stock_zh_a_spot_em returns codes without prefix (e.g., "002261").
        We normalize by stripping the market prefix for matching.

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

        # Build spot data lookup using code without market prefix
        # stock_zh_a_spot_em returns codes like "002261" (no prefix)
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
                # stock_hot_rank_em returns "代码" column with market prefix
                # e.g., "SZ002261", "SH603000"
                raw_symbol = str(row.get("代码", ""))
                if not raw_symbol or raw_symbol == "nan":
                    continue

                # Strip market prefix (SH/SZ/BJ) for lookup in spot_dict
                # Keep original symbol with prefix for the result
                symbol = raw_symbol
                lookup_symbol = raw_symbol
                if len(raw_symbol) > 2 and raw_symbol[:2] in ("SH", "SZ", "BJ"):
                    lookup_symbol = raw_symbol[2:]

                rank_percentile = 1 - (i / total_stocks) if total_stocks > 0 else 0

                # Get price change from spot data using stripped symbol
                spot_data = spot_dict.get(lookup_symbol, {})
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
        # API returns column '龙虎榜净买额' (dragon-tiger net buy amount)
        dt_data: dict[str, dict[str, float]] = {}
        if not dt_list_df.empty:
            for _, row in dt_list_df.iterrows():
                symbol = str(row.get("代码", row.get("股票代码", "")))
                if not symbol or symbol == "nan":
                    continue

                net_buy = row.get("龙虎榜净买额", 0)
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
        # API returns column '5日增持估计-占流通股比' (5-day estimated holding change as % of float)
        hsgt_data: dict[str, float] = {}
        if not hsgt_df.empty:
            for _, row in hsgt_df.iterrows():
                symbol = str(row.get("代码", row.get("股票代码", "")))
                if not symbol or symbol == "nan":
                    continue

                # Try multiple possible column names for holding change
                holding_change = row.get("5日增持估计-占流通股比", row.get("持股变动", 0))
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
                # Handle different column names: SSE uses 标的证券代码, SZSE uses 证券代码
                symbol = str(row.get("标的证券代码", row.get("证券代码", row.get("代码", ""))))
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
        - stock_margin_detail_sse: SSE margin trading (columns: 标的证券代码, 融资余额)
        - stock_margin_detail_szse: SZSE margin trading (columns: 证券代码, 融资余额)
        - stock_zh_a_spot_em: Trading volume (columns: 代码, 成交量)

        Sentiment formula:
        sentiment = 0.6 * margin_change + 0.4 * (volume_ratio - 1)

        where volume_ratio = current_volume / avg_volume

        Args:
            margin_df: Combined DataFrame from stock_margin_detail_sse and szse
            spot_df: DataFrame from stock_zh_a_spot_em

        Returns:
            List of SentimentScore objects with source='search'
        """
        scores: list[SentimentScore] = []
        timestamp = datetime.now()

        # Process margin data
        # SSE uses '标的证券代码', SZSE uses '证券代码'
        margin_data: dict[str, float] = {}
        if not margin_df.empty and "融资余额" in margin_df.columns:
            for _, row in margin_df.iterrows():
                # Try different column names for symbol (SSE vs SZSE)
                symbol = str(row.get("标的证券代码", row.get("证券代码", row.get("代码", ""))))
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
        if not spot_df.empty and "成交量" in spot_df.columns:
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


class ValuationDataProvider:
    """
    Provides valuation metrics from AKShare with per-industry normalization.

    Fetches PE/PB ratios on-demand from stock_zh_a_spot_em() API, which returns
    data for ALL A-shares in a single call. Uses per-industry normalization to
    calculate V scores since different sectors have drastically different
    valuation levels.
    """

    def __init__(self, config: dict | None = None) -> None:
        """
        Initialize the valuation data provider.

        Args:
            config: Configuration dict (optional). May contain valuation weights.
        """
        self.config = config or {}
        # Initialize valuation calculator with config weights if provided
        val_config = None
        if "valuation" in self.config:
            val_dict = self.config["valuation"]
            weights = val_dict.get("weights", {})
            val_config = ValuationConfig(
                pe_weight=weights.get("PE", 0.60),
                pb_weight=weights.get("PB", 0.40),
                dividend_weight=0.0,  # Not available from batch API
                peg_weight=0.0,  # Not available from batch API
                deeply_undervalued=val_dict.get("deeply_undervalued", 0.30),
                undervalued=val_dict.get("undervalued", 0.10),
                overvalued=val_dict.get("overvalued", -0.10),
                deeply_overvalued=val_dict.get("deeply_overvalued", -0.30),
            )
        self.calculator = ValuationCalculator(val_config)

    def get_stock_industry_map(self) -> dict[str, str]:
        """
        Fetch stock-to-industry mapping using stock_industry_category_cninfo.

        Returns:
            Dictionary mapping symbol to industry name.
            Example: {"600519": "食品饮料", "000858": "家用电器"}
        """
        try:
            df = ak.stock_industry_category_cninfo()
            logger.info(f"Fetched {len(df)} stock-industry mappings")

            # Build mapping from symbol to industry
            industry_map: dict[str, str] = {}
            for _, row in df.iterrows():
                symbol = str(row.get("股票代码", ""))
                industry = str(row.get("行业名称", ""))
                if symbol and symbol != "nan" and industry and industry != "nan":
                    industry_map[symbol] = industry

            logger.info(f"Mapped {len(industry_map)} symbols to industries")
            return industry_map
        except Exception as e:
            logger.error(f"Error fetching industry mapping: {e}")
            return {}

    def get_valuation_metrics(self, symbols: list[str] | None = None) -> pd.DataFrame:
        """
        Fetch PE/PB for all A-shares from stock_zh_a_spot_em().

        This API returns 5000+ stocks in a single call with:
        - 代码: Stock symbol
        - 名称: Stock name
        - 市盈率-动态: PE ratio (TTM)
        - 市净率: PB ratio

        Note: The symbols parameter is accepted for API consistency but is not
        used since the API returns all stocks in one call.

        Args:
            symbols: Optional list of symbols (ignored, API returns all stocks)

        Returns:
            DataFrame with columns: symbol, name, pe_ratio, pb_ratio
        """
        try:
            df = ak.stock_zh_a_spot_em()
            logger.info(f"Fetched {len(df)} spot records")

            # Extract relevant columns
            result = []
            for _, row in df.iterrows():
                symbol = str(row.get("代码", ""))
                name = str(row.get("名称", ""))
                pe_ratio = row.get("市盈率-动态", None)
                pb_ratio = row.get("市净率", None)

                if symbol and symbol != "nan":
                    # Convert to float, handling invalid values
                    pe: float | None = None
                    pb: float | None = None
                    if pe_ratio not in [None, "", "-"]:
                        try:
                            pe = float(pe_ratio)  # type: ignore[arg-type]
                        except (ValueError, TypeError):
                            pe = None
                    if pb_ratio not in [None, "", "-"]:
                        try:
                            pb = float(pb_ratio)  # type: ignore[arg-type]
                        except (ValueError, TypeError):
                            pb = None

                    result.append(
                        {
                            "symbol": symbol,
                            "name": name,
                            "pe_ratio": pe,
                            "pb_ratio": pb,
                        }
                    )

            result_df = pd.DataFrame(result)
            logger.info(f"Extracted valuation metrics for {len(result_df)} symbols")
            return result_df
        except Exception as e:
            logger.error(f"Error fetching valuation metrics: {e}")
            return pd.DataFrame()

    def calculate_v_scores(self, symbols: list[str]) -> dict[str, float]:
        """
        Calculate V scores with per-industry normalization.

        Process:
        1. Fetch valuation metrics for ALL stocks (needed for sector medians)
        2. Get industry mapping
        3. Calculate median PE/PB per industry
        4. Compute V scores using ValuationCalculator

        Args:
            symbols: List of stock symbols to calculate V scores for

        Returns:
            Dictionary mapping symbol to V score.
            Example: {"600519": 0.15, "000858": -0.05}
        """
        if not symbols:
            return {}

        # Fetch valuation metrics for all stocks
        metrics_df = self.get_valuation_metrics()
        if metrics_df.empty:
            logger.warning("No valuation metrics available")
            return {}

        # Get industry mapping
        industry_map = self.get_stock_industry_map()
        if not industry_map:
            logger.warning("No industry mapping available")

        # Add industry to metrics
        metrics_df["industry"] = metrics_df["symbol"].map(industry_map)  # type: ignore[arg-type]

        # Calculate sector medians
        industry_medians: dict[str, dict[str, float]] = {}
        for industry in metrics_df["industry"].dropna().unique():  # type: ignore[attr-defined]
            industry_data = metrics_df[metrics_df["industry"] == industry]

            # Calculate median PE/PB for this industry
            valid_pe = industry_data["pe_ratio"].dropna()  # type: ignore[attr-defined]
            valid_pb = industry_data["pb_ratio"].dropna()  # type: ignore[attr-defined]

            if not valid_pe.empty and not valid_pb.empty:
                industry_medians[industry] = {
                    "pe_ratio": float(valid_pe.median()),
                    "pb_ratio": float(valid_pb.median()),
                }

        logger.info(f"Calculated medians for {len(industry_medians)} industries")

        # Calculate V scores for requested symbols
        v_scores: dict[str, float] = {}
        for symbol in symbols:
            try:
                symbol_data = metrics_df[metrics_df["symbol"] == symbol]
                if symbol_data.empty:
                    logger.debug(f"No valuation data for {symbol}")
                    continue

                row = symbol_data.iloc[0]
                pe_ratio = row["pe_ratio"]
                pb_ratio = row["pb_ratio"]
                industry = row["industry"]

                # Use industry median if available, otherwise use defaults
                if industry and industry in industry_medians:
                    sector_pe = industry_medians[industry]["pe_ratio"]
                    sector_pb = industry_medians[industry]["pb_ratio"]
                else:
                    # Use conservative market-wide defaults
                    sector_pe = 15.0
                    sector_pb = 2.0
                    logger.debug(f"Using default sector medians for {symbol}")

                # Handle missing PE/PB values
                if pe_ratio is None or pd.isna(pe_ratio) or pe_ratio <= 0:
                    logger.debug(f"Invalid PE for {symbol}, using sector median")
                    pe_ratio = sector_pe
                if pb_ratio is None or pd.isna(pb_ratio) or pb_ratio <= 0:
                    logger.debug(f"Invalid PB for {symbol}, using sector median")
                    pb_ratio = sector_pb

                # Create ValuationMetrics and SectorMetrics
                company = ValuationMetrics(
                    pe_ratio=float(pe_ratio),
                    pb_ratio=float(pb_ratio),
                    dividend_yield=0.0,  # Not available from batch API
                    peg_ratio=None,  # Not available from batch API
                    eps=0.0,  # Not needed for V score
                    book_value_per_share=0.0,  # Not needed for V score
                    annual_dividend=0.0,
                )

                sector = SectorMetrics(
                    pe_ratio=sector_pe,
                    pb_ratio=sector_pb,
                    dividend_yield=0.0,
                    peg_ratio=None,
                )

                # Calculate valuation score
                valuation = self.calculator.calculate_valuation(company, sector)
                v_scores[symbol] = valuation.composite_score

            except Exception as e:
                logger.debug(f"Error calculating V score for {symbol}: {e}")

        logger.info(f"Calculated V scores for {len(v_scores)}/{len(symbols)} symbols")
        return v_scores

    def get_valuation_for_symbols(
        self, symbols: list[str]
    ) -> dict[str, dict[str, float | str | None]]:
        """
        Get detailed valuation data for specific symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary with symbol -> {pe_ratio, pb_ratio, v_score, industry}
        """
        result: dict[str, dict[str, float | str | None]] = {}

        # Get valuation metrics
        metrics_df = self.get_valuation_metrics()
        if metrics_df.empty:
            return result

        # Get industry mapping
        industry_map = self.get_stock_industry_map()

        # Calculate V scores
        v_scores = self.calculate_v_scores(symbols)

        for symbol in symbols:
            symbol_data = metrics_df[metrics_df["symbol"] == symbol]
            if symbol_data.empty:
                continue

            row = symbol_data.iloc[0]
            result[symbol] = {
                "pe_ratio": row["pe_ratio"],
                "pb_ratio": row["pb_ratio"],
                "v_score": v_scores.get(symbol),
                "industry": industry_map.get(symbol),
            }

        return result
