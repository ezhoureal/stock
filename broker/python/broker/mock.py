"""
Mock Broker Implementation for Testing
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import time
import uuid

from .base import (
    BrokerInterface,
    Order,
    Position,
    AccountBalance,
    OrderType,
    OrderSide,
    OrderStatus,
)


class MockBroker(BrokerInterface):
    """Mock broker implementation for testing without real broker connection"""

    def __init__(self, initial_cash: float = 1000000.0):
        """
        Initialize mock broker

        Args:
            initial_cash: Initial cash balance
        """
        self.connected = False
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.market_prices: Dict[str, float] = {}
        self.market_data: Dict[str, Dict[str, Any]] = {}

    def connect(self) -> bool:
        """Connect to the mock broker"""
        self.connected = True
        print(f"[MockBroker] Connected (Initial Cash: ¥{self.cash:,.2f})")
        return True

    def disconnect(self) -> bool:
        """Disconnect from the mock broker"""
        self.connected = False
        print("[MockBroker] Disconnected")
        return True

    def is_connected(self) -> bool:
        """Check if connected"""
        return self.connected

    def place_order(self, order: Order) -> Order:
        """Place an order"""
        if not self.connected:
            raise RuntimeError("Not connected to broker")

        # Generate order ID
        order.order_id = f"MOCK-{uuid.uuid4().hex[:8].upper()}"

        # Validate order
        if order.quantity <= 0:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "Quantity must be positive"
            self.orders[order.order_id] = order
            return order

        if order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and order.price is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "Price required for limit orders"
            self.orders[order.order_id] = order
            return order

        if order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and order.stop_price is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "Stop price required for stop orders"
            self.orders[order.order_id] = order
            return order

        # Check balance for buy orders
        if order.side == OrderSide.BUY:
            if order.order_type == OrderType.MARKET:
                price = self.market_prices.get(order.symbol, 10.0)
            else:
                price = order.price

            required = price * order.quantity
            if required > self.cash:
                order.status = OrderStatus.REJECTED
                order.reject_reason = "Insufficient funds"
                self.orders[order.order_id] = order
                return order

        # Check position for sell orders
        if order.side == OrderSide.SELL:
            position = self.positions.get(order.symbol)
            if position is None or position.quantity < order.quantity:
                order.status = OrderStatus.REJECTED
                order.reject_reason = "Insufficient position"
                self.orders[order.order_id] = order
                return order

        # Simulate order execution
        self._simulate_execution(order)

        self.orders[order.order_id] = order
        return order

    def _simulate_execution(self, order: Order) -> None:
        """Simulate order execution"""
        # Get execution price
        if order.order_type == OrderType.MARKET:
            execution_price = self.market_prices.get(order.symbol, 10.0)
        elif order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            execution_price = order.price
        else:  # STOP
            execution_price = self.market_prices.get(order.symbol, 10.0)

        # For simplicity, fill immediately
        order.add_fill(order.quantity, execution_price)

        # Update cash and positions
        if order.side == OrderSide.BUY:
            cost = execution_price * order.quantity
            self.cash -= cost

            # Update position
            position = self.positions.get(order.symbol)
            if position is None:
                position = Position(
                    symbol=order.symbol,
                    quantity=order.quantity,
                    avg_cost=execution_price,
                    current_price=execution_price,
                    market_value=execution_price * order.quantity,
                )
                self.positions[order.symbol] = position
            else:
                position.add_fill(order.quantity, execution_price)
        else:  # SELL
            proceeds = execution_price * order.quantity
            self.cash += proceeds

            # Update position
            position = self.positions.get(order.symbol)
            if position:
                realized_pnl = position.add_fill(-order.quantity, execution_price)
                if position.quantity == 0:
                    del self.positions[order.symbol]

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if not self.connected:
            raise RuntimeError("Not connected to broker")

        order = self.orders.get(order_id)
        if order is None:
            return False

        if order.is_complete:
            return False

        order.update_status(OrderStatus.CANCELLED)
        return True

    def get_order(self, order_id: str) -> Order:
        """Get order status"""
        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")
        return order

    def get_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all orders or orders for a specific symbol"""
        orders = list(self.orders.values())
        if symbol is not None:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def get_positions(self) -> List[Position]:
        """Get current positions"""
        return list(self.positions.values())

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol"""
        return self.positions.get(symbol)

    def get_account_balance(self) -> AccountBalance:
        """Get account balance information"""
        total_market_value = sum(p.market_value for p in self.positions.values())
        total_equity = self.cash + total_market_value

        return AccountBalance(
            total_equity=total_equity,
            cash=self.cash,
            buying_power=self.cash * 2,  # Assuming 2x margin
            margin_used=total_market_value * 0.5,
            available_withdrawal=self.cash,
            market_value=total_market_value,
        )

    def subscribe_market_data(self, symbols: List[str]) -> bool:
        """Subscribe to market data"""
        for symbol in symbols:
            if symbol not in self.market_prices:
                self.market_prices[symbol] = 10.0 + hash(symbol) % 100
            self.market_data[symbol] = {
                'price': self.market_prices[symbol],
                'bid': self.market_prices[symbol] * 0.995,
                'ask': self.market_prices[symbol] * 1.005,
                'volume': 1000000,
                'timestamp': datetime.now(),
            }
        return True

    def unsubscribe_market_data(self, symbols: List[str]) -> bool:
        """Unsubscribe from market data"""
        for symbol in symbols:
            if symbol in self.market_data:
                del self.market_data[symbol]
        return True

    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """Get current market data"""
        if symbol not in self.market_data:
            # Auto-subscribe if not subscribed
            self.subscribe_market_data([symbol])

        return self.market_data.get(symbol, {})

    def get_market_price(self, symbol: str) -> Optional[float]:
        """
        Get current market price for a symbol

        Args:
            symbol: Symbol to get price for

        Returns:
            Optional[float]: Current price or None
        """
        market_data = self.get_market_data(symbol)
        return market_data.get('price')

    def set_market_price(self, symbol: str, price: float) -> None:
        """
        Set market price for testing

        Args:
            symbol: Symbol to set price for
            price: New price
        """
        self.market_prices[symbol] = price
        if symbol in self.market_data:
            self.market_data[symbol]['price'] = price
            self.market_data[symbol]['bid'] = price * 0.995
            self.market_data[symbol]['ask'] = price * 1.005

        # Update position if exists
        if symbol in self.positions:
            self.positions[symbol].update_price(price)

    def advance_time(self, seconds: float = 1.0) -> None:
        """
        Simulate time passing for testing

        Args:
            seconds: Seconds to advance
        """
        time.sleep(0)  # In real implementation, might actually sleep
        # Update timestamps in market data
        for symbol, data in self.market_data.items():
            data['timestamp'] = datetime.now()
