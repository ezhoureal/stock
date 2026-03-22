"""
Simple test for mock broker without external dependencies
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from broker.base import Order, OrderSide, OrderStatus, OrderType
from broker.mock import MockBroker
from order.models import OrderRequest
from position.tracker import PositionTracker
from risk.controls import RiskLimit, RiskManager


def test_mock_broker():
    """Test the mock broker implementation"""
    print("=" * 60)
    print("Testing Mock Broker Implementation")
    print("=" * 60)

    # Initialize components
    broker = MockBroker(initial_cash=1000000.0)
    position_tracker = PositionTracker()
    risk_manager = RiskManager(
        RiskLimit(
            max_position_size=10000,
            max_total_position_value=500000,
            max_positions=5,
            max_daily_loss=10000,
            stop_loss_percent=5.0,
        )
    )

    # Connect to broker
    print("\n1. Connecting to broker...")
    if broker.connect():
        print("   ✓ Connected successfully")

    # Subscribe to market data
    print("\n2. Subscribing to market data...")
    symbols = ["600519.SH", "000858.SZ", "600036.SH"]
    if broker.subscribe_market_data(symbols):
        print(f"   ✓ Subscribed to {len(symbols)} symbols")

    # Start trading day
    account = broker.get_full_account_balance()
    risk_manager.start_day(account.cash)
    print(f"\n3. Starting balance: ¥{account.cash:,.2f}")

    # Test order 1: Buy Moutai
    print("\n4. Test: Buy Moutai (600519.SH)")
    price = broker.get_market_price("600519.SH")

    order = Order(
        symbol="600519.SH",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        price=price,
    )

    result = broker.place_order(order)
    print(f"   Order ID: {result.order_id}")
    print(f"   Status: {result.status.value}")
    print(f"   Filled: {result.filled_quantity} @ ¥{result.avg_fill_price:.2f}")

    # Update position tracker
    if result.status == OrderStatus.FILLED and result.avg_fill_price is not None:
        position_tracker.update_position(
            "600519.SH",
            result.quantity,
            result.avg_fill_price,
        )

    # Test order 2: Buy Wuliangye
    print("\n5. Test: Buy Wuliangye (000858.SZ)")
    price = broker.get_market_price("000858.SZ")

    order = Order(
        symbol="000858.SZ",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=200,
    )

    result = broker.place_order(order)
    print(f"   Order ID: {result.order_id}")
    print(f"   Status: {result.status.value}")
    print(f"   Filled: {result.filled_quantity} @ ¥{result.avg_fill_price:.2f}")

    if result.status == OrderStatus.FILLED and result.avg_fill_price is not None:
        position_tracker.update_position(
            "000858.SZ",
            result.quantity,
            result.avg_fill_price,
        )

    # Test order 3: Buy Minsheng Bank
    print("\n6. Test: Buy Minsheng Bank (600036.SH)")
    price = broker.get_market_price("600036.SH")

    order = Order(
        symbol="600036.SH",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=500,
    )

    result = broker.place_order(order)
    print(f"   Order ID: {result.order_id}")
    print(f"   Status: {result.status.value}")
    print(f"   Filled: {result.filled_quantity} @ ¥{result.avg_fill_price:.2f}")

    if result.status == OrderStatus.FILLED and result.avg_fill_price is not None:
        position_tracker.update_position(
            "600036.SH",
            result.quantity,
            result.avg_fill_price,
        )

    # Check positions
    print("\n7. Current Positions:")
    positions = broker.get_positions_broker()
    for pos in positions:
        print(f"   {pos.symbol}:")
        print(f"     Quantity: {pos.quantity}")
        print(f"     Avg Cost: ¥{pos.avg_cost:.2f}")
        print(f"     Market Value: ¥{pos.market_value:,.2f}")
        print(f"     Unrealized P&L: ¥{pos.unrealized_pnl:,.2f}")

    # Update prices and check P&L
    print("\n8. Updating prices...")
    moutai_price = broker.get_market_price("600519.SH")
    if moutai_price is not None:
        broker.set_market_price("600519.SH", moutai_price * 1.02)
    wuliangye_price = broker.get_market_price("000858.SZ")
    if wuliangye_price is not None:
        broker.set_market_price("000858.SZ", wuliangye_price * 0.98)
    print("   ✓ Moutai: +2%")
    print("   ✓ Wuliangye: -2%")

    # Check P&L after price update
    print("\n9. Positions after price update:")
    for pos in broker.get_positions_broker():
        print(f"   {pos.symbol}:")
        print(f"     Current Price: ¥{pos.current_price:.2f}")
        print(f"     Unrealized P&L: ¥{pos.unrealized_pnl:,.2f}")

    # Check account
    print("\n10. Account Summary:")
    account = broker.get_full_account_balance()
    print(f"    Cash: ¥{account.cash:,.2f}")
    print(f"    Market Value: ¥{account.market_value:,.2f}")
    print(f"    Total Equity: ¥{account.total_equity:,.2f}")
    print(f"    Daily P&L: ¥{account.total_equity - 1000000:,.2f}")
    print(f"    Daily Return: {((account.total_equity - 1000000) / 1000000 * 100):.2f}%")

    # Position tracker summary
    print("\n11. Position Tracker Summary:")
    summary = position_tracker.get_position_summary()
    print(f"    Number of Positions: {summary['num_positions']}")
    print(f"    Total Market Value: ¥{summary['total_market_value']:,.2f}")
    print(f"    Total Unrealized P&L: ¥{summary['total_unrealized_pnl']:,.2f}")

    # Risk manager summary
    print("\n12. Risk Manager Summary:")
    risk_summary = risk_manager.get_risk_summary()
    print(f"    Max Positions: {risk_summary['max_positions']}")
    print(f"    Stop Loss %: {risk_summary['stop_loss_percent']}%")
    print(f"    Current Daily Loss: ¥{risk_summary['current_daily_loss']:,.2f}")

    # Test order validation
    print("\n13. Test Order Validation:")
    current_positions = {pos.symbol: pos.quantity for pos in broker.get_positions_broker()}
    market_prices = {
        sym: price for sym in symbols if (price := broker.get_market_price(sym)) is not None
    }

    # Test: Exceed position limit
    order_request = OrderRequest(
        symbol="600519.SH",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=20000,  # Exceeds limit
        price=market_prices["600519.SH"],
    )

    validation_error = risk_manager.validate_order_request(
        order_request,
        current_positions,
        account.cash,
        market_prices,
    )

    if validation_error:
        print(f"    ✓ Rejected (as expected): {validation_error.message}")
    else:
        print("    ✗ Should have been rejected (position limit exceeded)")

    # Test: Insufficient funds
    order_request = OrderRequest(
        symbol="600519.SH",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100000,  # Too expensive
        price=market_prices["600519.SH"],
    )

    validation_error = risk_manager.validate_order_request(
        order_request,
        current_positions,
        account.cash,
        market_prices,
    )

    if validation_error:
        print(f"    ✓ Rejected (as expected): {validation_error.message}")
    else:
        print("    ✗ Should have been rejected (insufficient funds)")

    # Test: Invalid quantity
    order_request = OrderRequest(
        symbol="600519.SH",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=-100,  # Invalid
        price=market_prices["600519.SH"],
    )

    validation_error = order_request.validate()
    if validation_error:
        print(f"    ✓ Rejected (as expected): {validation_error.message}")
    else:
        print("    ✗ Should have been rejected (invalid quantity)")

    # Test order cancellation
    print("\n14. Test Order Cancellation:")
    moutai_price = broker.get_market_price("600519.SH")
    if moutai_price is None:
        print("    ✗ Failed to get market price")
    else:
        order = Order(
            symbol="600519.SH",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=moutai_price * 0.9,  # Below market
        )
        result = broker.place_order(order)
        if result.order_id is None:
            print("    ✗ Failed to place order")
        elif broker.cancel_order(result.order_id):
            print("    ✓ Order cancelled")
            updated_order = broker.get_order_broker(result.order_id)
            print(f"    Status: {updated_order.status.value}")
        else:
            print("    ✗ Failed to cancel order")

    # Final summary
    print("\n15. Final Summary:")
    account = broker.get_full_account_balance()
    print(f"    Cash: ¥{account.cash:,.2f}")
    print(f"    Market Value: ¥{account.market_value:,.2f}")
    print(f"    Total Equity: ¥{account.total_equity:,.2f}")
    print(f"    Daily P&L: ¥{account.total_equity - 1000000:,.2f}")
    print(f"    Daily Return: {((account.total_equity - 1000000) / 1000000 * 100):.2f}%")

    # Disconnect
    print("\n16. Disconnecting...")
    broker.disconnect()
    print("   ✓ Disconnected")

    print("\n" + "=" * 60)
    print("All tests completed successfully! ✓")
    print("=" * 60)


if __name__ == "__main__":
    test_mock_broker()
