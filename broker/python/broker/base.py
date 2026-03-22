"""
Base Broker Interface - Abstract base class for broker implementations

This module provides the core broker abstraction that can be used by
both real brokers (Futu, XTP, etc.) and mock implementations for testing.

The BrokerInterface extends ExecutionClient from common and adds
broker-specific functionality like market data subscriptions.
"""

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Add common to path
_common_path = Path(__file__).parent.parent.parent / "common"
if str(_common_path) not in sys.path:
    sys.path.insert(0, str(_common_path))

from common.interfaces import ExecutionClient  # noqa: E402
from common.types import Order as CommonOrder  # noqa: E402
from common.types import Position as CommonPosition  # noqa: E402


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
class Order:
    """Order data model with full state tracking"""

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float | None = None  # Required for limit and stop_limit orders
    stop_price: float | None = None  # Required for stop and stop_limit orders
    status: OrderStatus = OrderStatus.CREATED
    order_id: str | None = None
    filled_quantity: int = 0
    avg_fill_price: float | None = None
    reject_reason: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    filled_at: datetime | None = None
    cancelled_at: datetime | None = None
    source_signal: str | None = None  # Track which signal generated this order
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_quantity(self) -> int:
        """Get remaining quantity to fill"""
        return self.quantity - self.filled_quantity

    @property
    def is_complete(self) -> bool:
        """Check if order is complete (filled or cancelled)"""
        return self.status in [
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        ]

    @property
    def is_active(self) -> bool:
        """Check if order is still active"""
        return self.status in [OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED]

    def update_status(self, new_status: OrderStatus) -> None:
        """Update order status and timestamp"""
        self.status = new_status
        self.updated_at = datetime.now()

        if new_status == OrderStatus.FILLED:
            self.filled_at = datetime.now()
        elif new_status == OrderStatus.CANCELLED:
            self.cancelled_at = datetime.now()

    def add_fill(self, quantity: int, price: float) -> None:
        """Add a fill to the order"""
        self.filled_quantity += quantity

        # Calculate average fill price
        if self.avg_fill_price is None:
            self.avg_fill_price = price
        else:
            total_value = (self.avg_fill_price * (self.filled_quantity - quantity)) + (
                price * quantity
            )
            self.avg_fill_price = total_value / self.filled_quantity

        # Update status
        if self.filled_quantity >= self.quantity:
            self.update_status(OrderStatus.FILLED)
        else:
            self.update_status(OrderStatus.PARTIALLY_FILLED)

        self.updated_at = datetime.now()

    def to_common_order(self) -> CommonOrder:
        """Convert to common Order type for interoperability"""
        return CommonOrder(
            order_id=self.order_id or "",
            symbol=self.symbol,
            side=self.side.value.upper(),
            quantity=self.quantity,
            order_type=self.order_type.value.upper(),
            limit_price=self.price,
            stop_price=self.stop_price,
            status=self.status.value.upper(),
            filled_quantity=self.filled_quantity,
            avg_fill_price=self.avg_fill_price,
            timestamp=self.created_at,
            source_signal=self.source_signal,
            metadata=self.metadata,
        )

    @classmethod
    def from_common_order(cls, order: CommonOrder) -> "Order":
        """Create from common Order type"""
        return cls(
            symbol=order.symbol,
            side=OrderSide.BUY if order.side.upper() == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET
            if order.order_type.upper() == "MARKET"
            else OrderType.LIMIT,
            quantity=int(order.quantity),
            price=order.limit_price,
            stop_price=order.stop_price,
            order_id=order.order_id,
            filled_quantity=int(order.filled_quantity),
            avg_fill_price=order.avg_fill_price,
            source_signal=order.source_signal,
            metadata=order.metadata,
        )


@dataclass
class Position:
    """Position data model with P&L tracking"""

    symbol: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    entry_time: datetime | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    source_signal: str | None = None
    last_update: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_long(self) -> bool:
        """Check if position is long"""
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """Check if position is short"""
        return self.quantity < 0

    @property
    def is_flat(self) -> bool:
        """Check if position is flat (no position)"""
        return self.quantity == 0

    @property
    def return_pct(self) -> float:
        """Calculate return percentage"""
        if self.quantity > 0:
            return (self.current_price - self.avg_cost) / self.avg_cost
        else:
            return (self.avg_cost - self.current_price) / self.avg_cost

    def update_price(self, new_price: float) -> None:
        """Update current price and recalculate unrealized P&L"""
        self.current_price = new_price
        self.market_value = abs(self.quantity) * new_price
        self.unrealized_pnl = (self.current_price - self.avg_cost) * self.quantity
        self.last_update = datetime.now()

    def add_fill(self, quantity: int, price: float) -> float:
        """
        Add a fill to the position and return realized P&L

        Args:
            quantity: Quantity (positive for buy, negative for sell)
            price: Fill price

        Returns:
            float: Realized P&L from this fill
        """
        old_quantity = self.quantity
        old_avg_cost = self.avg_cost

        # Set entry time if this is a new position
        if self.entry_time is None:
            self.entry_time = datetime.now()

        # Calculate new average cost
        if old_quantity >= 0:
            if quantity >= 0:
                # Adding to long position
                total_cost = (old_quantity * old_avg_cost) + (quantity * price)
                self.quantity += quantity
                self.avg_cost = total_cost / self.quantity
                realized_pnl = 0.0
            else:
                # Closing or reducing long position
                if abs(quantity) <= old_quantity:
                    # Partial close
                    realized_pnl = (price - old_avg_cost) * abs(quantity)
                    self.quantity += quantity
                    # Avg cost unchanged
                else:
                    # Complete close + short
                    realized_pnl = (price - old_avg_cost) * old_quantity
                    remaining_short = abs(quantity) - old_quantity
                    self.quantity = -remaining_short
                    self.avg_cost = price
        else:
            if quantity <= 0:
                # Adding to short position
                total_cost = (abs(old_quantity) * old_avg_cost) + (abs(quantity) * price)
                self.quantity += quantity
                self.avg_cost = total_cost / abs(self.quantity)
                realized_pnl = 0.0
            else:
                # Closing or reducing short position
                if quantity <= abs(old_quantity):
                    # Partial close
                    realized_pnl = (old_avg_cost - price) * quantity
                    self.quantity += quantity
                    # Avg cost unchanged
                else:
                    # Complete close + long
                    realized_pnl = (old_avg_cost - price) * abs(old_quantity)
                    remaining_long = quantity - abs(old_quantity)
                    self.quantity = remaining_long
                    self.avg_cost = price

        self.realized_pnl += realized_pnl
        self.last_update = datetime.now()
        self.update_price(price)

        return realized_pnl

    def to_common_position(self) -> CommonPosition:
        """Convert to common Position type for interoperability"""
        return CommonPosition(
            symbol=self.symbol,
            side="long" if self.quantity > 0 else "short",
            quantity=float(self.quantity),
            entry_price=self.avg_cost,
            entry_time=self.entry_time or datetime.now(),
            current_price=self.current_price,
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            unrealized_pnl=self.unrealized_pnl,
            realized_pnl=self.realized_pnl,
            source_signal=self.source_signal,
        )


@dataclass
class AccountBalance:
    """Account balance information"""

    total_equity: float
    cash: float
    buying_power: float
    margin_used: float
    available_withdrawal: float
    market_value: float
    last_update: datetime = field(default_factory=datetime.now)


class BrokerInterface(ExecutionClient, ABC):
    """
    Abstract base class for broker implementations.

    This extends ExecutionClient from common module and adds
    broker-specific functionality like market data subscriptions.

    This class uses broker-specific Order and Position types internally but
    converts to/from common.types.Order and common.types.Position when
    implementing the ExecutionClient interface.

    Subclasses must implement:
    - place_order() - Core order placement (broker-specific)
    - get_orders() - Get all orders (broker-specific)
    - subscribe_market_data() - Market data subscription
    - unsubscribe_market_data() - Market data unsubscription
    - get_market_data() - Get market data
    """

    # === Abstract methods that must be implemented by subclasses ===

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """
        Place an order (broker-specific implementation)

        Args:
            order: Order to place

        Returns:
            Order: Updated order with order_id assigned
        """
        pass

    @abstractmethod
    def get_orders_broker(self, symbol: str | None = None) -> list[Order]:
        """
        Get all orders or orders for a specific symbol (broker-specific)

        Args:
            symbol: Optional symbol filter

        Returns:
            List[Order]: List of orders (broker-specific Order type)
        """
        pass

    @abstractmethod
    def subscribe_market_data(self, symbols: list[str]) -> bool:
        """
        Subscribe to market data for symbols

        Args:
            symbols: List of symbols to subscribe

        Returns:
            bool: True if subscription successful
        """
        pass

    @abstractmethod
    def unsubscribe_market_data(self, symbols: list[str]) -> bool:
        """
        Unsubscribe from market data for symbols

        Args:
            symbols: List of symbols to unsubscribe

        Returns:
            bool: True if unsubscription successful
        """
        pass

    @abstractmethod
    def get_market_data(self, symbol: str) -> dict[str, Any]:
        """
        Get current market data for a symbol

        Args:
            symbol: Symbol to retrieve

        Returns:
            Dict[str, Any]: Market data including price, bid, ask, volume, etc.
        """
        pass

    @abstractmethod
    def get_order_broker(self, order_id: str) -> Order:
        """
        Get order status (broker-specific)

        Args:
            order_id: Order ID to retrieve

        Returns:
            Order: Current order status
        """
        pass

    @abstractmethod
    def get_positions_broker(self) -> list[Position]:
        """
        Get current positions (broker-specific)

        Returns:
            List[Position]: List of current positions
        """
        pass

    @abstractmethod
    def get_position_broker(self, symbol: str) -> Position | None:
        """
        Get position for a specific symbol (broker-specific)

        Args:
            symbol: Symbol to retrieve

        Returns:
            Optional[Position]: Position if exists, None otherwise
        """
        pass

    @abstractmethod
    def get_account_balance(self) -> float:
        """
        Get available account balance

        Returns:
            float: Available cash balance
        """
        pass

    # === ExecutionClient interface implementation (uses common types) ===

    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to the broker.

        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if connected to broker.

        Returns:
            True if connected
        """
        pass

    def submit_order(self, order: CommonOrder) -> CommonOrder:
        """
        Implementation of ExecutionClient.submit_order

        Converts common Order to broker Order, places it, and converts back.
        """
        broker_order = Order.from_common_order(order)
        result = self.place_order(broker_order)
        return result.to_common_order()

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancellation successful
        """
        pass

    def get_order(self, order_id: str) -> CommonOrder:
        """
        Get order status (ExecutionClient interface)

        Args:
            order_id: Order ID to retrieve

        Returns:
            Order: Current order status (common.types.Order)
        """
        broker_order = self.get_order_broker(order_id)
        return broker_order.to_common_order()

    def get_orders_common(self, symbol: str | None = None) -> list[CommonOrder]:
        """
        Get all orders (ExecutionClient interface)

        Args:
            symbol: Optional symbol filter

        Returns:
            List[Order]: List of orders (common.types.Order)
        """
        broker_orders = self.get_orders_broker(symbol)
        return [o.to_common_order() for o in broker_orders]

    def get_orders(self, symbol: str | None = None) -> list[CommonOrder]:
        """
        Get all orders (ExecutionClient interface implementation)

        Args:
            symbol: Optional symbol filter

        Returns:
            List[Order]: List of orders (common.types.Order)
        """
        return self.get_orders_common(symbol)

    def get_positions(self) -> list[CommonPosition]:
        """
        Get current positions (ExecutionClient interface)

        Returns:
            List[Position]: List of current positions (common.types.Position)
        """
        broker_positions = self.get_positions_broker()
        return [p.to_common_position() for p in broker_positions]

    def get_position(self, symbol: str) -> CommonPosition | None:
        """
        Get position for a specific symbol (ExecutionClient interface)

        Args:
            symbol: Symbol to retrieve

        Returns:
            Optional[Position]: Position if exists, None otherwise (common.types.Position)
        """
        broker_position = self.get_position_broker(symbol)
        if broker_position is None:
            return None
        return broker_position.to_common_position()

    def get_total_equity(self) -> float:
        """
        Get total account equity

        Returns:
            float: Total equity (cash + positions)
        """
        balance = self.get_account_balance()
        positions = self.get_positions_broker()
        positions_value = sum(p.market_value for p in positions)
        return balance + positions_value
