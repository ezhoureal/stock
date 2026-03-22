"""
Main entry point for Broker Integration System
"""

import argparse
import logging
import os
import sys
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from broker.base import Order, OrderSide, OrderStatus, OrderType
from broker.mock import MockBroker
from order.models import OrderRequest
from position.tracker import PositionTracker
from risk.controls import RiskLimit, RiskManager

# Import Config from local config module
import config as config_module  # noqa: E402

Config = config_module.Config  # type: ignore[attr-defined]


def setup_logging(config: Any) -> logging.Logger:
    """Setup logging"""
    logger = logging.getLogger("broker")
    logger.setLevel(getattr(logging, config.logging.log_level))

    if config.logging.log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if config.logging.log_file:
        file_handler = logging.FileHandler(config.logging.log_file)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def test_paper_trading(logger: logging.Logger) -> None:
    """
    Test paper trading with mock broker

    Args:
        logger: Logger instance
    """
    logger.info("Starting paper trading test...")

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
    broker.connect()

    # Subscribe to market data
    broker.subscribe_market_data(["600519.SH", "000858.SZ"])

    # Start trading day
    account = broker.get_full_account_balance()
    risk_manager.start_day(account.cash)

    logger.info(f"Starting balance: ¥{account.cash:,.2f}")

    # Test order 1: Buy Moutai
    logger.info("\n=== Test 1: Buy Moutai ===")
    price_opt = broker.get_market_price("600519.SH")
    if price_opt is None:
        logger.error("Failed to get market price for 600519.SH")
        return
    price: float = price_opt

    order_request = OrderRequest(
        symbol="600519.SH",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        price=price,
    )

    # Validate order
    current_positions = {pos.symbol: int(pos.quantity) for pos in broker.get_positions()}
    # Only include prices that are not None
    market_prices: dict[str, float] = {"600519.SH": price}

    validation_error = risk_manager.validate_order_request(
        order_request,
        current_positions,
        account.cash,
        market_prices,
    )

    if validation_error:
        logger.error(f"Order validation failed: {validation_error.message}")
    else:
        order = Order(
            symbol=order_request.symbol,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            price=order_request.price,
        )
        result = broker.place_order(order)
        logger.info(f"Order placed: {result.order_id} - Status: {result.status.value}")

        # Update position tracker
        if result.status == OrderStatus.FILLED:
            fill_price = order_request.price if order_request.price is not None else price
            position_tracker.update_position(
                order_request.symbol,
                order_request.quantity,
                fill_price,
            )
            logger.info(f"Position updated: {position_tracker.get_position('600519.SH')}")

    # Test order 2: Buy Wuliangye
    logger.info("\n=== Test 2: Buy Wuliangye ===")
    price_opt = broker.get_market_price("000858.SZ")
    if price_opt is None:
        logger.error("Failed to get market price for 000858.SZ")
        return
    price_wl: float = price_opt

    order_request = OrderRequest(
        symbol="000858.SZ",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=200,
    )

    market_prices_wl: dict[str, float] = {"000858.SZ": price_wl}
    validation_error = risk_manager.validate_order_request(
        order_request,
        {pos.symbol: int(pos.quantity) for pos in broker.get_positions()},
        account.cash,
        market_prices_wl,
    )

    if not validation_error:
        order = Order(
            symbol=order_request.symbol,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
        )
        result = broker.place_order(order)
        logger.info(f"Order placed: {result.order_id} - Status: {result.status.value}")

        if result.status == OrderStatus.FILLED:
            fill_price = order_request.price if order_request.price is not None else price_wl
            position_tracker.update_position(
                order_request.symbol,
                order_request.quantity,
                fill_price,
            )
            logger.info(f"Position updated: {position_tracker.get_position('000858.SZ')}")

    # Check positions
    logger.info("\n=== Current Positions ===")
    positions = broker.get_positions()
    for pos in positions:
        logger.info(f"{pos.symbol}: {pos.quantity} shares @ ¥{pos.entry_price:.2f}")

    # Check account
    logger.info("\n=== Account Summary ===")
    account = broker.get_full_account_balance()
    logger.info(f"Cash: ¥{account.cash:,.2f}")
    logger.info(f"Market Value: ¥{account.market_value:,.2f}")
    logger.info(f"Total Equity: ¥{account.total_equity:,.2f}")

    # Test order 3: Sell half of Moutai
    logger.info("\n=== Test 3: Sell half of Moutai ===")
    moutai_pos = broker.get_position("600519.SH")
    if moutai_pos:
        order_request = OrderRequest(
            symbol="600519.SH",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=int(moutai_pos.quantity // 2),
        )

        price_sell_opt = broker.get_market_price("600519.SH")
        if price_sell_opt is None:
            logger.error("Failed to get market price for 600519.SH")
            return
        price_sell: float = price_sell_opt
        market_prices_mt: dict[str, float] = {"600519.SH": price_sell}
        validation_error = risk_manager.validate_order_request(
            order_request,
            {pos.symbol: int(pos.quantity) for pos in broker.get_positions()},
            account.cash,
            market_prices_mt,
        )

        if not validation_error:
            order = Order(
                symbol=order_request.symbol,
                side=order_request.side,
                order_type=order_request.order_type,
                quantity=order_request.quantity,
            )
            result = broker.place_order(order)
            logger.info(f"Order placed: {result.order_id} - Status: {result.status.value}")

    # Final summary
    logger.info("\n=== Final Summary ===")
    account = broker.get_full_account_balance()
    logger.info(f"Cash: ¥{account.cash:,.2f}")
    logger.info(f"Market Value: ¥{account.market_value:,.2f}")
    logger.info(f"Total Equity: ¥{account.total_equity:,.2f}")
    logger.info(f"Daily P&L: ¥{account.total_equity - 1000000:,.2f}")

    logger.info("\nPosition Summary:")
    logger.info(position_tracker.get_position_summary())

    logger.info("\nRisk Summary:")
    logger.info(risk_manager.get_risk_summary())

    # Disconnect
    broker.disconnect()
    logger.info("\nPaper trading test completed!")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Broker Integration & Order Execution System")
    parser.add_argument("--paper-trading", action="store_true", help="Run in paper trading mode")
    parser.add_argument("--config", type=str, help="Path to config file")

    args = parser.parse_args()

    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return 1

    # Setup logging
    logger = setup_logging(Config)
    logger.info("Broker Integration System starting...")
    logger.info(f"Broker type: {Config.broker.broker_type}")
    logger.info(f"Paper trading: {Config.broker.paper_trading}")

    # Run paper trading test if requested
    if args.paper_trading:
        test_paper_trading(logger)
    else:
        logger.info("No action specified. Use --paper-trading to run tests.")

    logger.info("Done!")
    return 0


if __name__ == "__main__":
    exit(main())
