# Common Module

Shared interfaces, types, and utilities for the Chinese Stock Trading System.

## Overview

This module provides the unified architecture for the trading system, enabling:

- **Interoperability**: All components communicate through standard interfaces
- **Backtesting**: Test strategies against historical data
- **Signal Aggregation**: Combine signals from multiple strategies
- **Extensibility**: Add new strategies and data sources easily

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     TradingSystem (Orchestrator)                 │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ SentimentArb    │  │   Contrarian    │  │  Custom Strategy │ │
│  │   Adapter       │  │    Adapter      │  │                  │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                    │           │
│           └────────────────────┼────────────────────┘           │
│                                ▼                                │
│                    ┌─────────────────────┐                      │
│                    │   Signal Router     │                      │
│                    │   (Aggregation)     │                      │
│                    └──────────┬──────────┘                      │
│                               │                                 │
│           ┌───────────────────┼───────────────────┐             │
│           ▼                   ▼                   ▼             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Data Provider  │  │  Backtest Engine │  │ Execution Client│ │
│  │   (DuckDB)      │  │                  │  │   (Broker)      │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Signal Generation

```python
from common import TradingSystem, create_system

# Create and initialize the system
system = create_system()

# Generate signals for specific symbols
portfolio = system.run_once(symbols=["600519.SH", "000858.SZ"])

# Access signals
for signal in portfolio.signals:
    print(f"{signal.symbol}: {signal.signal_type.value} (strength: {signal.strength})")
```

### Backtesting

```python
from common import quick_backtest, BacktestConfig

# Quick backtest with defaults
result = quick_backtest(
    strategy_name="sentiment_arbitrage",
    days=365,
    initial_capital=1_000_000.0,
)

print(result.summary())
```

### Custom Strategy

```python
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
        # Your signal generation logic here
        return signals

    # ... implement other required methods

# Add to system
system = create_system()
system.add_strategy(MyStrategy())
```

## Core Interfaces

### DataProvider

Abstract interface for data access. Implementations:
- `DuckDBDataProvider` - Access data from DuckDB database

```python
class DataProvider(ABC):
    def get_prices(symbols, start, end, timeframe) -> DataFrame
    def get_latest_prices(symbols) -> Dict[str, float]
    def get_fundamentals(symbols, as_of) -> List[Fundamentals]
    def get_sentiment(symbols, start, end) -> List[SentimentScore]
    def get_universe(universe_name) -> List[str]
```

### SignalGenerator

Abstract interface for strategies. Implementations:
- `SentimentArbAdapter` - Wraps sentiment_arbitrage module
- `ContrarianAdapter` - Wraps strategy module

```python
class SignalGenerator(ABC):
    @property
    def name(self) -> str

    @property
    def time_horizon(self) -> str

    def generate_signals(symbols, as_of, data_provider) -> List[TradingSignal]
    def update(new_data) -> None
    def get_state() -> Dict
    def set_state(state) -> None
```

### ExecutionClient

Abstract interface for broker execution.

```python
class ExecutionClient(ABC):
    def connect() -> bool
    def disconnect() -> None
    def submit_order(order) -> Order
    def cancel_order(order_id) -> bool
    def get_positions() -> List[Position]
    def get_account_balance() -> float
```

## Signal Types

### TradingSignal

The unified signal format used across all strategies:

```python
@dataclass
class TradingSignal:
    symbol: str
    signal_type: SignalType  # BUY, SELL, HOLD, EXIT
    timestamp: datetime
    source: str  # Strategy name

    strength: float  # 0-100
    confidence: float  # 0-1

    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    position_size: Optional[float]

    # Strategy-specific
    sentiment_score: Optional[float]
    valuation_score: Optional[float]
    price_z_score: Optional[float]
    dislocation: Optional[float]
```

## Configuration

### SystemConfig

Top-level configuration loaded from JSON:

```python
config = SystemConfig.from_file("config/system_config.json")

system = TradingSystem(config=config)
```

### Configuration Files

- `config/system_config.json` - Main system configuration

Key configuration sections:
- `data` - Database and cache settings
- `router` - Signal aggregation settings
- `backtest` - Backtesting parameters
- `execution` - Broker settings
- `sentiment_arb` - Sentiment arbitrage strategy parameters
- `contrarian` - Contrarian strategy parameters

## Backtesting

The backtesting engine provides:

- Multiple fill models (next_open, close, vwap)
- Realistic cost modeling (commission, slippage, stamp duty)
- Position tracking and P&L calculation
- Performance metrics (Sharpe, drawdown, win rate)

```python
from common import BacktestEngineImpl, BacktestConfig

config = BacktestConfig(
    initial_capital=1_000_000.0,
    commission_rate=0.0003,  # 0.03%
    slippage_rate=0.001,     # 0.1%
    stamp_duty=0.001,        # 0.1% (China A-shares)
)

engine = BacktestEngineImpl(data_provider, config)
result = engine.run(strategy, symbols, start, end)

print(f"Total Return: {result.total_return:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.max_drawdown:.2%}")
```

## Signal Router

Aggregates signals from multiple strategies:

```python
from common import SignalRouterImpl, RouterConfig

config = RouterConfig(
    sentiment_arb_weight=0.6,
    strategy_weight=0.4,
    min_conviction=0.3,
    min_strength=30.0,
)

router = SignalRouterImpl(config)
router.add_strategy(sentiment_arb_adapter)
router.add_strategy(contrarian_adapter)

portfolio = router.aggregate_signals(symbols, as_of, data_provider)
```

## Module Structure

```
common/
├── __init__.py          # Public API exports
├── types.py             # Data classes (TradingSignal, Position, etc.)
├── interfaces.py        # Abstract base classes
├── config.py            # Configuration classes
├── signal_router.py     # Signal aggregation implementation
├── backtest.py          # Backtesting engine
├── data_provider.py     # DuckDB data provider
├── strategy_adapters.py # Strategy wrapper adapters
└── orchestrator.py      # Main TradingSystem class
```

## Extending the System

### Adding a New Data Source

1. Implement the `DataProvider` interface
2. Register with the system

```python
class MyDataProvider(DataProvider):
    # Implement all abstract methods
    pass

# Use in system
system = TradingSystem()
system._data_provider = MyDataProvider()
```

### Adding a New Strategy

1. Implement the `SignalGenerator` interface
2. Add to the system

```python
class MyStrategy(SignalGenerator):
    # Implement all abstract methods
    pass

system.add_strategy(MyStrategy())
```

### Adding a New Broker

1. Implement the `ExecutionClient` interface
2. Connect to the system

```python
class MyBroker(ExecutionClient):
    # Implement all abstract methods
    pass

system.connect_broker(MyBroker())
```
