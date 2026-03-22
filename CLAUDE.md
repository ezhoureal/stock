# CLAUDE.md
## Project Overview

A Chinese stock trading system with multiple strategies and live trading infrastructure. The codebase consists of independent modules that can operate separately but share data infrastructure through the `common` module.

## Commands

### Setup and Installation

Uses uv for dependency management:

```bash
# Install uv if not already installed
curl -LsSf https://docs.astral.sh/uv | sh

# Install dependencies (creates virtual environment automatically)
uv sync
```

## Architecture

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

# Type check
uv run pyright .

# Run tests to verify changes
uv run pytest
```

**All code must pass both Ruff and Pyright with zero errors before committing.**

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
