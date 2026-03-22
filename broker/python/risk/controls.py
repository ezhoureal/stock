"""
Risk Controls - Position limits, stop-loss, and risk management
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from broker.base import Order, OrderSide, Position
from order.models import OrderErrorType, OrderRequest, OrderValidationError


@dataclass
class RiskLimit:
    """Risk limit configuration"""

    max_position_size: int = 10000
    max_total_position_value: float = 1000000.0
    max_positions: int = 10
    max_daily_loss: float = 5000.0
    stop_loss_percent: float = 5.0
    max_order_value: float = 100000.0


@dataclass
class DailyLossTracker:
    """Track daily losses"""

    date: datetime  # Will store the datetime when day starts
    start_balance: float
    current_balance: float
    realized_pnl: float

    @property
    def daily_loss(self) -> float:
        """Calculate daily loss"""
        return self.start_balance - self.current_balance


class RiskManager:
    """Risk manager for order validation and position monitoring"""

    def __init__(self, limits: RiskLimit | None = None):
        """
        Initialize risk manager

        Args:
            limits: Risk limit configuration
        """
        self.limits = limits or RiskLimit()
        self.daily_tracker: DailyLossTracker | None = None
        self.position_limits: dict[str, int] = {}
        self.stop_loss_orders: dict[str, Order] = {}

    def set_position_limit(self, symbol: str, limit: int) -> None:
        """
        Set custom position limit for a symbol

        Args:
            symbol: Symbol to set limit for
            limit: Max position size
        """
        self.position_limits[symbol] = limit

    def get_position_limit(self, symbol: str) -> int:
        """
        Get position limit for a symbol

        Args:
            symbol: Symbol to get limit for

        Returns:
            int: Position limit
        """
        return self.position_limits.get(symbol, self.limits.max_position_size)

    def start_day(self, balance: float) -> None:
        """
        Start tracking a new trading day

        Args:
            balance: Starting account balance
        """
        self.daily_tracker = DailyLossTracker(
            date=datetime.now(),
            start_balance=balance,
            current_balance=balance,
            realized_pnl=0.0,
        )

    def update_balance(self, balance: float) -> None:
        """
        Update current balance

        Args:
            balance: New balance
        """
        if self.daily_tracker:
            self.daily_tracker.current_balance = balance

    def update_realized_pnl(self, realized_pnl: float) -> None:
        """
        Update realized P&L

        Args:
            realized_pnl: Cumulative realized P&L
        """
        if self.daily_tracker:
            self.daily_tracker.realized_pnl = realized_pnl

    def validate_order_request(
        self,
        order_request: OrderRequest,
        current_positions: dict[str, int],
        account_balance: float,
        market_prices: dict[str, float],
    ) -> OrderValidationError | None:
        """
        Validate order request against risk limits

        Args:
            order_request: Order request to validate
            current_positions: Current positions by symbol
            account_balance: Current account balance
            market_prices: Current market prices

        Returns:
            OrderValidationError: Error if validation fails, None otherwise
        """
        # Validate basic order parameters
        validation_error = order_request.validate()
        if validation_error:
            return validation_error

        # Get current position
        current_qty = current_positions.get(order_request.symbol, 0)

        # Calculate new position size
        if order_request.side == OrderSide.BUY:
            new_qty = current_qty + order_request.quantity
        else:  # SELL
            new_qty = current_qty - order_request.quantity

        # Check position limit
        position_limit = self.get_position_limit(order_request.symbol)
        if abs(new_qty) > position_limit:
            return OrderValidationError(
                error_type=OrderErrorType.RISK_LIMIT_EXCEEDED,
                message=f"Position limit exceeded: {abs(new_qty)} > {position_limit}",
                field="quantity",
            )

        # Check max positions
        if current_qty == 0 and new_qty != 0:
            # Opening new position
            num_positions = sum(1 for q in current_positions.values() if q != 0)
            if num_positions >= self.limits.max_positions:
                return OrderValidationError(
                    error_type=OrderErrorType.RISK_LIMIT_EXCEEDED,
                    message=f"Max positions exceeded: {num_positions} >= {self.limits.max_positions}",
                )

        # Check order value
        price = market_prices.get(order_request.symbol)
        if price is None and order_request.price is None:
            return OrderValidationError(
                error_type=OrderErrorType.INVALID_PRICE,
                message=f"Market price not available for {order_request.symbol}",
            )

        execution_price = order_request.price or price
        if execution_price is None:
            return OrderValidationError(
                error_type=OrderErrorType.INVALID_PRICE,
                message=f"Execution price is None for {order_request.symbol}",
            )
        order_value = execution_price * order_request.quantity

        if order_value > self.limits.max_order_value:
            return OrderValidationError(
                error_type=OrderErrorType.RISK_LIMIT_EXCEEDED,
                message=f"Order value exceeds limit: {order_value} > {self.limits.max_order_value}",
            )

        # Check total position value
        new_total_value = (
            sum(abs(q) * market_prices.get(sym, 0) for sym, q in current_positions.items())
            + order_value
        )

        if new_total_value > self.limits.max_total_position_value:
            return OrderValidationError(
                error_type=OrderErrorType.RISK_LIMIT_EXCEEDED,
                message=f"Total position value exceeds limit: {new_total_value} > {self.limits.max_total_position_value}",
            )

        # Check daily loss
        if self.daily_tracker:
            if self.daily_tracker.daily_loss >= self.limits.max_daily_loss:
                return OrderValidationError(
                    error_type=OrderErrorType.RISK_LIMIT_EXCEEDED,
                    message=f"Daily loss limit reached: {self.daily_tracker.daily_loss} >= {self.limits.max_daily_loss}",
                )

        # Check funds for buy orders
        if order_request.side == OrderSide.BUY:
            if order_value > account_balance:
                return OrderValidationError(
                    error_type=OrderErrorType.INSUFFICIENT_FUNDS,
                    message=f"Insufficient funds: {order_value} > {account_balance}",
                )

        # Check position for sell orders
        if order_request.side == OrderSide.SELL:
            if order_request.quantity > abs(current_qty):
                return OrderValidationError(
                    error_type=OrderErrorType.INSUFFICIENT_POSITION,
                    message=f"Insufficient position: {order_request.quantity} > {abs(current_qty)}",
                )

        return None

    def check_stop_loss(self, positions: list[Position]) -> list[str]:
        """
        Check if any positions hit stop-loss

        Args:
            positions: Current positions

        Returns:
            List[str]: Symbols that hit stop-loss
        """
        stop_loss_symbols = []

        for position in positions:
            # Calculate P&L percentage
            if position.quantity > 0:  # Long
                pnl_percent = (position.current_price - position.avg_cost) / position.avg_cost * 100
            else:  # Short
                pnl_percent = (position.avg_cost - position.current_price) / position.avg_cost * 100

            # Check stop-loss
            if pnl_percent <= -self.limits.stop_loss_percent:
                stop_loss_symbols.append(position.symbol)

        return stop_loss_symbols

    def should_close_positions(self, positions: list[Position]) -> bool:
        """
        Check if we should close all positions due to risk limits

        Args:
            positions: Current positions

        Returns:
            bool: True if positions should be closed
        """
        # Check daily loss
        if self.daily_tracker and self.daily_tracker.daily_loss >= self.limits.max_daily_loss:
            return True

        return False

    def get_daily_loss(self) -> float:
        """
        Get current daily loss

        Returns:
            float: Daily loss (0 if not tracking)
        """
        if self.daily_tracker:
            return self.daily_tracker.daily_loss
        return 0.0

    def is_daily_limit_reached(self) -> bool:
        """
        Check if daily loss limit is reached

        Returns:
            bool: True if limit reached
        """
        if self.daily_tracker:
            return self.daily_tracker.daily_loss >= self.limits.max_daily_loss
        return False

    def get_risk_summary(self) -> dict[str, Any]:
        """
        Get risk summary

        Returns:
            Dict with risk summary information
        """
        return {
            "max_position_size": self.limits.max_position_size,
            "max_total_position_value": self.limits.max_total_position_value,
            "max_positions": self.limits.max_positions,
            "max_daily_loss": self.limits.max_daily_loss,
            "stop_loss_percent": self.limits.stop_loss_percent,
            "current_daily_loss": self.get_daily_loss(),
            "daily_limit_reached": self.is_daily_limit_reached(),
            "custom_position_limits": len(self.position_limits),
        }
