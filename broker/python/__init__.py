"""
Broker Integration & Order Execution System
Chinese Stock Sentiment Trading System

This module provides broker abstraction for order execution,
position tracking, and risk management.

Usage:
    from broker import MockBroker, Order, OrderSide, OrderType

    # Create mock broker for testing
    broker = MockBroker(initial_cash=1000000)
    broker.connect()

    # Place an order
    order = Order(
        symbol="600519.SH",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
    )
    result = broker.place_order(order)
"""

__version__ = "0.1.0"
__author__ = "Trading System Engineer"

from .broker.base import (
    AccountBalance,
    BrokerInterface,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from .broker.mock import MockBroker
from .order.models import OrderRequest, OrderResponse, OrderValidationError
from .position.tracker import PositionTracker
from .risk.controls import RiskLimit, RiskManager

__all__ = [
    # Core interfaces
    "BrokerInterface",
    # Data classes
    "Order",
    "Position",
    "AccountBalance",
    # Enums
    "OrderType",
    "OrderSide",
    "OrderStatus",
    # Implementations
    "MockBroker",
]
