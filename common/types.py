"""
Common Types and Data Classes

Defines shared data structures used across all modules.
These are the canonical types used throughout the trading system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List


# =============================================================================
# Enums
# =============================================================================

class SignalType(Enum):
    """Trading signal types"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    EXIT = "EXIT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"


class SignalStrength(Enum):
    """Signal strength levels"""
    WEAK = 1
    MODERATE = 2
    STRONG = 3


class TimeFrame(Enum):
    """Supported timeframes for data"""
    TICK = "tick"
    MIN_1 = "1m"
    MIN_5 = "5m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"


class OrderType(Enum):
    """Order types"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    """Order sides"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order statuses"""
    CREATED = "created"
    VALIDATING = "validating"
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Bar:
    """OHLCV bar data"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: Optional[float] = None  # Trading amount in currency

    @property
    def typical_price(self) -> float:
        """Calculate typical price (H+L+C)/3"""
        return (self.high + self.low + self.close) / 3

    @property
    def range(self) -> float:
        """Calculate bar range"""
        return self.high - self.low

    @property
    def body_size(self) -> float:
        """Calculate body size"""
        return abs(self.close - self.open)


@dataclass
class MarketData:
    """Market data point for a single symbol"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: Optional[float] = None

    def to_bar(self) -> Bar:
        """Convert to Bar object"""
        return Bar(
            symbol=self.symbol,
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            amount=self.amount,
        )


@dataclass
class Fundamentals:
    """Fundamental data for a stock"""
    symbol: str
    timestamp: datetime
    pe_ratio: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    eps: Optional[float] = None
    book_value_per_share: Optional[float] = None
    total_mv: Optional[float] = None  # Total market value
    circ_mv: Optional[float] = None  # Circulating market value
    sector: Optional[str] = None
    industry: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "pe_ratio": self.pe_ratio,
            "pe_ttm": self.pe_ttm,
            "pb_ratio": self.pb_ratio,
            "ps_ratio": self.ps_ratio,
            "peg_ratio": self.peg_ratio,
            "dividend_yield": self.dividend_yield,
            "roe": self.roe,
            "roa": self.roa,
            "eps": self.eps,
            "book_value_per_share": self.book_value_per_share,
            "total_mv": self.total_mv,
            "circ_mv": self.circ_mv,
            "sector": self.sector,
            "industry": self.industry,
        }


@dataclass
class SentimentScore:
    """Sentiment score for a stock"""
    symbol: str
    timestamp: datetime
    score: float  # -1 to 1 (bearish to bullish)
    confidence: float  # 0 to 1
    source: str  # "news", "social", "search", "forum", "composite"
    raw_score: Optional[float] = None
    sample_size: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_bullish(self) -> bool:
        """Check if sentiment is bullish"""
        return self.score > 0.3

    @property
    def is_bearish(self) -> bool:
        """Check if sentiment is bearish"""
        return self.score < -0.3

    @property
    def is_neutral(self) -> bool:
        """Check if sentiment is neutral"""
        return -0.3 <= self.score <= 0.3


@dataclass
class TradingSignal:
    """
    Unified trading signal used across all strategy modules.

    This is the standard signal format that all signal generators must produce.
    """
    # Core fields
    symbol: str
    signal_type: SignalType
    timestamp: datetime
    source: str  # "sentiment_arbitrage" or "strategy"

    # Signal quality
    strength: float  # 0-100 (higher = stronger)
    confidence: float  # 0-1 (model confidence)

    # Price levels
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Position sizing
    position_size: Optional[float] = None  # Fraction of portfolio
    quantity: Optional[int] = None  # Number of shares

    # Strategy-specific data
    sentiment_score: Optional[float] = None
    valuation_score: Optional[float] = None
    price_z_score: Optional[float] = None
    dislocation: Optional[float] = None

    # Metadata
    reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def strength_level(self) -> SignalStrength:
        """Convert strength to level"""
        if self.strength >= 70:
            return SignalStrength.STRONG
        elif self.strength >= 40:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    @property
    def is_entry(self) -> bool:
        """Check if this is an entry signal"""
        return self.signal_type in [SignalType.BUY, SignalType.SELL]

    @property
    def is_exit(self) -> bool:
        """Check if this is an exit signal"""
        return self.signal_type in [SignalType.EXIT, SignalType.EXIT_LONG, SignalType.EXIT_SHORT]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "strength": self.strength,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size": self.position_size,
            "quantity": self.quantity,
            "sentiment_score": self.sentiment_score,
            "valuation_score": self.valuation_score,
            "price_z_score": self.price_z_score,
            "dislocation": self.dislocation,
            "reasons": self.reasons,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradingSignal":
        """Create from dictionary"""
        data["signal_type"] = SignalType(data["signal_type"])
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class PortfolioSignal:
    """Aggregated signals for portfolio construction"""
    signals: List[TradingSignal]
    timestamp: datetime

    # Exposure metrics
    long_count: int = 0
    short_count: int = 0
    total_exposure: float = 0.0
    net_exposure: float = 0.0

    # Risk metrics
    max_single_position: float = 0.0
    sector_concentration: Dict[str, float] = field(default_factory=dict)

    @property
    def signal_count(self) -> int:
        """Total number of signals"""
        return len(self.signals)

    def get_signals_by_type(self, signal_type: SignalType) -> List[TradingSignal]:
        """Filter signals by type"""
        return [s for s in self.signals if s.signal_type == signal_type]

    def get_signals_by_symbol(self, symbol: str) -> List[TradingSignal]:
        """Filter signals by symbol"""
        return [s for s in self.signals if s.symbol == symbol]


@dataclass
class Position:
    """Active position representation"""
    symbol: str
    side: str  # "long" or "short"
    quantity: float
    entry_price: float
    entry_time: datetime
    current_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    source_signal: Optional[str] = None  # Strategy that generated the signal

    @property
    def market_value(self) -> float:
        """Current market value"""
        return abs(self.quantity) * self.current_price

    @property
    def cost_basis(self) -> float:
        """Total cost basis"""
        return abs(self.quantity) * self.entry_price

    @property
    def return_pct(self) -> float:
        """Return percentage"""
        if self.side == "long":
            return (self.current_price - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - self.current_price) / self.entry_price

    def update_price(self, new_price: float) -> None:
        """Update current price and recalculate P&L"""
        self.current_price = new_price
        if self.side == "long":
            self.unrealized_pnl = (new_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - new_price) * abs(self.quantity)


@dataclass
class Order:
    """Order representation"""
    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    order_type: str  # "MARKET", "LIMIT", "STOP"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = "PENDING"
    filled_quantity: float = 0.0
    avg_fill_price: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)
    source_signal: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_quantity(self) -> float:
        """Remaining quantity to fill"""
        return self.quantity - self.filled_quantity

    @property
    def is_complete(self) -> bool:
        """Check if order is complete"""
        return self.status in ["FILLED", "CANCELLED", "REJECTED"]

    @property
    def is_active(self) -> bool:
        """Check if order is still active"""
        return self.status in ["PENDING", "PARTIALLY_FILLED"]


@dataclass
class Trade:
    """Executed trade representation"""
    trade_id: str
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: datetime
    commission: float = 0.0
    slippage: float = 0.0
    source_signal: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def notional_value(self) -> float:
        """Total trade value"""
        return self.quantity * self.price

    @property
    def total_cost(self) -> float:
        """Total cost including commission"""
        return self.notional_value + self.commission
