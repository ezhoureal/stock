"""
Base Broker Interface - Abstract base class for broker implementations
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


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
    """Order data model"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Optional[float] = None  # Required for limit and stop_limit orders
    stop_price: Optional[float] = None  # Required for stop and stop_limit orders
    status: OrderStatus = OrderStatus.CREATED
    order_id: Optional[str] = None
    filled_quantity: int = 0
    avg_fill_price: Optional[float] = None
    reject_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_quantity(self) -> int:
        """Get remaining quantity to fill"""
        return self.quantity - self.filled_quantity

    @property
    def is_complete(self) -> bool:
        """Check if order is complete (filled or cancelled)"""
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELLED,
                               OrderStatus.REJECTED, OrderStatus.EXPIRED]

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
            total_value = (self.avg_fill_price * (self.filled_quantity - quantity)) + (price * quantity)
            self.avg_fill_price = total_value / self.filled_quantity

        # Update status
        if self.filled_quantity >= self.quantity:
            self.update_status(OrderStatus.FILLED)
        else:
            self.update_status(OrderStatus.PARTIALLY_FILLED)

        self.updated_at = datetime.now()


@dataclass
class Position:
    """Position data model"""
    symbol: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    last_update: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

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

    def update_price(self, new_price: float) -> None:
        """Update current price and recalculate unrealized P&L"""
        self.current_price = new_price
        self.market_value = abs(self.quantity) * new_price
        self.unrealized_pnl = (self.current_price - self.avg_cost) * self.quantity
        self.last_update = datetime.now()

    def add_fill(self, quantity: int, price: float) -> float:
        """
        Add a fill to the position and return realized P&L

        Returns:
            float: Realized P&L from this fill
        """
        old_quantity = self.quantity
        old_avg_cost = self.avg_cost

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


class BrokerInterface(ABC):
    """Abstract base class for broker implementations"""

    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to the broker

        Returns:
            bool: True if connection successful
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from the broker

        Returns:
            bool: True if disconnection successful
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if connected to broker

        Returns:
            bool: True if connected
        """
        pass

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """
        Place an order

        Args:
            order: Order to place

        Returns:
            Order: Updated order with order_id assigned
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order

        Args:
            order_id: Order ID to cancel

        Returns:
            bool: True if cancellation successful
        """
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Order:
        """
        Get order status

        Args:
            order_id: Order ID to retrieve

        Returns:
            Order: Current order status
        """
        pass

    @abstractmethod
    def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all orders or orders for a specific symbol

        Args:
            symbol: Optional symbol filter

        Returns:
            List[Order]: List of orders
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """
        Get current positions

        Returns:
            List[Position]: List of current positions
        """
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol

        Args:
            symbol: Symbol to retrieve

        Returns:
            Optional[Position]: Position if exists, None otherwise
        """
        pass

    @abstractmethod
    def get_account_balance(self) -> AccountBalance:
        """
        Get account balance information

        Returns:
            AccountBalance: Account balance details
        """
        pass

    @abstractmethod
    def subscribe_market_data(self, symbols: List[str]) -> bool:
        """
        Subscribe to market data for symbols

        Args:
            symbols: List of symbols to subscribe

        Returns:
            bool: True if subscription successful
        """
        pass

    @abstractmethod
    def unsubscribe_market_data(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from market data for symbols

        Args:
            symbols: List of symbols to unsubscribe

        Returns:
            bool: True if unsubscription successful
        """
        pass

    @abstractmethod
    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get current market data for a symbol

        Args:
            symbol: Symbol to retrieve

        Returns:
            Dict[str, Any]: Market data including price, bid, ask, volume, etc.
        """
        pass
