# Chinese Stock Sentiment Trading System - Algorithm Design Document

## Overview

This document describes the design of a sentiment-based trading algorithm for Chinese A-share stocks. The strategy combines fundamental valuation metrics with market sentiment to generate contrarian trading signals.

## Core Philosophy

**Contrarian Approach:** Buy when sentiment is pessimistic but fundamentals are solid (undervalued). Sell when sentiment is euphoric but fundamentals are stretched (overvalued).

**Rationale:**
- Sentiment extremes often precede reversals
- Fundamentals provide a safety margin (value investing principle)
- Combining both reduces false signals compared to using either alone

---

## 1. Sentiment Scoring Model

### 1.1 Sentiment Sources

| Source | Data Point | Weight | Collection Frequency |
|--------|-----------|--------|---------------------|
| News | Article sentiment (BERT/NLP) | 40% | Hourly |
| Social Media | Weibo, 东方财富股吧 posts | 35% | Hourly |
| Search Volume | Baidu search trends for stock symbol | 15% | Daily |
| Forum Activity | Post count, comment velocity | 10% | Hourly |

### 1.2 Sentiment Range

**Scale:** -5.0 (extremely bearish) to +5.0 (extremely bullish)

**Interpretation:**
| Range | Interpretation |
|-------|---------------|
| -5.0 to -3.0 | Extreme bearish (panic) |
| -3.0 to -1.5 | Bearish |
| -1.5 to +1.5 | Neutral |
| +1.5 to +3.0 | Bullish |
| +3.0 to +5.0 | Extreme bullish (euphoria) |

### 1.3 Sentiment Scoring Formula

For each source `i`:
```
sentiment_i = normalized_sentiment_i * weight_i
```

Where `normalized_sentiment_i` is in [-1, 1] and weight_i sums to 1.0.

**Total Sentiment Score:**
```
S_total = sum(sentiment_i for all i) * 5
```

Example: If all sources are mildly bullish (average 0.3), S_total = 0.3 * 5 = 1.5

### 1.4 Sentiment Smoothing

To avoid noise, apply exponential moving average (EMA) with α = 0.2:

```
S_smoothed[t] = α * S_total[t] + (1-α) * S_smoothed[t-1]
```

### 1.5 Sentiment Rate of Change

Calculate momentum of sentiment (S_roc):

```
S_roc[t] = S_smoothed[t] - S_smoothed[t-1]
```

This helps identify:
- **Rapid deterioration:** S_roc < -1.0 (potential crash scenario)
- **Rapid improvement:** S_roc > +1.0 (potential breakout)

---

## 2. Intrinsic Value Estimation

### 2.1 Valuation Metrics

| Metric | Calculation | Weight |
|--------|-------------|--------|
| P/E Ratio | price / eps | 40% |
| P/B Ratio | price / book_value_per_share | 25% |
| Dividend Yield | annual_dividend / price | 15% |
| PEG Ratio | P/E / earnings_growth_rate | 20% |

### 2.2 Sector-Based Valuation

For each metric, compare to sector median:

```
relative_metric = (company_metric / sector_median) - 1
```

Examples:
- Company P/E = 15, Sector median = 20 → relative_PE = (15/20) - 1 = -0.25 (25% cheaper)
- Company P/B = 1.8, Sector median = 1.5 → relative_PB = (1.8/1.5) - 1 = +0.20 (20% premium)

### 2.3 Undervalued/Overvalued Score

**Composite Valuation Score (V):**

```
V = (relative_PE * -0.40) +
    (relative_PB * -0.25) +
    (dividend_yield_diff * 0.15) +
    (relative_PEG * -0.20)
```

**Note:** Inverting relative PE/PB/PEG because lower = better (undervalued)

**V Range:**
| V Range | Interpretation |
|---------|---------------|
| V < -0.30 | Severely overvalued |
| -0.30 ≤ V < -0.10 | Overvalued |
| -0.10 ≤ V < +0.10 | Fair value |
| +0.10 ≤ V < +0.30 | Undervalued |
| V ≥ +0.30 | Deeply undervalued |

**Example Calculation:**
- relative_PE = -0.25 (25% cheaper)
- relative_PB = +0.10 (10% premium)
- dividend_yield_diff = +0.02 (2% higher than sector)
- relative_PEG = -0.15 (PEG 15% cheaper)

V = (-0.25 * -0.40) + (0.10 * -0.25) + (0.02 * 0.15) + (-0.15 * -0.20)
  = +0.10 - 0.025 + 0.003 + 0.03
  = +0.108 → Slightly undervalued

### 2.4 Valuation Trend

Track V over time to identify improving/worsening fundamentals:

```
V_trend[t] = V[t] - V[t-1]
```

---

## 3. Signal Generation Logic

### 3.1 Primary Signals

#### Buy Signal

**Condition (ALL must be true):**

1. Sentiment is bearish or rapidly deteriorating:
   - `S_smoothed < -1.5` OR
   - `S_roc < -1.0` (rapid sentiment crash)

2. Fundamentals are undervalued:
   - `V > +0.10` (undervalued) OR
   - `V > 0 AND V_trend > 0` (approaching undervaluation)

3. Minimum deviation thresholds:
   - Sentiment must be at least 1.5 standard deviations below 30-day mean
   - Valuation must be at least 10% above fair value

**Buy Strength (0-100):**
```
buy_strength = (
    (max(-S_smoothed, 0) / 3.5) * 0.5 +
    (min(V, 0.5) / 0.5) * 0.5
) * 100
```

#### Sell Signal

**Condition (ALL must be true):**

1. Sentiment is bullish or rapidly improving:
   - `S_smoothed > +1.5` OR
   - `S_roc > +1.0` (rapid sentiment spike)

2. Fundamentals are overvalued:
   - `V < -0.10` (overvalued) OR
   - `V < 0 AND V_trend < 0` (approaching overvaluation)

3. Minimum deviation thresholds:
   - Sentiment must be at least 1.5 standard deviations above 30-day mean
   - Valuation must be at least 10% below fair value

**Sell Strength (0-100):**
```
sell_strength = (
    (max(S_smoothed, 0) / 3.5) * 0.5 +
    (min(-V, 0.5) / 0.5) * 0.5
) * 100
```

### 3.2 Signal Confirmation

To reduce false signals, require confirmation:

**Buy Confirmation:**
- Signal persists for 2+ consecutive periods (e.g., 2 days)
- Price action shows stabilization (not free-falling)

**Sell Confirmation:**
- Signal persists for 2+ consecutive periods
- Price action shows weakness (volume spike with price decline)

### 3.3 Exit Conditions

#### Stop-Loss Exit
```
if (entry_type == "BUY" and price < entry_price * 0.92) OR
   (entry_type == "SELL" and price > entry_price * 1.08):
    EXIT with stop-loss
```
- 8% stop-loss for long positions
- 8% stop-loss for short positions

#### Take-Profit Exit
```
if (entry_type == "BUY" and price > entry_price * 1.15) OR
   (entry_type == "SELL" and price < entry_price * 0.85):
    EXIT with take-profit
```
- 15% take-profit for long positions
- 15% take-profit for short positions

#### Signal Reversal Exit
```
if (entry_type == "BUY" and S_smoothed > +1.0) OR
   (entry_type == "BUY" and V < -0.05):
    EXIT (sentiment improved or valuation deteriorated)

if (entry_type == "SELL" and S_smoothed < -1.0) OR
   (entry_type == "SELL" and V > +0.05):
    EXIT (sentiment deteriorated or valuation improved)
```

### 3.4 Position Sizing

**Base Size:** 1% of portfolio per signal

**Adjustments:**
```
adjusted_size = base_size *
                signal_strength *  # 0.5 to 1.5
                (1 / max_correlation)  # reduce for correlated positions
```

**Max Position:** 5% of portfolio per stock
**Max Exposure:** 30% long + 30% short = 60% gross exposure

---

## 4. Risk Management

### 4.1 Sector Concentration
- Max 25% of portfolio in any single sector
- Sector classification using China SW industry codes

### 4.2 Correlation Limits
- Avoid taking positions in highly correlated stocks simultaneously
- Use daily returns correlation > 0.7 as threshold

### 4.3 Liquidity Filter
- Minimum 30-day average daily turnover: ¥50 million
- Avoid illiquid small caps

### 4.4 Market Condition Filter
**Bear Market (SSE Composite < 200-day MA):**
- Only take BUY signals (value opportunity)
- Hold size smaller

**Bull Market (SSE Composite > 200-day MA):**
- Both BUY and SELL signals allowed
- Can be more aggressive

---

## 5. Backtesting Considerations

### 5.1 Data Requirements
- **Price Data:** Daily OHLCV (5+ years)
- **Fundamental Data:** Quarterly financials, sector medians
- **Sentiment Data:** Historical news, social media, search volume (if available)

### 5.2 Evaluation Metrics
- Sharpe Ratio (target: > 1.5)
- Maximum Drawdown (target: < 25%)
- Win Rate (target: > 55%)
- Average Win/Loss Ratio (target: > 1.3)
- Annualized Return (target: > 15%)
- Alpha vs. SSE Composite

### 5.3 Benchmark
- SSE Composite Index (000001.SH)
- CSI 300 Index (000300.SH)

### 5.4 Transaction Costs
- Commission: 0.03% per side
- Stamp duty: 0.1% (sell only)
- Slippage: 0.2% per trade

---

## 6. Implementation Notes

### 6.1 Language & Libraries
- **Python 3.10+**
- **pandas** - Data manipulation
- **numpy** - Numerical computations
- **scipy** - Statistical functions
- **scikit-learn** - Machine learning (for sentiment analysis)
- **tushare** - Chinese stock data (optional, for fetching fundamentals)

### 6.2 Data Flow
```
1. Fetch price and fundamental data
2. Calculate sentiment scores from external sources
3. Compute valuation metrics and V score
4. Generate signals based on conditions
5. Apply risk filters and position sizing
6. Output: signals.csv with columns [date, symbol, signal, strength, entry_price, stop_loss, take_profit]
```

### 6.3 Configuration Parameters
All thresholds and weights should be configurable via `config.json`:

```json
{
  "sentiment": {
    "weights": {"news": 0.4, "social": 0.35, "search": 0.15, "forum": 0.1},
    "ema_alpha": 0.2,
    "roc_threshold": 1.0
  },
  "valuation": {
    "weights": {"PE": 0.4, "PB": 0.25, "dividend": 0.15, "PEG": 0.2},
    "undervalued_threshold": 0.10,
    "overvalued_threshold": -0.10
  },
  "signal": {
    "sentiment_threshold": 1.5,
    "min_deviation_std": 1.5,
    "confirmation_periods": 2,
    "stop_loss_pct": 0.08,
    "take_profit_pct": 0.15
  },
  "risk": {
    "base_position_size": 0.01,
    "max_position_size": 0.05,
    "max_long_exposure": 0.30,
    "max_short_exposure": 0.30,
    "max_sector_exposure": 0.25,
    "min_daily_turnover_million": 50
  }
}
```

---

## 7. Future Enhancements

1. **Machine Learning Integration:** Train ML model to predict sentiment using historical data
2. **Multi-Factor Model:** Add technical factors (momentum, mean reversion)
3. **Sector Rotation:** Adjust sector exposures based on macro indicators
4. **Dynamic Thresholds:** Adapt thresholds based on market volatility (VIX-like)
5. **Intraday Signals:** Extend to hourly signals for higher-frequency trading

---

## 8. References

- Buffett, W. (1984). The Superinvestors of Graham-and-Doddsville
- Jegadeesh, N., & Titman, S. (1993). Returns to Buying Winners and Selling Losers
- Baker, M., & Wurgler, J. (2007). Investor Sentiment in the Stock Market
- Fama, E. F., & French, K. R. (1993). Common Risk Factors in Stock Returns

---

## Document Version

- **Version:** 1.0
- **Date:** 2026-03-08
- **Author:** Algorithm Designer (OpenClaw Subagent)
