# Chinese Stock Broker API Research
## Broker Integration & Order Execution Infrastructure

Research Date: 2026-03-08
Project: Chinese Stock Sentiment Trading System

---

## Executive Summary

After researching major Chinese stock broker APIs and trading platforms, **Futu (富途) OpenAPI** emerges as the best option for this project due to:

- ✅ **Full Paper Trading Support** - Simulated trading for A-shares (China Connect) and other markets
- ✅ **Excellent API Documentation** - Comprehensive, well-structured documentation
- ✅ **Multi-language Support** - Python, Java, C#, C++, JavaScript
- ✅ **Free for Account Holders** - No additional API fees
- ✅ **Low Latency** - 0.0014s order placement speed
- ✅ **A-share Access** - Supports China Connect securities via universal account

**Recommended Choice**: **Futu OpenAPI** with Python for prototyping, potential migration to Rust for production if performance needs dictate.

---

## 1. Broker API Options Comparison

### 1.1 Futu OpenAPI (富途) - ⭐ RECOMMENDED

**Overview**: Futu Securities (moomoo/Futubull) provides a comprehensive API for programmatic trading across multiple markets including A-shares.

**Markets Supported**:
| Market | Securities | Options | Futures | Paper Trading |
|--------|-----------|---------|---------|---------------|
| Hong Kong | ✅ Stocks, ETFs, Warrants, CBBCs | ✅ | ✅ | ✅ |
| US | ✅ Stocks, ETFs | ✅ | ✅ | ✅ |
| A-share (China) | ✅ China Connect Stocks | ❌ | ❌ | ✅ |
| Singapore | ❌ | ❌ | ✅ | ❌ |
| Japan | ❌ | ❌ | ✅ | ❌ |

**API Capabilities**:
- ✅ Real-time market data subscription (quote, candlestick, tick, order book)
- ✅ Historical data retrieval
- ✅ Order placement (market, limit, stop, stop-limit)
- ✅ Position management and P&L tracking
- ✅ Account information retrieval
- ✅ Order state management (pending, filled, cancelled, rejected)

**Technical Details**:
- **Languages**: Python, Java, C#, C++, JavaScript
- **Architecture**: OpenD gateway (local/cloud) + Futu API SDK
- **Order Speed**: 0.0014s
- **Platforms**: Windows, macOS, CentOS, Ubuntu

**Cost**:
- **Free** for customers with Futu brokerage account
- Market data may require separate subscriptions (Quotation Card)
- No additional charges for trading via OpenAPI

**Documentation Quality**: ⭐⭐⭐⭐⭐ (Excellent)
- Comprehensive documentation at https://openapi.futunn.com/futu-api-doc/en/
- Well-structured with clear examples
- Active community support
- SDK references for all supported languages

**Account Requirements**:
- Futu ID (Futubull account)
- Universal Account (for multi-market trading)
- Market data authorities for each market type

**Paper Trading**:
- ✅ Full paper trading support for supported markets
- Same API for paper and live trading (just different account mode)
- Perfect for strategy development and testing

**Pros**:
- Excellent paper trading environment
- Comprehensive API with full trading capabilities
- Free for account holders
- Multi-language support
- Good documentation
- Fast execution
- Supports A-shares via China Connect

**Cons**:
- A-share access limited to China Connect securities only (some A-shares not available)
- Requires opening a brokerage account
- Market data may have additional costs for some markets
- China Connect has eligibility requirements (e.g., minimum account balance)

---

### 1.2 Tiger OpenAPI (老虎证券)

**Overview**: Tiger Securities provides API access for automated trading, primarily focused on US and HK markets.

**API Capabilities**:
- Order placement with advanced order types
- Account management
- Multiple order allocation plans
- Customizable reports

**Technical Details**:
- **Languages**: Not explicitly listed (likely REST/HTTP-based)
- Documentation at: https://developer.itigerup.com

**Cost**:
- Pricing not publicly available on main page
- Likely requires institutional/partner relationship

**Paper Trading**:
- Information not clearly documented on public pages
- May be available for institutional clients

**Documentation Quality**: ⭐⭐⭐ (Moderate)
- Some documentation available but not as comprehensive as Futu
- Enterprise-focused, less individual trader friendly

**Pros**:
- Advanced order types
- Flexible integration solutions
- Customizable reports

**Cons**:
- A-share support unclear
- Paper trading support not clearly documented
- Enterprise focus (may not be suitable for individual)
- Pricing and account requirements unclear

---

### 1.3 JoinQuant (聚宽)

**Overview**: JoinQuant is a Chinese quantitative trading platform providing strategy research, backtesting, and live trading.

**API Capabilities**:
- ✅ A-shares, futures, options, funds, macro data
- ✅ Hundreds of common factors
- ✅ Strategy research and historical backtesting
- ✅ Paper trading (模拟交易)
- ✅ Live trading (实盘交易)

**Technical Details**:
- **Languages**: Python (primary)
- Platform-based (local option available with JoinQuant client)
- Data services: JQData (Python SDK)

**Cost**:
- Free tier available (limited)
- Paid tiers for advanced features and more data
- Live trading requires broker connection

**Paper Trading**:
- ✅ Comprehensive paper trading support
- Same platform for backtesting, paper trading, and live trading

**Documentation Quality**: ⭐⭐⭐⭐ (Good)
- Extensive documentation and tutorials
- 100+ courses available
- Active community

**Pros**:
- Excellent for A-shares (primary focus)
- Paper trading built-in
- Backtesting platform
- Python-based
- Good educational resources

**Cons**:
- Platform-based (less flexible than direct API)
- Live trading requires separate broker connection
- May have limitations on custom execution logic

---

### 1.4 Tushare Pro

**Overview**: Tushare is a data provider, NOT a broker. It provides comprehensive financial data but NO trading capabilities.

**API Capabilities**:
- ✅ A-shares data (daily, minute, tick)
- ✅ Financial statements
- ✅ Index data
- ✅ Macro data
- ✅ Fund data

**Technical Details**:
- **Languages**: Python (primary), HTTP RESTful
- SDK available: pip install tushare

**Cost**:
- Free tier available (limited)
- Paid tiers for more data and features
- Community contributions system

**Trading Support**:
- ❌ NO trading capabilities (data only)
- ❌ NO paper trading

**Use Case**: Excellent for data acquisition and strategy research, but requires separate broker integration for actual trading.

---

### 1.5 QuantConnect

**Overview**: International quantitative trading platform supporting multiple global markets.

**API Capabilities**:
- ✅ US stocks, ETFs, options, futures (since 1998)
- ✅ Backtesting
- ✅ Paper trading
- ✅ Live trading (20+ broker integrations)

**Technical Details**:
- **Languages**: Python, C#
- Cloud-based platform
- LEAN engine available for on-premise deployment

**Cost**:
- Free tier for research and backtesting
- Paid tiers for live trading
- Institutional plans available

**A-share Support**:
- ❌ Limited or no A-share support (primarily US markets)

**Paper Trading**:
- ✅ Excellent paper trading environment
- Same engine for backtesting and live trading

**Pros**:
- Excellent platform and tools
- Great documentation
- Cloud-based or on-premise
- Machine learning support

**Cons**:
- No A-share support (showstopper for this project)
- Primarily US-focused

---

### 1.6 Xueqiu (雪球)

**Overview**: Social trading platform with some API capabilities.

**API Capabilities**:
- Limited API access (primarily web scraping required)
- Community features
- Portfolio tracking

**Trading Support**:
- ❌ No official trading API
- Paper trading via web interface only
- Live trading requires separate broker

**Documentation Quality**: ⭐⭐ (Poor)
- Limited official API documentation
- Most integration requires unofficial methods

**Not Recommended**: Lacks official API and comprehensive documentation.

---

### 1.7 East Money (东方财富)

**Overview**: Financial data provider and portal with historical data APIs.

**API Capabilities**:
- ✅ Historical stock data
- ✅ Real-time quotes
- ❌ No trading API

**Trading Support**:
- ❌ No trading capabilities (data only)
- Paper trading via separate broker (东方财富证券)

**Documentation Quality**: ⭐⭐⭐ (Moderate)
- Some documentation for data APIs
- Limited trading API information

**Not Recommended**: Lacks comprehensive trading API for programmatic trading.

---

### 1.8 Tonghuashun (同花顺) / 10jqka

**Overview**: Major Chinese financial platform with trading capabilities.

**API Capabilities**:
- ✅ Trading via APP interface
- ✅ Some programmatic access (limited documentation)
- ❌ No official public trading API

**Trading Support**:
- ❌ Paper trading unclear (may require account)
- Live trading requires reverse engineering APP protocols

**Documentation Quality**: ⭐ (Poor)
- Limited public API documentation
- Most integration requires unofficial methods

**Not Recommended**: No official public API for programmatic trading.

---

## 2. Detailed Paper Trading Evaluation

### 2.1 Futu OpenAPI Paper Trading

**Setup Requirements**:
1. Open Futu account (can open online)
2. Enable paper trading in account settings
3. Install OpenD gateway (Windows/macOS/CentOS/Ubuntu)
4. Install Futu API SDK (Python: `pip install futu-api`)

**Paper Trading Features**:
- Real-time market data (simulation)
- Same order types as live trading:
  - Market order
  - Limit order
  - Stop order
  - Stop-limit order
- Position tracking
- P&L calculation
- Order history
- Account balance simulation

**Code Example (Python)**:
```python
from futu import *

# Connect to OpenD
quote_ctx = OpenSecQuoteContext(host='127.0.0.1', port=11111)
trade_ctx = OpenSecTradeContext(host='127.0.0.1', port=11111)

# For paper trading, use paper_trading=True
trade_ctx = OpenSecTradeContext(
    host='127.0.0.1',
    port=11111,
    security_firm=SecurityFirm.FUTUSECURITIES,
    paper_trading=True  # Enable paper trading
)

# Place an order
ret, data = trade_ctx.place_order(
    price=10.5,
    qty=100,
    code='600519.SH',  # Maotai stock
    trd_env=TrdEnv.SIMULATE  # Simulation environment
)
```

**Limitations**:
- Market data may have slight delays (simulated)
- Slippage may not perfectly match reality
- Paper trading may not account for all real-world frictions

---

### 2.2 JoinQuant Paper Trading

**Setup Requirements**:
1. Create JoinQuant account (free tier available)
2. Use web-based platform or local client
3. Python-based strategy development

**Paper Trading Features**:
- A-share paper trading (full support)
- Same API for backtesting and paper trading
- Comprehensive strategy testing tools

**Code Example (Python)**:
```python
from joinquant import *

# Initialize strategy
def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

def handle_data(context, data):
    order_target_value('600519.XSHG', 100000)
```

---

## 3. Recommended Technical Architecture

### 3.1 Language Selection

**Python (Recommended for Prototyping)**:
- ✅ Futu API has excellent Python SDK
- ✅ Easy to develop and test quickly
- ✅ Rich ecosystem (pandas, numpy, etc.)
- ✅ Good for data analysis and strategy research
- ✅ JoinQuant also Python-based

**Rust (Recommended for Production - Future)**:
- ✅ Performance-critical components
- ✅ Memory safety
- ✅ Low-level control
- ⚠️ May need to implement broker API bindings
- ⚠️ Less ecosystem support for trading

**Hybrid Approach (Recommended)**:
- Python for strategy development and testing
- Rust for execution engine and critical components
- Inter-process communication (e.g., gRPC, message queues)

---

### 3.2 Project Structure

```
~/trade/stocks/live/broker/
├── BROKER_RESEARCH.md          # This document
├── README.md                   # Project overview
├── architecture.md             # System architecture docs
├── design/
│   ├── order_management.md    # Order management design
│   ├── position_tracking.md    # Position tracking design
│   ├── risk_controls.md        # Risk management design
│   └── broker_abstraction.md   # Broker interface abstraction
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
│   ├── Cargo.toml
│   └── src/
├── tests/
│   ├── test_order.py
│   ├── test_position.py
│   └── test_risk.py
└── .env                        # Environment variables (not in git)
```

---

## 4. Order Management System Design

### 4.1 Order Submission Flow

```
[Strategy Signal]
      ↓
[Risk Check] → (Fail) → [Reject Order]
      ↓ (Pass)
[Position Check] → (Insufficient) → [Reject Order]
      ↓ (OK)
[Order Creation]
      ↓
[Order Validation] → (Fail) → [Reject Order]
      ↓ (Pass)
[Broker API Call]
      ↓
[Order Submission]
      ↓
[Order ID Returned]
      ↓
[Order State: PENDING]
      ↓
[Monitor Order Status]
      ↓
[Filled / Cancelled / Rejected]
```

### 4.2 Order Types

1. **Market Order (市价单)**
   - Execute immediately at best available price
   - No price guarantee
   - Use for urgent execution

2. **Limit Order (限价单)**
   - Execute only at specified price or better
   - No execution guarantee
   - Use for precise price control

3. **Stop Order (止损单)**
   - Trigger market order when price reaches stop level
   - Use for stop-loss

4. **Stop-Limit Order (止损限价单)**
   - Trigger limit order when price reaches stop level
   - More control than stop order
   - No execution guarantee

### 4.3 Order State Machine

```
[CREATED]
      ↓
[VALIDATING] → (Fail) → [REJECTED]
      ↓ (Pass)
[PENDING]
      ↓
[FILLED] ←─┐
[CANCELLED] ←── [CANCELLING]
[PARTIALLY_FILLED]
[REJECTED]
```

### 4.4 Position Tracking

**Current Holdings**:
- Track per-symbol positions
- Track average cost basis
- Track unrealized P&L

**Data Model**:
```python
class Position:
    symbol: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    last_update: datetime
```

### 4.5 Risk Controls

**Position Limits**:
- Max position size per symbol
- Max total position value
- Max number of open positions
- Max daily loss limit

**Stop-Loss Mechanisms**:
- Per-position stop-loss
- Portfolio-level stop-loss
- Time-based stops (close before market close)
- Volatility-based stops

**Order Validation**:
- Check account balance
- Check margin requirements
- Check position limits
- Check market hours
- Check order validity (price, quantity, etc.)

---

## 5. Implementation Roadmap

### Phase 1: Setup & Research (Current) ✅
- [x] Research broker APIs
- [x] Document findings
- [x] Create project structure
- [ ] Open Futu account (if not already)
- [ ] Enable paper trading

### Phase 2: Broker Integration (Next)
- [ ] Install OpenD gateway
- [ ] Install Futu Python SDK
- [ ] Implement base broker interface
- [ ] Implement Futu broker adapter
- [ ] Test basic connection to paper trading

### Phase 3: Order Management
- [ ] Implement order models
- [ ] Implement order manager
- [ ] Implement order validation
- [ ] Implement order state tracking
- [ ] Test order submission flow

### Phase 4: Position Tracking
- [ ] Implement position models
- [ ] Implement position tracker
- [ ] Implement P&L calculation
- [ ] Test position updates

### Phase 5: Risk Controls
- [ ] Implement risk manager
- [ ] Implement position limits
- [ ] Implement stop-loss mechanisms
- [ ] Test risk controls

### Phase 6: Integration & Testing
- [ ] Integrate with sentiment analysis
- [ ] End-to-end testing with paper trading
- [ ] Performance optimization
- [ ] Documentation

---

## 6. Next Steps

### Immediate Actions:
1. **Open Futu account** (if not already) and enable paper trading
2. **Install OpenD** and Futu Python SDK
3. **Create base broker interface** and Futu implementation
4. **Test basic order placement** in paper trading environment

### Recommended Starting Code:
```python
# ~/trade/stocks/live/broker/python/broker/base.py
from abc import ABC, abstractmethod
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class Order:
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market', 'limit', 'stop', 'stop_limit'
    quantity: int
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = 'created'
    order_id: Optional[str] = None
    filled_quantity: int = 0
    avg_fill_price: Optional[float] = None

@dataclass
class Position:
    symbol: str
    quantity: int
    avg_cost: float
    current_price: float
    unrealized_pnl: float

class BrokerInterface(ABC):
    @abstractmethod
    def place_order(self, order: Order) -> Order:
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Order:
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        pass

    @abstractmethod
    def get_account_balance(self) -> dict:
        pass
```

---

## 7. Conclusion

**Best Option**: **Futu OpenAPI** with Python for initial development.

**Why**:
1. Full paper trading support for A-shares
2. Excellent API and documentation
3. Free for account holders
4. Multi-language support
5. Low latency
6. Comprehensive trading features

**Timeline Estimate**:
- Setup and basic connection: 1-2 days
- Order management implementation: 3-5 days
- Position tracking: 2-3 days
- Risk controls: 2-3 days
- Integration and testing: 3-5 days
- **Total**: ~2-3 weeks for initial working system

---

## 8. References

- Futu OpenAPI Documentation: https://openapi.futunn.com/futu-api-doc/en/
- Futu OpenD Download: https://www.futunn.com/en/download/openAPI
- JoinQuant: https://www.joinquant.com
- Tushare Pro: https://tushare.pro
- QuantConnect: https://www.quantconnect.com

---

*Document Version: 1.0*
*Last Updated: 2026-03-08*
*Author: Trading System Engineer (Subagent)*
