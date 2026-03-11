# Chinese Stock Sentiment Trading System

A contrarian trading strategy for Chinese A-share stocks that combines sentiment analysis with fundamental valuation.

## Overview

**Strategy Philosophy:** Buy when the crowd is fearful but fundamentals are strong. Sell when the crowd is euphoric but fundamentals are stretched.

**Core Principle:**
- **BUY Signal:** Bearish sentiment + Undervalued fundamentals
- **SELL Signal:** Bullish sentiment + Overvalued fundamentals

## Components

### 1. Valuation Calculator (`valuation.py`)

Calculates intrinsic value and valuation scores relative to sector medians.

**Metrics Used:**
- P/E Ratio (Price to Earnings) - 40% weight
- P/B Ratio (Price to Book) - 25% weight
- Dividend Yield - 15% weight
- PEG Ratio (PE / Growth Rate) - 20% weight

**Valuation Score (V):**
- V > +0.30: Deeply undervalued
- +0.30 > V > +0.10: Undervalued
- -0.10 < V < +0.10: Fair value
- -0.10 > V > -0.30: Overvalued
- V < -0.30: Deeply overvalued

### 2. Sentiment Analyzer (`sentiment.py`)

Analyzes sentiment from multiple sources.

**Sources:**
- News (articles, headlines) - 40% weight
- Social Media (Weibo, 东方财富股吧) - 35% weight
- Search Volume (Baidu trends) - 15% weight
- Forum Activity (post count, velocity) - 10% weight

**Sentiment Score (S):**
- -5.0 to -3.0: Extreme bearish (panic)
- -3.0 to -1.5: Bearish
- -1.5 to +1.5: Neutral
- +1.5 to +3.0: Bullish
- +3.0 to +5.0: Extreme bullish (euphoria)

### 3. Signal Generator (`signals.py`)

Combines sentiment and valuation to generate trading signals.

**Signal Generation:**

**Buy Signal** (ALL must be true):
1. Sentiment < -1.5 OR rate of change < -1.0 (rapid deterioration)
2. Valuation > +0.10 (undervalued)
3. Sentiment > 1.5 std devs from 30-day mean

**Sell Signal** (ALL must be true):
1. Sentiment > +1.5 OR rate of change > +1.0 (rapid improvement)
2. Valuation < -0.10 (overvalued)
3. Sentiment > 1.5 std devs from 30-day mean

**Exit Conditions:**
- Stop-loss: 8%
- Take-profit: 15%
- Signal reversal: Sentiment or valuation moves back toward neutral

**Position Sizing:**
- Base size: 1% of portfolio
- Adjusted by signal strength (0-100)
- Maximum: 5% per position

## Quick Start

### Basic Usage

```python
from strategy import (
    ValuationCalculator,
    SentimentAnalyzer,
    SignalGenerator,
    ValuationMetrics,
    SectorMetrics,
    SentimentSource
)
from datetime import datetime

# Initialize components
valuation_calc = ValuationCalculator()
sentiment_analyzer = SentimentAnalyzer()
signal_generator = SignalGenerator(sentiment_analyzer, valuation_calc)

# Step 1: Calculate valuation
company = ValuationMetrics(
    pe_ratio=15.0,           # Price to Earnings
    pb_ratio=2.5,            # Price to Book
    dividend_yield=0.02,     # 2% dividend yield
    peg_ratio=1.2,           # PEG
    eps=2.0,                 # Earnings per share
    book_value_per_share=8.0,
    annual_dividend=0.4
)

sector = SectorMetrics(
    pe_ratio=25.0,           # Sector median P/E
    pb_ratio=2.5,            # Sector median P/B
    dividend_yield=0.015,    # Sector median dividend
    peg_ratio=1.8            # Sector median PEG
)

valuation = valuation_calc.calculate_valuation(company, sector)
print(f"Valuation Score (V): {valuation.composite_score:.3f}")
print(f"Interpretation: {valuation.interpretation}")

# Step 2: Analyze sentiment
sources = [
    SentimentSource('news', datetime.now(), -0.4, -0.4, 0.8, {}),
    SentimentSource('social', datetime.now(), -0.6, -0.6, 0.7, {}),
    SentimentSource('search', datetime.now(), -0.7, -0.7, 0.6, {}),
    SentimentSource('forum', datetime.now(), -0.5, -0.5, 0.5, {}),
]

sentiment = sentiment_analyzer.calculate_sentiment("600519.SH", sources)
print(f"Sentiment Score (S): {sentiment.smoothed_score:.2f}")
print(f"Interpretation: {sentiment.interpretation}")

# Step 3: Generate trading signal
signal = signal_generator.generate_signal(
    symbol="600519.SH",
    current_price=100.0,
    sentiment=sentiment,
    valuation=valuation,
    portfolio_value=100000.0
)

print(f"\n=== Trading Signal ===")
print(f"Type: {signal.signal_type}")
print(f"Strength: {signal.strength:.1f}")
print(f"Entry Price: ¥{signal.entry_price:.2f}")
print(f"Stop Loss: ¥{signal.stop_loss:.2f}")
print(f"Take Profit: ¥{signal.take_profit:.2f}")
print(f"Reasons: {signal.reasons}")
```

## Configuration

All parameters are configurable via `config.json`:

```json
{
  "sentiment": {
    "weights": {"news": 0.40, "social": 0.35, "search": 0.15, "forum": 0.10},
    "ema_alpha": 0.2,
    "roc_threshold": 1.0
  },
  "valuation": {
    "weights": {"PE": 0.40, "PB": 0.25, "dividend": 0.15, "PEG": 0.20},
    "undervalued_threshold": 0.10,
    "overvalued_threshold": -0.10
  },
  "signal": {
    "sentiment_threshold": 1.5,
    "min_deviation_std": 1.5,
    "stop_loss_pct": 0.08,
    "take_profit_pct": 0.15
  }
}
```

## Backtesting

To backtest the strategy:

```python
from backtest import Backtester

backtester = Backtester(
    strategy=signal_generator,
    start_date="2021-01-01",
    end_date="2024-12-31"
)

results = backtester.run()
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
print(f"Max Drawdown: {results.max_drawdown:.2%}")
print(f"Win Rate: {results.win_rate:.2%}")
```

## Risk Management

Built-in risk controls:

- **Position Size:** Max 5% per stock
- **Exposure Limits:** Max 30% long + 30% short
- **Sector Limits:** Max 25% per sector
- **Liquidity Filter:** Min ¥50M daily turnover
- **Stop-Loss:** 8% mandatory stop-loss
- **Correlation Filter:** Avoid highly correlated positions

## Data Requirements

**Daily:**
- Price data (OHLCV)
- Fundamental metrics (PE, PB, dividend, PEG)
- Sector medians
- Sentiment data from all sources

**Historical (for backtesting):**
- 5+ years of price and fundamental data
- Historical sentiment (if available) or reconstruction

## Testing

Run the test examples:

```bash
cd ~/trade/stocks/strategy

# Test valuation
python valuation.py

# Test sentiment
python sentiment.py

# Test signals
python signals.py
```

## File Structure

```
~/trade/stocks/strategy/
├── __init__.py          # Package initialization
├── valuation.py         # Valuation calculator
├── sentiment.py         # Sentiment analyzer
├── signals.py          # Signal generator
├── config.json         # Configuration parameters
├── DESIGN.md           # Detailed design document
└── README.md           # This file
```

## Performance Targets

- **Sharpe Ratio:** > 1.5
- **Max Drawdown:** < 25%
- **Win Rate:** > 55%
- **Average Win/Loss Ratio:** > 1.3
- **Annualized Return:** > 15%

## Benchmarks

- SSE Composite Index (000001.SH)
- CSI 300 Index (000300.SH)

## Future Enhancements

1. Machine learning for sentiment prediction
2. Multi-factor model (add technical indicators)
3. Dynamic sector rotation
4. Adaptive thresholds based on market volatility
5. Intraday signals for higher-frequency trading

## References

- Graham, B., & Dodd, D. (1934). Security Analysis
- Baker, M., & Wurgler, J. (2007). Investor Sentiment in the Stock Market
- Fama, E. F., & French, K. R. (1993). Common Risk Factors in Stock Returns

## License

Internal use only - OpenClaw Trading System

## Version

Version 1.0.0 - 2026-03-08
