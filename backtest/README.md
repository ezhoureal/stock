# Backtest Module

A comprehensive backtesting framework for testing trading strategies against historical data with realistic execution simulation.

## Overview

The backtest module provides a production-ready backtesting engine that simulates strategy performance with realistic market conditions. It supports multiple fill models, accurate cost modeling for China A-shares, and comprehensive performance metrics.

## Key Features

- **Multiple Fill Models**: Choose between `next_open`, `close`, and `vwap` execution simulation
- **Realistic Cost Modeling**: Includes commission, slippage, and China A-shares stamp duty
- **Position Tracking**: Full long and short position management with P&L calculation
- **Performance Metrics**: Sharpe ratio, maximum drawdown, win rate, profit factor, and more
- **Risk Controls**: Maximum drawdown stop, position size limits
- **Result Persistence**: Save trades, equity curves, and signals to CSV files
- **System Integration**: Works seamlessly with the `TradingSystem` orchestrator

## Architecture

```
backtest/
├── __init__.py          # Module exports
└── engine.py            # BacktestEngineImpl and run_backtest function
```

### Core Components

#### BacktestEngineImpl

The main backtesting engine that implements the `BacktestEngine` interface. It orchestrates:

1. **Data Loading**: Fetches historical price data via `DataProvider`
2. **Signal Generation**: Calls strategy's `generate_signals()` for each trading date
3. **Order Processing**: Converts signals to orders with configurable fill models
4. **Position Management**: Tracks open positions and calculates P&L
5. **Metrics Calculation**: Computes performance statistics at backtest completion

#### BacktestState

Internal dataclass that tracks backtest execution state:
- Cash balance and positions
- Equity curve history
- Trade history
- Pending orders
- Drawdown tracking

#### BacktestResult

Container for all backtest results (defined in `common/interfaces.py`):
- Capital metrics (initial, final, returns)
- Risk metrics (Sharpe ratio, max drawdown)
- Trade statistics (win rate, profit factor)
- Historical data (trades, equity curve, signals)

## Configuration

The backtest engine is configured via `BacktestConfig` (from `common/config.py`):

```python
from common.config import BacktestConfig

config = BacktestConfig(
    # Capital
    initial_capital=1_000_000.0,    # Starting capital (default: 1,000,000 CNY)
    benchmark="csi300",              # Benchmark for comparison

    # Trading Costs
    commission_rate=0.0003,          # 0.03% commission
    min_commission=5.0,              # Minimum 5 CNY per trade
    slippage_rate=0.001,             # 0.1% slippage
    stamp_duty=0.001,                # 0.1% stamp duty (China A-shares, sell only)

    # Execution
    fill_model="next_open",          # "next_open", "close", or "vwap"
    partial_fills=False,             # Enable partial order fills

    # Data
    price_field="adj_close",         # "close" or "adj_close"
    handle_missing_data="skip",      # "skip", "fill", or "error"

    # Risk
    max_position_pct=0.10,           # Max 10% per position
    max_drawdown_stop=0.20,          # Stop at 20% drawdown (None to disable)

    # Output
    save_trades=True,                # Save trade history to CSV
    save_equity_curve=True,          # Save equity curve to CSV
    save_signals=True,               # Save signal history to CSV
    output_dir="backtest_results",   # Output directory
)
```

### Fill Models

| Model | Description | Use Case |
|-------|-------------|----------|
| `next_open` | Uses next day's opening price | Conservative, realistic for daily strategies |
| `close` | Uses same day's closing price | For intraday signal generation |
| `vwap` | Simulates VWAP with small premium/discount | For large position sizing |

### Cost Modeling

The engine models realistic trading costs:

1. **Commission**: Applied to both buys and sells
   - `commission = max(notional * commission_rate, min_commission)`

2. **Slippage**: Applied based on trade direction
   - Buy: `fill_price = price * (1 + slippage_rate)`
   - Sell: `fill_price = price * (1 - slippage_rate)`

3. **Stamp Duty** (China A-shares): Applied only to sells
   - `stamp_duty = notional * stamp_duty_rate`

## Usage Examples

### Basic Usage

```python
from datetime import datetime, timedelta
from backtest import BacktestEngineImpl, run_backtest
from common.config import BacktestConfig

# Using the convenience function
result = run_backtest(
    strategy=my_strategy,
    symbols=["600519.SH", "000858.SZ", "601318.SH"],
    start=datetime(2023, 1, 1),
    end=datetime(2023, 12, 31),
    data_provider=data_provider,
    initial_capital=1_000_000.0,
)

print(result.summary())
```

### With Custom Configuration

```python
from backtest import BacktestEngineImpl
from common.config import BacktestConfig

# Create custom configuration
config = BacktestConfig(
    initial_capital=500_000.0,
    commission_rate=0.0002,
    min_commission=3.0,
    slippage_rate=0.0005,
    fill_model="vwap",
    max_drawdown_stop=0.15,  # Stop at 15% drawdown
    save_trades=True,
    output_dir="my_backtests",
)

# Create engine with config
engine = BacktestEngineImpl(data_provider, config)

# Run backtest
result = engine.run(
    strategy=my_strategy,
    symbols=symbols,
    start=start_date,
    end=end_date,
    initial_capital=500_000.0,
)
```

### Integration with TradingSystem

```python
from common import TradingSystem, create_system, quick_backtest

# Method 1: Using TradingSystem
system = create_system()
result = system.run_backtest(
    strategy_name="sentiment_arbitrage",
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2023, 12, 31),
    initial_capital=1_000_000.0,
)
print(result.summary())

# Method 2: Quick backtest with defaults
result = quick_backtest(
    strategy_name="sentiment_arbitrage",
    days=365,
    initial_capital=500_000.0,
)
print(result.summary())
```

### Custom Strategy Backtest

```python
from datetime import datetime, timedelta
from backtest import BacktestEngineImpl
from common import SignalGenerator, TradingSignal, SignalType

class MyStrategy(SignalGenerator):
    @property
    def name(self) -> str:
        return "my_strategy"

    @property
    def time_horizon(self) -> str:
        return "medium_term"

    def generate_signals(self, symbols, as_of, data_provider):
        signals = []
        lookback = as_of - timedelta(days=30)
        prices = data_provider.get_prices(symbols, lookback, as_of)

        for symbol in symbols:
            try:
                symbol_prices = prices.xs(symbol, level=0)["close"]
                if len(symbol_prices) < 20:
                    continue

                # Your signal logic here
                ma20 = symbol_prices.rolling(20).mean().iloc[-1]
                current_price = symbol_prices.iloc[-1]

                if current_price > ma20 * 1.02:
                    signals.append(TradingSignal(
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        timestamp=as_of,
                        source=self.name,
                        strength=60.0,
                        confidence=0.7,
                        entry_price=float(current_price),
                        stop_loss=float(current_price * 0.95),
                        take_profit=float(current_price * 1.10),
                    ))
            except Exception:
                continue

        return signals

    def update(self, new_data): pass
    def get_state(self): return {}
    def set_state(self, state): pass
    def get_required_data(self): return ["prices"]

# Run backtest with custom strategy
engine = BacktestEngineImpl(data_provider)
result = engine.run(
    strategy=MyStrategy(),
    symbols=symbols,
    start=start_date,
    end=end_date,
)
```

## Performance Metrics

The `BacktestResult` object contains comprehensive performance metrics:

### Return Metrics

| Metric | Description |
|--------|-------------|
| `initial_capital` | Starting capital |
| `final_capital` | Ending capital |
| `total_return` | Total return as decimal (e.g., 0.15 = 15%) |
| `annualized_return` | Annualized return rate |

### Risk Metrics

| Metric | Description |
|--------|-------------|
| `sharpe_ratio` | Risk-adjusted return (annualized, risk-free rate = 0) |
| `max_drawdown` | Maximum peak-to-trough decline as decimal |

### Trade Statistics

| Metric | Description |
|--------|-------------|
| `total_trades` | Total number of trades executed |
| `win_rate` | Percentage of profitable trades |
| `profit_factor` | Gross profit / Gross loss |

### Historical Data

| Attribute | Description |
|-----------|-------------|
| `trades` | List of all `Trade` objects |
| `equity_curve` | Daily equity values with date, cash, and position values |
| `signals` | List of all `TradingSignal` objects generated |

### Accessing Results

```python
# Print summary
print(result.summary())

# Access individual metrics
print(f"Total Return: {result.total_return:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.max_drawdown:.2%}")
print(f"Win Rate: {result.win_rate:.2%}")

# Convert to dictionary
metrics = result.to_dict()

# Analyze trades
for trade in result.trades:
    print(f"{trade.symbol}: {trade.side} {trade.quantity} @ {trade.price}")

# Analyze equity curve
import pandas as pd
equity_df = pd.DataFrame(result.equity_curve)
equity_df.plot(x='date', y='equity')
```

## Output Files

When `save_trades`, `save_equity_curve`, or `save_signals` is enabled, the engine saves CSV files to the output directory:

```
backtest_results/
├── strategy_name_equity_20240115_143022.csv    # Equity curve
├── strategy_name_trades_20240115_143022.csv    # Trade history
└── strategy_name_signals_20240115_143022.csv   # Signal history
```

### Equity Curve Format

| Column | Description |
|--------|-------------|
| `date` | Trading date |
| `equity` | Total portfolio equity |
| `cash` | Cash balance |
| `positions_value` | Value of open positions |

### Trades Format

| Column | Description |
|--------|-------------|
| `trade_id` | Unique trade identifier |
| `symbol` | Stock symbol |
| `side` | "BUY" or "SELL" |
| `quantity` | Number of shares |
| `price` | Execution price |
| `timestamp` | Execution timestamp |
| `commission` | Commission paid |
| `source_signal` | Strategy that generated the signal |

## Signal Processing Flow

1. **Signal Generation**: Strategy generates `TradingSignal` objects
2. **Signal Classification**:
   - Entry signals: `SignalType.BUY` or `SignalType.SELL`
   - Exit signals: `SignalType.EXIT`, `SignalType.EXIT_LONG`, `SignalType.EXIT_SHORT`
3. **Position Sizing**:
   - Use `signal.quantity` if specified
   - Use `signal.position_size` as fraction of equity
   - Default to 2% of cash if not specified
4. **Execution**:
   - Calculate fill price based on fill model
   - Apply slippage
   - Deduct commission and stamp duty
5. **Position Management**:
   - Create `Position` object for entries
   - Close position and realize P&L for exits

## Risk Controls

### Maximum Drawdown Stop

Set `max_drawdown_stop` to halt backtesting when drawdown exceeds threshold:

```python
config = BacktestConfig(
    max_drawdown_stop=0.20,  # Stop at 20% drawdown
)
```

### Position Size Limits

The engine respects position size limits from both config and signals:

```python
# Global limit
config = BacktestConfig(max_position_pct=0.10)  # Max 10% per position

# Per-signal limit
signal = TradingSignal(
    symbol="600519.SH",
    signal_type=SignalType.BUY,
    position_size=0.05,  # 5% of portfolio
    ...
)
```

## Integration Points

### With DataProvider

The backtest engine requires a `DataProvider` implementation:

```python
from data.providers import DuckDBDataProvider

data_provider = DuckDBDataProvider(data_config)
engine = BacktestEngineImpl(data_provider, backtest_config)
```

### With SignalGenerator

Strategies must implement the `SignalGenerator` interface:

```python
class MyStrategy(SignalGenerator):
    @property
    def name(self) -> str: ...

    @property
    def time_horizon(self) -> str: ...

    def generate_signals(self, symbols, as_of, data_provider) -> list[TradingSignal]: ...

    def update(self, new_data) -> None: ...
    def get_state(self) -> dict: ...
    def set_state(self, state) -> None: ...
    def get_required_data(self) -> list[str]: ...
```

### With TradingSystem

The `TradingSystem` class provides unified access to backtesting:

```python
system = TradingSystem()
system.initialize()

# Backtest specific strategy
result = system.run_backtest(
    strategy_name="sentiment_arbitrage",
    start_date=start,
    end_date=end,
)

# Backtest combined strategies
result = system.run_backtest(
    strategy_name=None,  # Uses all registered strategies
    start_date=start,
    end_date=end,
)
```

## Testing

Run the mock data test to verify functionality:

```bash
uv run python examples/test_system_mock.py
```

This uses synthetic data to test signal generation and backtesting without requiring a database.

## Notes

- The engine uses daily timeframes by default (via `TimeFrame.DAY_1`)
- All monetary values are in Chinese Yuan (CNY)
- Stamp duty is only applied to sell orders (China A-shares regulation)
- Short positions are supported but require appropriate signal generation
- The engine logs progress at INFO level; use DEBUG for detailed trade information
