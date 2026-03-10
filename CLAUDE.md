# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Chinese stock trading system with multiple strategies and live trading infrastructure. The codebase consists of four independent modules that can operate separately but share data infrastructure.

## Commands

### Setup and Installation

Each module has its own `requirements.txt`:

```bash
# Data pipeline
pip install -r data/requirements.txt

# Sentiment arbitrage (requires CUDA GPU)
pip install -r sentiment_arbitrage/requirements.txt

# Broker integration
pip install -r live/broker/requirements.txt
```

### Running the System

**Sentiment Arbitrage System:**
```bash
cd sentiment_arbitrage
python main.py                                    # Run demo with synthetic data
python main.py --config configs/default_config.json  # Custom config
python tests/test_framework.py                    # Run tests
```

**Strategy Module (Contrarian Trading):**
```bash
cd strategy
python valuation.py      # Test valuation calculator
python sentiment.py      # Test sentiment analyzer
python signals.py        # Test signal generator
```

**Data Pipeline:**
```bash
cd data
python init_db.py                       # Initialize DuckDB database
python collect_csi300.py                # Fetch CSI 300 constituents
python collect_historical_prices.py     # Collect price data
python collect_historical_prices.py --years 3  # Extended history
```

**Broker/Live Trading:**
```bash
cd live/broker/python
python main.py --paper-trading          # Paper trading mode
python test_simple.py                   # Mock broker test
```

## Architecture

```
stock/
├── sentiment_arbitrage/    # GPU-optimized vectorized sentiment arbitrage (500+ stocks)
│   ├── src/
│   │   ├── kalman_filter.py       # Square-root Kalman filter for state estimation
│   │   ├── z_scoring.py           # Vectorized z-score calculators (rolling/exp/cross-sectional)
│   │   ├── echo_chamber.py        # Orthogonalization to remove market-wide effects
│   │   ├── signal_generation.py   # Entry/exit signals with risk management
│   │   └── sentiment_extraction.py # Distil-FinBERT + Triton integration
│   └── main.py                    # Main integration module
│
├── strategy/               # Contrarian strategy (sentiment + fundamental valuation)
│   ├── valuation.py        # Intrinsic value calculator (P/E, P/B, PEG, dividend)
│   ├── sentiment.py        # Multi-source sentiment aggregation (news, social, search)
│   └── signals.py          # Signal generator combining sentiment + valuation
│
├── data/                   # Data collection pipeline (DuckDB storage)
│   ├── init_db.py          # Database schema initialization
│   ├── collect_csi300.py   # CSI 300 constituent collection (Akshare)
│   └── collect_historical_prices.py  # Historical price data (Baostock)
│
└── live/broker/            # Live trading infrastructure
    └── python/
        ├── broker/         # Broker abstraction (Futu API + mock for testing)
        ├── order/          # Order management with state machines
        ├── position/       # Position tracking and P&L
        └── risk/           # Risk controls and position limits
```

## Key Architectural Patterns

### Sentiment Arbitrage System
Multi-layer pipeline: Data Ingestion → Sentiment Extraction (Distil-FinBERT/Triton) → State Estimation (Kalman Filter) → Signal Processing (Z-Scoring + Echo Chamber Elimination) → Signal Generation → Execution

Mathematical model: `P_t = β * S_t + ε` where β is estimated via Kalman filter. Uses CuPy for GPU acceleration. Performance target: <100ms end-to-end latency.

### Strategy Module (Contrarian)
- **BUY**: Bearish sentiment (< -1.5) + Undervalued fundamentals (V > +0.10)
- **SELL**: Bullish sentiment (> +1.5) + Overvalued fundamentals (V < -0.10)
- Risk controls: 8% stop-loss, 15% take-profit, max 5% position size

### Data Layer
DuckDB for analytics-optimized storage. Primary data sources: Akshare (free, scraping-based) and Baostock (free, API-based). Universe: CSI 300.

### Broker Integration
Futu OpenAPI recommended. Broker abstraction layer allows mock testing. Paper trading environment available.

## Configuration

Each module has its own config:
- `sentiment_arbitrage/configs/default_config.json` - Kalman parameters, z-score thresholds, signal thresholds
- `strategy/config.json` - Sentiment weights, valuation weights, risk limits
- `data/config.json` - Data source settings
- `live/broker/.env.example` - Broker connection, risk limits (copy to `.env`)

## Environment Variables

For live trading, copy `live/broker/.env.example` to `.env`:
- `BROKER_TYPE=futu`
- `PAPER_TRADING=true` (for testing)
- `FUTU_HOST/PORT` - OpenD gateway connection
- Risk limits: `MAX_POSITION_SIZE`, `MAX_DAILY_LOSS`, `STOP_LOSS_PERCENT`

## Python Version

Python 3.13 (specified in `.python-version`)

## GPU Requirements

The `sentiment_arbitrage` module requires NVIDIA GPU with CUDA 12.x (uses CuPy). Install appropriate CuPy version for your CUDA/ROCm setup.
