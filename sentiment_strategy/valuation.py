"""
Valuation Module - Chinese Stock Sentiment Trading System

Calculates intrinsic value and undervalued/overvalued scores for Chinese stocks
based on fundamental metrics relative to sector medians.
"""

import json
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.types import Fundamentals

logger = logging.getLogger(__name__)


@dataclass
class ValuationConfig:
    """Configuration for valuation calculations"""

    # Metric weights
    pe_weight: float = 0.40
    pb_weight: float = 0.25
    dividend_weight: float = 0.15
    peg_weight: float = 0.20

    # Thresholds
    deeply_undervalued: float = 0.30
    undervalued: float = 0.10
    overvalued: float = -0.10
    deeply_overvalued: float = -0.30


@dataclass
class ValuationMetrics:
    """Fundamental metrics for a stock"""

    pe_ratio: float  # Price to Earnings
    pb_ratio: float  # Price to Book
    dividend_yield: float  # Annual dividend yield (0-1)
    peg_ratio: float | None  # PEG (PE / earnings growth rate)
    eps: float  # Earnings per share
    book_value_per_share: float
    annual_dividend: float


@dataclass
class SectorMetrics:
    """Sector median metrics for comparison"""

    pe_ratio: float
    pb_ratio: float
    dividend_yield: float
    peg_ratio: float | None


@dataclass
class ValuationScore:
    """Valuation analysis result"""

    composite_score: float  # V score (higher = more undervalued)
    interpretation: str
    relative_pe: float  # (company / sector) - 1
    relative_pb: float
    dividend_diff: float  # relative dividend (company / sector) - 1
    relative_peg: float
    component_scores: dict[str, float]
    trend: float | None = None  # V_trend if historical data available


class ValuationCalculator:
    """
    Calculates intrinsic value and valuation scores for Chinese stocks.
    """

    def __init__(self, config: ValuationConfig | None = None):
        """
        Initialize the valuation calculator.

        Args:
            config: Valuation configuration (uses defaults if None)
        """
        self.config = config or ValuationConfig()

    def calculate_relative_metrics(
        self, company: ValuationMetrics, sector: SectorMetrics
    ) -> tuple[float, float, float, float]:
        """
        Calculate company metrics relative to sector medians.

        For PE, PB, PEG, dividend: (company / sector) - 1
        All metrics use relative percentage calculation for consistency.

        Note: Negative or zero P/E ratios (loss-making companies) are handled
        by assigning a neutral relative score of 0.0, as traditional P/E
        comparisons are meaningless for unprofitable companies.

        Returns:
            (relative_pe, relative_pb, relative_dividend, relative_peg)
        """
        # PE: Lower is better
        # BUG-007 FIX: Handle negative/zero P/E for loss-making companies
        # A negative P/E means the company is losing money - traditional P/E
        # comparison is meaningless in this case
        if sector.pe_ratio > 0 and company.pe_ratio > 0:
            relative_pe = (company.pe_ratio / sector.pe_ratio) - 1
        else:
            # Neutral score for loss-making companies or invalid sector PE
            relative_pe = 0.0

        # PB: Lower is better
        if sector.pb_ratio > 0 and company.pb_ratio > 0:
            relative_pb = (company.pb_ratio / sector.pb_ratio) - 1
        else:
            relative_pb = 0.0

        # BUG-008 FIX: Dividend uses relative percentage like other metrics
        # Higher is better: (company / sector) - 1
        if sector.dividend_yield > 0:
            relative_dividend = (company.dividend_yield / sector.dividend_yield) - 1
        elif company.dividend_yield > 0:
            # Company pays dividend but sector doesn't - positive signal
            relative_dividend = 1.0  # Cap at +100% relative advantage
        else:
            relative_dividend = 0.0

        # PEG: Lower is better
        if (
            sector.peg_ratio
            and sector.peg_ratio > 0
            and company.peg_ratio
            and company.peg_ratio > 0
        ):
            relative_peg = (company.peg_ratio / sector.peg_ratio) - 1
        else:
            # If PEG not available, use neutral score
            relative_peg = 0.0

        return relative_pe, relative_pb, relative_dividend, relative_peg

    def calculate_composite_score(
        self,
        relative_pe: float,
        relative_pb: float,
        relative_dividend: float,
        relative_peg: float,
    ) -> tuple[float, dict[str, float]]:
        """
        Calculate the composite valuation score (V).

        Higher V = more undervalued
        Lower V = more overvalued

        V = (relative_PE * -weight_PE) +
            (relative_PB * -weight_PB) +
            (relative_dividend * weight_dividend) +
            (relative_PEG * -weight_PEG)

        Note: All relative metrics are now percentage-based (company/sector - 1),
        providing consistent scale across all components.

        Returns:
            (composite_score, component_scores)
        """
        # Component scores (negative because lower PE/PB/PEG = better)
        pe_score = -relative_pe * self.config.pe_weight
        pb_score = -relative_pb * self.config.pb_weight
        dividend_score = relative_dividend * self.config.dividend_weight
        peg_score = -relative_peg * self.config.peg_weight

        component_scores = {
            "PE": pe_score,
            "PB": pb_score,
            "dividend": dividend_score,
            "PEG": peg_score,
        }

        composite_score = sum(component_scores.values())

        return composite_score, component_scores

    def interpret_score(self, score: float) -> str:
        """
        Interpret the valuation score.

        Args:
            score: Composite valuation score

        Returns:
            Human-readable interpretation
        """
        if score >= self.config.deeply_undervalued:
            return "deeply_undervalued"
        elif score >= self.config.undervalued:
            return "undervalued"
        elif score >= self.config.overvalued:
            return "fair_value"
        elif score >= self.config.deeply_overvalued:
            return "overvalued"
        else:
            return "deeply_overvalued"

    def calculate_valuation(
        self,
        company: ValuationMetrics,
        sector: SectorMetrics,
        historical_scores: pd.Series | None = None,
    ) -> ValuationScore:
        """
        Calculate full valuation analysis for a stock.

        Args:
            company: Company fundamental metrics
            sector: Sector median metrics
            historical_scores: Historical V scores (for trend calculation)

        Returns:
            ValuationScore with full analysis
        """
        # Calculate relative metrics
        rel_pe, rel_pb, div_diff, rel_peg = self.calculate_relative_metrics(company, sector)

        # Calculate composite score
        composite, components = self.calculate_composite_score(rel_pe, rel_pb, div_diff, rel_peg)

        # Interpret
        interpretation = self.interpret_score(composite)

        # Calculate trend if historical data available
        trend = None
        if historical_scores is not None and len(historical_scores) > 1:
            trend = composite - historical_scores.iloc[-1]

        return ValuationScore(
            composite_score=composite,
            interpretation=interpretation,
            relative_pe=rel_pe,
            relative_pb=rel_pb,
            dividend_diff=div_diff,
            relative_peg=rel_peg,
            component_scores=components,
            trend=trend,
        )

    def calculate_from_fundamentals(
        self,
        fundamentals: Fundamentals,
        default_sector: SectorMetrics | None = None,
    ) -> ValuationScore:
        """
        Calculate valuation score from common.types.Fundamentals.

        This method converts Fundamentals from the common module to
        internal types and calculates the valuation.

        Args:
            fundamentals: Fundamentals object from common.types
            default_sector: Default sector metrics to use if sector not available.
                          If None, uses conservative market-wide defaults.

        Returns:
            ValuationScore object
        """
        # Create internal ValuationMetrics from Fundamentals
        company = ValuationMetrics(
            pe_ratio=fundamentals.pe_ratio or fundamentals.pe_ttm or 0.0,
            pb_ratio=fundamentals.pb_ratio or 0.0,
            dividend_yield=fundamentals.dividend_yield or 0.0,
            peg_ratio=fundamentals.peg_ratio,
            eps=fundamentals.eps or 0.0,
            book_value_per_share=fundamentals.book_value_per_share or 0.0,
            annual_dividend=(fundamentals.dividend_yield or 0.0)
            * (fundamentals.book_value_per_share or 0.0),
        )

        # Use provided sector or create default
        if default_sector is None:
            # Use conservative market-wide defaults for Chinese A-shares
            default_sector = SectorMetrics(
                pe_ratio=15.0,  # Conservative market P/E
                pb_ratio=2.0,  # Conservative market P/B
                dividend_yield=0.02,  # 2% dividend yield
                peg_ratio=1.5,  # Conservative PEG
            )

        return self.calculate_valuation(company, default_sector)

    def batch_calculate(
        self, metrics_df: pd.DataFrame, sector_medians: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate valuation for multiple stocks.

        Args:
            metrics_df: DataFrame with columns [symbol, pe_ratio, pb_ratio,
                       dividend_yield, peg_ratio, eps, book_value_per_share,
                       annual_dividend, sector]
            sector_medians: DataFrame with sector medians

        Returns:
            DataFrame with valuation scores added
        """
        results = []
        skipped_symbols = []  # BUG-018 FIX: Track skipped stocks

        for _, row in metrics_df.iterrows():
            symbol = row["symbol"]

            # Get sector median
            sector_data = sector_medians[sector_medians["sector"] == row["sector"]]
            if sector_data.empty:
                # BUG-018 FIX: Log warning when stock is skipped due to missing sector data
                skipped_symbols.append(symbol)
                logger.warning(
                    "Skipping symbol '%s': no sector data found for sector '%s'",
                    symbol,
                    row["sector"],
                )
                continue

            sector_row = sector_data.iloc[0]

            company = ValuationMetrics(
                pe_ratio=row["pe_ratio"],
                pb_ratio=row["pb_ratio"],
                dividend_yield=row["dividend_yield"],
                peg_ratio=row.get("peg_ratio", None),
                eps=row["eps"],
                book_value_per_share=row["book_value_per_share"],
                annual_dividend=row["annual_dividend"],
            )

            sector = SectorMetrics(
                pe_ratio=sector_row["pe_ratio"],
                pb_ratio=sector_row["pb_ratio"],
                dividend_yield=sector_row["dividend_yield"],
                peg_ratio=sector_row.get("peg_ratio", None),
            )

            valuation = self.calculate_valuation(company, sector)

            results.append(
                {
                    "symbol": symbol,
                    "V": valuation.composite_score,
                    "V_interpretation": valuation.interpretation,
                    "V_trend": valuation.trend,
                    "relative_pe": valuation.relative_pe,
                    "relative_pb": valuation.relative_pb,
                    "dividend_diff": valuation.dividend_diff,
                    "relative_peg": valuation.relative_peg,
                }
            )

        # BUG-018 FIX: Log summary of skipped stocks
        if skipped_symbols:
            logger.warning(
                "Batch calculation skipped %d symbols due to missing sector data: %s",
                len(skipped_symbols),
                skipped_symbols[:10],  # Show first 10 to avoid log spam
            )

        return pd.DataFrame(results)

    def calculate_intrinsic_value(
        self, company: ValuationMetrics, sector: SectorMetrics, risk_free_rate: float = 0.03
    ) -> dict[str, float | None]:
        """
        Calculate intrinsic value using multiple methods.

        This is a simplified approach. For production, consider:
        - DCF (Discounted Cash Flow)
        - Gordon Growth Model (for dividend stocks)
        - Residual Income Model

        Args:
            company: Company metrics
            sector: Sector metrics
            risk_free_rate: Risk-free rate (default 3%)

        Returns:
            Dict with intrinsic value estimates
        """
        # Method 1: P/E based
        # BUG-009 FIX: Handle negative earnings (loss-making companies)
        # P/E based intrinsic value is only meaningful for profitable companies
        if sector.pe_ratio > 0 and company.eps > 0:
            fair_pe = sector.pe_ratio
            intrinsic_pe = company.eps * fair_pe
        else:
            # For loss-making companies, P/E method is not applicable
            intrinsic_pe = None

        # Method 2: P/B based
        if sector.pb_ratio > 0 and company.book_value_per_share > 0:
            fair_pb = sector.pb_ratio
            intrinsic_pb = company.book_value_per_share * fair_pb
        else:
            intrinsic_pb = None

        # Method 3: Gordon Growth Model (for dividend stocks)
        # P = D * (1 + g) / (r - g)
        # Assume growth rate = 3% (conservative) or use sector average
        if company.dividend_yield > 0 and risk_free_rate > 0.03:
            growth_rate = 0.03  # Conservative assumption
            if risk_free_rate > growth_rate:
                intrinsic_gordon = (
                    company.annual_dividend * (1 + growth_rate) / (risk_free_rate - growth_rate)
                )
            else:
                intrinsic_gordon = None
        else:
            intrinsic_gordon = None

        # Weighted average (equal weights for available methods)
        methods = []
        if intrinsic_pe is not None:
            methods.append(intrinsic_pe)
        if intrinsic_pb is not None:
            methods.append(intrinsic_pb)
        if intrinsic_gordon is not None:
            methods.append(intrinsic_gordon)

        if methods:
            intrinsic_value = float(np.mean(methods))
            # BUG-009 FIX: Calculate current price safely
            # For profitable companies: P = PE * EPS
            # For loss-making companies: Use P/B as fallback
            if company.pe_ratio > 0 and company.eps > 0:
                current_price = company.pe_ratio * company.eps
            elif company.pb_ratio > 0 and company.book_value_per_share > 0:
                current_price = company.pb_ratio * company.book_value_per_share
            else:
                # Cannot calculate current price reliably
                current_price = None

            if current_price and current_price > 0:
                discount = (intrinsic_value / current_price) - 1
            else:
                discount = None
        else:
            intrinsic_value = None
            discount = None

        return {
            "intrinsic_pe": intrinsic_pe,
            "intrinsic_pb": intrinsic_pb,
            "intrinsic_gordon": intrinsic_gordon,
            "intrinsic_value": intrinsic_value,
            "discount_to_intrinsic": discount,
        }


def load_config(config_path: str) -> ValuationConfig:
    """
    Load valuation configuration from JSON file.

    The config file has a nested structure with valuation settings under
    the "valuation" key. This function parses the nested structure correctly.

    Expected config.json structure:
    {
        "valuation": {
            "weights": {
                "PE": 0.40,
                "PB": 0.25,
                "dividend": 0.15,
                "PEG": 0.20
            },
            "deeply_undervalued": 0.30,
            "undervalued": 0.10,
            "overvalued": -0.10,
            "deeply_overvalued": -0.30
        }
    }

    Args:
        config_path: Path to config JSON file

    Returns:
        ValuationConfig instance
    """
    with open(config_path) as f:
        config_dict = json.load(f)

    # BUG-013 FIX: Parse nested structure correctly
    # The config file has valuation settings under "valuation" key
    if "valuation" in config_dict:
        valuation_config = config_dict["valuation"]
    else:
        # Fallback: assume flat structure for backward compatibility
        valuation_config = config_dict

    # Extract weights from nested structure
    weights = valuation_config.get("weights", {})

    return ValuationConfig(
        pe_weight=weights.get("PE", 0.40),
        pb_weight=weights.get("PB", 0.25),
        dividend_weight=weights.get("dividend", 0.15),
        peg_weight=weights.get("PEG", 0.20),
        deeply_undervalued=valuation_config.get("deeply_undervalued", 0.30),
        undervalued=valuation_config.get("undervalued", 0.10),
        overvalued=valuation_config.get("overvalued", -0.10),
        deeply_overvalued=valuation_config.get("deeply_overvalued", -0.30),
    )


# Example usage and testing
if __name__ == "__main__":
    # Test with example data
    calculator = ValuationCalculator()

    # Example: A technology company that looks undervalued
    company = ValuationMetrics(
        pe_ratio=15.0,  # Below sector median of 25
        pb_ratio=2.5,  # At sector median
        dividend_yield=0.02,  # 2% vs sector 1.5%
        peg_ratio=1.2,  # Below sector median of 1.8
        eps=2.0,
        book_value_per_share=8.0,
        annual_dividend=0.4,
    )

    sector = SectorMetrics(pe_ratio=25.0, pb_ratio=2.5, dividend_yield=0.015, peg_ratio=1.8)

    valuation = calculator.calculate_valuation(company, sector)

    print("=== Valuation Analysis ===")
    print(f"Composite Score (V): {valuation.composite_score:.3f}")
    print(f"Interpretation: {valuation.interpretation}")
    print("\nComponent Scores:")
    for name, score in valuation.component_scores.items():
        print(f"  {name}: {score:.3f}")
    print("\nRelative Metrics:")
    print(f"  PE: {valuation.relative_pe:.2%}")
    print(f"  PB: {valuation.relative_pb:.2%}")
    print(f"  Dividend: {valuation.dividend_diff:.2%}")
    print(f"  PEG: {valuation.relative_peg:.2%}")

    # Intrinsic value calculation
    intrinsic = calculator.calculate_intrinsic_value(company, sector)
    print("\n=== Intrinsic Value ===")
    if intrinsic["intrinsic_value"]:
        print(f"Intrinsic Value: CNY{intrinsic['intrinsic_value']:.2f}")
        print(f"Discount to Intrinsic: {intrinsic['discount_to_intrinsic']:.2%}")
    else:
        print("Unable to calculate intrinsic value (insufficient data)")
