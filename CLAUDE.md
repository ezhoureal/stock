# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Chinese stock trading system with multiple strategies and live trading infrastructure. The codebase consists of independent modules that can operate separately but share data infrastructure through the `common` module.

## Commands

### Setup and Installation

Uses uv for dependency management with optional dependency groups:

```bash
# Install uv if not already installed
curl -LsSf https://docs.astral.sh/uv | sh

# Create virtual environment and install dependencies
uv venv

# Install with specific dependency groups
uv pip install -e ".[data,sentiment,broker,dev]"  # All optional deps
uv pip install -e ".[data]"                       # Data pipeline only
uv pip install -e ".[sentiment]"                  # Sentiment arbitrage only
uv pip install -e ".[broker]"                     # Broker integration only
uv pip install -e ".[dev]"                        # Development tools only

# Install everything (core + all optional)
uv pip install -e ".[all]"
```

### Running the System

All commands should be run from the project root unless otherwise noted:

**Sentiment Strategy (Contrarian Trading):**
```bash
uv run python sentiment_strategy/valuation.py    # Test valuation calculator
uv run python sentiment_strategy/sentiment.py    # Test sentiment analyzer
uv run python sentiment_strategy/signals.py      # Test signal generator
uv run python sentiment_strategy/example.py      # Full demo
```

**Data Pipeline:**
```bash
uv run python data/init_db.py                       # Initialize DuckDB database
uv run python data/collect_csi300.py                # Fetch CSI 300 constituents
uv run python data/collect_historical_prices.py     # Collect price data
uv run python data/collect_historical_prices.py -- --years 3  # Extended history
```

**Broker/Live Trading (run from broker/python/):**
```bash
cd broker/python
uv run python test_simple.py           # Mock broker test
uv run python main.py --paper-trading  # Paper trading mode
```

**Examples:**
```bash
uv run python examples/run_trading_system.py      # Full system demo
uv run python examples/test_system_mock.py        # Mock system test
uv run python examples/test_broker_integration.py # Broker integration test
```

### Development

```bash
# Run all tests (ignore GPU-dependent tests on machines without CUDA)
uv run pytest --ignore=high_freq_sentiment

# Run specific test file
uv run pytest broker/python/test_simple.py

# Run specific test function
uv run pytest examples/test_system_mock.py::test_trading_system_mock -v

# Lint and format code (REQUIRED before commits)
uv run ruff check .           # Check for issues
uv run ruff check --fix .     # Auto-fix issues
uv run ruff format .          # Format code

# Alternative linter
uv run flake8 .
```

## Architecture

```
stock/
├── common/                    # Shared infrastructure (core module)
│   ├── types.py               # Core data types (Signal, Position, Order, Trade, etc.)
│   ├── interfaces.py          # Abstract interfaces (DataProvider, SignalGenerator, etc.)
│   ├── config.py              # Configuration dataclasses
│   ├── signal_router.py       # Routes signals to execution
│   ├── strategy_adapters.py   # Adapters for different strategies
│   └── orchestrator.py        # TradingSystem class, quick_backtest helper
│
├── sentiment_strategy/        # Contrarian strategy (sentiment + fundamental valuation)
│   ├── valuation.py           # Intrinsic value calculator (P/E, P/B, PEG, dividend)
│   ├── sentiment.py           # Multi-source sentiment aggregation
│   ├── signals.py             # Signal generator combining sentiment + valuation
│   ├── example.py             # Demo script
│   └── config.json            # Strategy configuration
│
├── backtest/                  # Backtesting engine
│   └── engine.py              # BacktestEngineImpl with realistic execution simulation
│
├── data/                      # Data collection pipeline
│   ├── init_db.py             # DuckDB schema initialization
│   ├── collect_csi300.py      # CSI 300 constituent collection
│   ├── collect_historical_prices.py  # Historical price data
│   ├── collect_sentiment.py   # Sentiment data collection
│   └── providers/             # Data providers (DuckDB, etc.)
│
├── broker/                    # Live trading infrastructure
│   ├── .env                   # Broker configuration (copy from .env.example)
│   └── python/
│       ├── broker/            # Broker abstraction (mock + Futu API)
│       │   ├── base.py        # Base broker interface
│       │   └── mock.py        # Mock broker for testing
│       ├── order/             # Order management and models
│       ├── position/          # Position tracking and P&L
│       ├── risk/              # Risk controls and position limits
│       ├── main.py            # Entry point for paper trading
│       └── test_simple.py     # Mock broker test
│
├── high_freq_sentiment/       # High-frequency sentiment processing
├── examples/                  # Usage examples and integration tests
└── config/                    # Global configuration files
```

## Key Architectural Patterns

### Common Module (Core)
The `common` module provides shared infrastructure:
- **Types**: `TradingSignal`, `Position`, `Order`, `Trade`, `Bar`, `SignalType`
- **Interfaces**: `DataProvider`, `SignalGenerator`, `ExecutionClient`, `BacktestEngine`
- **TradingSystem**: Unified entry point via `common.TradingSystem` or `common.quick_backtest()`

```python
from common import TradingSystem, quick_backtest

# Create and run the system
system = TradingSystem()
system.initialize()
portfolio = system.run_once()

# Run a quick backtest
result = quick_backtest(strategy_name="sentiment_arbitrage", days=365)
```

### Sentiment Strategy (Contrarian)
- **BUY**: Bearish sentiment (< -1.5) + Undervalued fundamentals (V > +0.10)
- **SELL**: Bullish sentiment (> +1.5) + Overvalued fundamentals (V < -0.10)
- Risk controls: 8% stop-loss, 15% take-profit, max 5% position size

### Backtest Engine
Realistic execution simulation with:
- Multiple fill models (next_open, close, vwap)
- Cost modeling (commission, slippage, stamp duty for China A-shares)
- Performance metrics (Sharpe, drawdown, win rate)

### Broker Integration
Broker abstraction layer with mock for testing. Run from `broker/python/` directory:
```bash
cd broker/python
uv run python main.py --paper-trading
```

## Configuration

Each module has its own config:
- `sentiment_strategy/config.json` - Sentiment weights, valuation weights, risk limits
- `data/config.json` - Data source settings
- `broker/.env` - Broker connection, risk limits (copy from `.env.example`)

## Environment Variables

For live trading with Futu, configure `broker/.env`:
- `BROKER_TYPE=futu` or `mock`
- `PAPER_TRADING=true` (for testing)
- `FUTU_HOST/PORT` - OpenD gateway connection (default: 127.0.0.1:11111)
- Risk limits: `MAX_POSITION_SIZE`, `MAX_DAILY_LOSS`, `STOP_LOSS_PERCENT`

## Coding Guidelines

### Code Quality (REQUIRED)
Always run these before committing Python code:

```bash
# Fix linting issues and format
uv run ruff check --fix .
uv run ruff format .

# Run tests to verify changes
uv run pytest
```

### Ruff Configuration
Project uses ruff with settings in `pyproject.toml`:
- Line length: 100
- Target: Python 3.13
- Enabled rules: E, F, W, I, N, UP, B (pycodestyle, pyflakes, warnings, isort, naming, upgrade, bugbear)

### Python Version
Python 3.13 (specified in `.python-version`)

### Type Hints
Use modern Python 3.13 type hints:
```python
# Prefer
def func(x: int | None) -> list[str]:

# Over
def func(x: Optional[int]) -> List[str]:
```

### Import Style
Use absolute imports from package root:
```python
from common.types import TradingSignal, Position
from sentiment_strategy.signals import SignalGenerator
```

## GPU Requirements

The `high_freq_sentiment` module requires NVIDIA GPU with CUDA 12.x (uses CuPy). Install appropriate CuPy version for your CUDA setup.
