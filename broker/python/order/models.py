"""
Order Data Models
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from broker.base import OrderSide, OrderType


class OrderErrorType(Enum):
    """Types of order errors"""

    INSUFFICIENT_FUNDS = "insufficient_funds"
    INSUFFICIENT_POSITION = "insufficient_position"
    INVALID_QUANTITY = "invalid_quantity"
    INVALID_PRICE = "invalid_price"
    INVALID_SYMBOL = "invalid_symbol"
    MARKET_CLOSED = "market_closed"
    RISK_LIMIT_EXCEEDED = "risk_limit_exceeded"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class OrderRequest:
    """Order request from strategy"""

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float | None = None
    stop_price: float | None = None
    time_in_force: str = "DAY"  # DAY, GTC, IOC, FOK
    client_order_id: str | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def validate(self) -> "OrderValidationError":
        """
        Validate order request

        Returns:
            OrderValidationError: Error if invalid, None if valid
        """
        if not self.symbol or not isinstance(self.symbol, str):
            return OrderValidationError(
                error_type=OrderErrorType.INVALID_SYMBOL,
                message="Symbol must be a non-empty string",
            )

        if self.quantity <= 0:
            return OrderValidationError(
                error_type=OrderErrorType.INVALID_QUANTITY,
                message=f"Quantity must be positive, got {self.quantity}",
            )

        if self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and self.price is None:
            return OrderValidationError(
                error_type=OrderErrorType.INVALID_PRICE,
                message="Price is required for limit orders",
            )

        if self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and self.stop_price is None:
            return OrderValidationError(
                error_type=OrderErrorType.INVALID_PRICE,
                message="Stop price is required for stop orders",
            )

        if self.price is not None and self.price <= 0:
            return OrderValidationError(
                error_type=OrderErrorType.INVALID_PRICE,
                message=f"Price must be positive, got {self.price}",
            )

        if self.stop_price is not None and self.stop_price <= 0:
            return OrderValidationError(
                error_type=OrderErrorType.INVALID_PRICE,
                message=f"Stop price must be positive, got {self.stop_price}",
            )

        return None


@dataclass
class OrderResponse:
    """Order response after submission"""

    success: bool
    order_id: str | None = None
    message: str | None = None
    error_type: str | None = None
    client_order_id: str | None = None
    submitted_at: datetime = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.submitted_at is None:
            self.submitted_at = datetime.now()
        if self.metadata is None:
            self.metadata = {}

    @classmethod
    def success_response(cls, order_id: str, client_order_id: str | None = None) -> "OrderResponse":
        """Create a success response"""
        return cls(
            success=True,
            order_id=order_id,
            client_order_id=client_order_id,
            message="Order submitted successfully",
        )

    @classmethod
    def error_response(
        cls, error_type: OrderErrorType, message: str, client_order_id: str | None = None
    ) -> "OrderResponse":
        """Create an error response"""
        return cls(
            success=False,
            error_type=error_type.value,
            message=message,
            client_order_id=client_order_id,
        )


@dataclass
class OrderValidationError:
    """Order validation error"""

    error_type: OrderErrorType
    message: str
    field: str | None = None

    def to_response(self, client_order_id: str | None = None) -> OrderResponse:
        """Convert to order response"""
        return OrderResponse.error_response(self.error_type, self.message, client_order_id)
