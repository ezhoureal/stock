"""
Main entry point for Broker Integration System
"""
import argparse
import logging
from typing import Optional

from config import Config
from broker.base import Order, OrderType, OrderSide, OrderStatus
from broker.mock import MockBroker
from order.models import OrderRequest, OrderResponse
from position.tracker import PositionTracker
from risk.controls import RiskManager, RiskLimit


def setup_logging(config: Config) -> logging.Logger:
    """Setup logging"""
    logger = logging.getLogger('broker')
    logger.setLevel(getattr(logging, config.logging.log_level))

    if config.logging.log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if config.logging.log_file:
        file_handler = logging.FileHandler(config.logging.log_file)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
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
    risk_manager = RiskManager(RiskLimit(
        max_position_size=10000,
        max_total_position_value=500000,
        max_positions=5,
        max_daily_loss=10000,
        stop_loss_percent=5.0,
    ))

    # Connect to broker
    broker.connect()

    # Subscribe to market data
    broker.subscribe_market_data(['600519.SH', '000858.SZ'])

    # Start trading day
    account = broker.get_account_balance()
    risk_manager.start_day(account.cash)

    logger.info(f"Starting balance: ¥{account.cash:,.2f}")

    # Test order 1: Buy Moutai
    logger.info("\n=== Test 1: Buy Moutai ===")
    price = broker.get_market_price('600519.SH')

    order_request = OrderRequest(
        symbol='600519.SH',
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        price=price,
    )

    # Validate order
    current_positions = {sym: pos.quantity for sym, pos in broker.get_positions()}
    market_prices = {'600519.SH': price}

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
            position_tracker.update_position(
                order_request.symbol,
                order_request.quantity,
                order_request.price or price,
            )
            logger.info(f"Position updated: {position_tracker.get_position('600519.SH')}")

    # Test order 2: Buy Wuliangye
    logger.info("\n=== Test 2: Buy Wuliangye ===")
    price = broker.get_market_price('000858.SZ')

    order_request = OrderRequest(
        symbol='000858.SZ',
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=200,
    )

    validation_error = risk_manager.validate_order_request(
        order_request,
        {sym: pos.quantity for sym, pos in broker.get_positions()},
        account.cash,
        {'000858.SZ': price},
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
            position_tracker.update_position(
                order_request.symbol,
                order_request.quantity,
                price,
            )
            logger.info(f"Position updated: {position_tracker.get_position('000858.SZ')}")

    # Check positions
    logger.info("\n=== Current Positions ===")
    positions = broker.get_positions()
    for pos in positions:
        logger.info(f"{pos.symbol}: {pos.quantity} shares @ ¥{pos.avg_cost:.2f}")

    # Check account
    logger.info("\n=== Account Summary ===")
    account = broker.get_account_balance()
    logger.info(f"Cash: ¥{account.cash:,.2f}")
    logger.info(f"Market Value: ¥{account.market_value:,.2f}")
    logger.info(f"Total Equity: ¥{account.total_equity:,.2f}")

    # Test order 3: Sell half of Moutai
    logger.info("\n=== Test 3: Sell half of Moutai ===")
    moutai_pos = broker.get_position('600519.SH')
    if moutai_pos:
        order_request = OrderRequest(
            symbol='600519.SH',
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=moutai_pos.quantity // 2,
        )

        validation_error = risk_manager.validate_order_request(
            order_request,
            {sym: pos.quantity for sym, pos in broker.get_positions()},
            account.cash,
            {'600519.SH': broker.get_market_price('600519.SH')},
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
    account = broker.get_account_balance()
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
    parser = argparse.ArgumentParser(
        description='Broker Integration & Order Execution System'
    )
    parser.add_argument(
        '--paper-trading',
        action='store_true',
        help='Run in paper trading mode'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to config file'
    )

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


if __name__ == '__main__':
    exit(main())
