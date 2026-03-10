# Broker Integration & Order Execution System

Chinese Stock Sentiment Trading System - Broker Integration Module

## Overview

This module provides broker integration and order execution infrastructure for the Chinese Stock Sentiment Trading System. It supports paper trading and live trading through various broker APIs.

## Current Status

- ✅ Research completed - See [BROKER_RESEARCH.md](./BROKER_RESEARCH.md)
- 🔄 Implementation in progress

## Recommended Broker

**Futu OpenAPI** (富途) - Full support for A-shares (China Connect) with paper trading environment.

## Project Structure

```
~/trade/stocks/live/broker/
├── BROKER_RESEARCH.md          # Comprehensive broker API research
├── README.md                   # This file
├── architecture.md             # System architecture (TODO)
├── design/
│   ├── order_management.md    # Order management design (TODO)
│   ├── position_tracking.md    # Position tracking design (TODO)
│   ├── risk_controls.md        # Risk management design (TODO)
│   └── broker_abstraction.md   # Broker interface abstraction (TODO)
├── python/
│   ├── __init__.py
│   ├── config.py               # Configuration
│   ├── broker/
│   │   ├── __init__.py
│   │   ├── base.py             # Base broker interface
│   │   ├── futu.py             # Futu implementation
│   │   └── mock.py             # Mock for testing
│   ├── order/
│   │   ├── __init__.py
│   │   ├── manager.py          # Order manager
│   │   └── models.py           # Order data models
│   ├── position/
│   │   ├── __init__.py
│   │   ├── tracker.py          # Position tracker
│   │   └── models.py           # Position data models
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── controls.py         # Risk controls
│   │   └── limits.py           # Position limits
│   └── main.py                 # Main entry point
├── rust/                       # Future: Rust execution engine
├── tests/
│   ├── test_order.py
│   ├── test_position.py
│   └── test_risk.py
└── .env.example                # Environment variables template
```

## Quick Start

### 1. Install Dependencies

```bash
# Install Futu Python SDK
pip install futu-api

# Install other dependencies
pip install pandas numpy python-dotenv
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Run Paper Trading Test

```bash
cd ~/trade/stocks/live/broker/python
python main.py --paper-trading
```

## Development

### Testing

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_order.py
```

### Code Style

```bash
# Format code
black python/

# Lint code
flake8 python/
```

## Architecture

The system follows a modular architecture:

1. **Broker Interface** - Abstract base class for broker implementations
2. **Order Management** - Order creation, validation, and tracking
3. **Position Tracking** - Real-time position and P&L monitoring
4. **Risk Controls** - Position limits, stop-loss, and risk management

## Broker Implementation Status

| Broker | Status | Notes |
|--------|--------|-------|
| Futu OpenAPI | ✅ Recommended | Full paper trading, excellent docs |
| JoinQuant | 🔄 Planned | Good for A-shares, platform-based |
| Tiger Securities | ❌ Not prioritized | Enterprise-focused |
| Tushare | ❌ Data only | No trading capabilities |

## Documentation

- [Broker Research](./BROKER_RESEARCH.md) - Comprehensive broker API comparison
- [Architecture](./architecture.md) - System architecture (TODO)
- [Order Management](./design/order_management.md) - Order flow and state machine (TODO)
- [Position Tracking](./design/position_tracking.md) - Position and P&L tracking (TODO)
- [Risk Controls](./design/risk_controls.md) - Risk management design (TODO)

## Contributing

See [BROKER_RESEARCH.md](./BROKER_RESEARCH.md) for detailed research and implementation roadmap.

## License

Part of the Chinese Stock Sentiment Trading System.
