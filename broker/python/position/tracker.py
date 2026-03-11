"""
Position Tracker - Track positions and P&L in real-time
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from broker.base import Position


class PositionTracker:
    """Track positions and calculate P&L"""

    def __init__(self):
        """Initialize position tracker"""
        self.positions: dict[str, Position] = {}

    def update_position(self, symbol: str, quantity: int, price: float) -> float:
        """
        Update position with a fill

        Args:
            symbol: Symbol to update
            quantity: Quantity (positive for buy, negative for sell)
            price: Fill price

        Returns:
            float: Realized P&L from this fill
        """
        position = self.positions.get(symbol)

        if position is None:
            # New position
            if quantity > 0:
                # Opening long
                position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    avg_cost=price,
                    current_price=price,
                    market_value=quantity * price,
                )
                self.positions[symbol] = position
            else:
                # Opening short
                position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    avg_cost=price,
                    current_price=price,
                    market_value=abs(quantity) * price,
                )
                self.positions[symbol] = position
            return 0.0
        else:
            # Update existing position
            realized_pnl = position.add_fill(quantity, price)

            # Remove position if flat
            if position.quantity == 0:
                del self.positions[symbol]

            return realized_pnl

    def update_price(self, symbol: str, price: float) -> None:
        """
        Update current price for a position

        Args:
            symbol: Symbol to update
            price: New price
        """
        position = self.positions.get(symbol)
        if position:
            position.update_price(price)

    def get_position(self, symbol: str) -> Position | None:
        """
        Get position for a specific symbol

        Args:
            symbol: Symbol to retrieve

        Returns:
            Optional[Position]: Position if exists
        """
        return self.positions.get(symbol)

    def get_positions(self) -> list[Position]:
        """
        Get all positions

        Returns:
            List[Position]: List of all positions
        """
        return list(self.positions.values())

    def get_total_unrealized_pnl(self) -> float:
        """
        Get total unrealized P&L across all positions

        Returns:
            float: Total unrealized P&L
        """
        return sum(p.unrealized_pnl for p in self.positions.values())

    def get_total_realized_pnl(self) -> float:
        """
        Get total realized P&L

        Returns:
            float: Total realized P&L
        """
        return sum(p.realized_pnl for p in self.positions.values())

    def get_total_market_value(self) -> float:
        """
        Get total market value of all positions

        Returns:
            float: Total market value
        """
        return sum(p.market_value for p in self.positions.values())

    def get_total_quantity(self, symbol: str | None = None) -> int:
        """
        Get total quantity (for specific symbol or all)

        Args:
            symbol: Optional symbol filter

        Returns:
            int: Total quantity
        """
        if symbol is not None:
            position = self.positions.get(symbol)
            return position.quantity if position else 0
        else:
            return sum(abs(p.quantity) for p in self.positions.values())

    def is_long(self, symbol: str) -> bool:
        """Check if position is long for a symbol"""
        position = self.positions.get(symbol)
        return position is not None and position.is_long

    def is_short(self, symbol: str) -> bool:
        """Check if position is short for a symbol"""
        position = self.positions.get(symbol)
        return position is not None and position.is_short

    def is_flat(self, symbol: str) -> bool:
        """Check if no position for a symbol"""
        return symbol not in self.positions

    def close_position(self, symbol: str, price: float) -> float | None:
        """
        Close entire position for a symbol

        Args:
            symbol: Symbol to close
            price: Closing price

        Returns:
            Optional[float]: Realized P&L if position existed
        """
        position = self.positions.get(symbol)
        if position is None:
            return None

        # Close entire position
        quantity_to_close = -position.quantity
        realized_pnl = self.update_position(symbol, quantity_to_close, price)

        return realized_pnl

    def get_position_summary(self) -> dict[str, any]:
        """
        Get position summary

        Returns:
            Dict with position summary information
        """
        return {
            "num_positions": len(self.positions),
            "total_market_value": self.get_total_market_value(),
            "total_unrealized_pnl": self.get_total_unrealized_pnl(),
            "total_realized_pnl": self.get_total_realized_pnl(),
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_cost": p.avg_cost,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                }
                for p in self.positions.values()
            ],
        }
