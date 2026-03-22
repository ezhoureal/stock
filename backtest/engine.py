"""
Backtesting Engine Implementation

Provides a comprehensive backtesting framework for testing strategies
against historical data with realistic execution simulation.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from common.config import BacktestConfig
from common.interfaces import (
    BacktestEngine,
    BacktestResult,
    DataProvider,
    SignalGenerator,
)
from common.types import (
    Order,
    Position,
    SignalType,
    TimeFrame,
    Trade,
    TradingSignal,
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestState:
    """Internal state for backtest execution"""

    cash: float
    positions: dict[str, Position]
    equity_curve: list[dict[str, Any]]
    trades: list[Trade]
    signals: list[TradingSignal]
    pending_orders: list[Order]
    daily_pnl: list[float]
    peak_equity: float = 0.0
    max_drawdown: float = 0.0


class BacktestEngineImpl(BacktestEngine):
    """
    Comprehensive backtesting engine.

    Features:
    - Multiple fill models (next_open, close, vwap)
    - Realistic cost modeling (commission, slippage, stamp duty)
    - Position tracking and P&L calculation
    - Performance metrics (Sharpe, drawdown, win rate)
    - Support for both long and short positions
    """

    def __init__(
        self,
        data_provider: DataProvider,
        config: BacktestConfig | None = None,
    ):
        """
        Initialize backtest engine.

        Args:
            data_provider: Data source for historical data
            config: Backtest configuration
        """
        self.data_provider = data_provider
        self.config = config or BacktestConfig()
        self._commission_rate = self.config.commission_rate
        self._min_commission = self.config.min_commission
        self._slippage_rate = self.config.slippage_rate
        self._stamp_duty = self.config.stamp_duty

    def run(
        self,
        strategy: SignalGenerator,
        symbols: list[str],
        start: datetime,
        end: datetime,
        initial_capital: float = 1000000.0,
    ) -> BacktestResult:
        """
        Run backtest for a strategy.

        Args:
            strategy: Strategy to test
            symbols: List of symbols to trade
            start: Start datetime
            end: End datetime
            initial_capital: Starting capital

        Returns:
            BacktestResult with performance metrics
        """
        logger.info(f"Starting backtest for {strategy.name}")
        logger.info(f"  Period: {start.date()} to {end.date()}")
        logger.info(f"  Symbols: {len(symbols)}")
        logger.info(f"  Initial capital: ¥{initial_capital:,.2f}")

        # Initialize state
        state = BacktestState(
            cash=initial_capital,
            positions={},
            equity_curve=[],
            trades=[],
            signals=[],
            pending_orders=[],
            daily_pnl=[],
            peak_equity=initial_capital,
        )

        # Load historical data
        logger.info("Loading historical data...")
        price_data = self._load_price_data(symbols, start, end)

        if price_data.empty:
            logger.error("No price data available")
            return self._create_empty_result(initial_capital)

        # Get unique trading dates
        trading_dates = self._get_trading_dates(price_data)
        logger.info(f"  Trading days: {len(trading_dates)}")

        # Main backtest loop
        for current_date in trading_dates:
            # Get current prices
            current_prices = self._get_prices_for_date(price_data, current_date)

            # Update position prices
            self._update_position_prices(state, current_prices)

            # Process pending orders from previous day
            self._process_pending_orders(state, current_prices, current_date)

            # Generate signals
            signals = strategy.generate_signals(
                symbols,
                current_date,
                self.data_provider,
            )

            # Process signals
            for signal in signals:
                signal.timestamp = current_date
                state.signals.append(signal)
                self._process_signal(state, signal, current_prices, current_date)

            # Calculate daily P&L and equity
            daily_equity = self._calculate_equity(state, current_prices)
            state.equity_curve.append(
                {
                    "date": current_date,
                    "equity": daily_equity,
                    "cash": state.cash,
                    "positions_value": daily_equity - state.cash,
                }
            )

            # Track drawdown
            if daily_equity > state.peak_equity:
                state.peak_equity = daily_equity

            drawdown = (state.peak_equity - daily_equity) / state.peak_equity
            if drawdown > state.max_drawdown:
                state.max_drawdown = drawdown

            # Check max drawdown stop
            if self.config.max_drawdown_stop and drawdown >= self.config.max_drawdown_stop:
                logger.warning(f"Max drawdown stop triggered at {drawdown:.2%}")
                break

        # Calculate final metrics
        result = self._calculate_metrics(state, initial_capital, start, end)

        # Save outputs
        self._save_results(result, strategy.name)

        logger.info("Backtest complete:")
        logger.info(f"  Total return: {result.total_return:.2%}")
        logger.info(f"  Sharpe ratio: {result.sharpe_ratio:.2f}")
        logger.info(f"  Max drawdown: {result.max_drawdown:.2%}")

        return result

    def set_commission(self, commission_rate: float, min_commission: float = 0.0) -> None:
        """Set commission rates"""
        self._commission_rate = commission_rate
        self._min_commission = min_commission

    def set_slippage(self, slippage_rate: float) -> None:
        """Set slippage rate"""
        self._slippage_rate = slippage_rate

    def _load_price_data(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Load historical price data"""
        try:
            df = self.data_provider.get_prices(
                symbols,
                start,
                end,
                TimeFrame.DAY_1,
            )
            return df
        except Exception as e:
            logger.error(f"Error loading price data: {e}")
            return pd.DataFrame()

    def _get_trading_dates(self, price_data: pd.DataFrame) -> list[datetime]:
        """Extract unique trading dates from price data"""
        if isinstance(price_data.index, pd.MultiIndex):
            # MultiIndex (symbol, timestamp)
            dates = price_data.index.get_level_values(1).unique()
        else:
            # Single index (timestamp)
            dates = price_data.index.unique()

        return sorted(dates.tolist())

    def _get_prices_for_date(
        self,
        price_data: pd.DataFrame,
        date: datetime,
    ) -> dict[str, float]:
        """Get closing prices for a specific date"""
        prices = {}

        if isinstance(price_data.index, pd.MultiIndex):
            try:
                day_data = price_data.xs(date, level=1)
                for symbol in day_data.index:
                    prices[symbol] = float(day_data.loc[symbol, "close"])
            except KeyError:
                pass
        else:
            try:
                day_data = price_data.loc[date]
                if isinstance(day_data, pd.DataFrame):
                    for _, row in day_data.iterrows():
                        if "symbol" in row:
                            prices[row["symbol"]] = float(row["close"])
            except KeyError:
                pass

        return prices

    def _update_position_prices(
        self,
        state: BacktestState,
        current_prices: dict[str, float],
    ) -> None:
        """Update position prices with current market data"""
        for symbol, position in state.positions.items():
            if symbol in current_prices:
                position.update_price(current_prices[symbol])

    def _process_pending_orders(
        self,
        state: BacktestState,
        current_prices: dict[str, float],
        current_date: datetime,
    ) -> None:
        """Process any pending orders"""
        filled_orders = []

        for order in state.pending_orders:
            if order.symbol not in current_prices:
                continue

            fill_price = self._calculate_fill_price(
                order,
                current_prices[order.symbol],
            )

            if fill_price:
                self._execute_order(state, order, fill_price, current_date)
                filled_orders.append(order)

        for order in filled_orders:
            state.pending_orders.remove(order)

    def _calculate_fill_price(
        self,
        order: Order,
        current_price: float,
    ) -> float | None:
        """Calculate fill price based on fill model"""
        if self.config.fill_model == "next_open":
            # Use current price (simplified - in reality would use next day's open)
            fill_price = current_price
        elif self.config.fill_model == "close":
            fill_price = current_price
        elif self.config.fill_model == "vwap":
            # Simplified VWAP - add small premium
            fill_price = current_price * 1.001 if order.side == "BUY" else current_price * 0.999
        else:
            fill_price = current_price

        # Apply slippage
        if order.side == "BUY":
            fill_price *= 1 + self._slippage_rate
        else:
            fill_price *= 1 - self._slippage_rate

        return fill_price

    def _execute_order(
        self,
        state: BacktestState,
        order: Order,
        fill_price: float,
        current_date: datetime,
    ) -> None:
        """Execute an order and create corresponding trade and position"""
        symbol = order.symbol
        quantity = order.quantity
        side = order.side

        # Calculate commission
        notional = quantity * fill_price
        commission = max(notional * self._commission_rate, self._min_commission)

        if side == "BUY":
            # Update cash
            state.cash -= notional + commission

            # Create or update position
            if symbol in state.positions:
                # Add to existing position
                existing_pos = state.positions[symbol]
                total_quantity = existing_pos.quantity + quantity
                # Weighted average entry price
                total_cost = (
                    existing_pos.entry_price * existing_pos.quantity + fill_price * quantity
                )
                new_entry_price = total_cost / total_quantity
                existing_pos.quantity = total_quantity
                existing_pos.entry_price = new_entry_price
            else:
                # Create new position
                state.positions[symbol] = Position(
                    symbol=symbol,
                    side="long",
                    quantity=quantity,
                    entry_price=fill_price,
                    entry_time=current_date,
                    current_price=fill_price,
                )
        else:  # SELL
            # Calculate stamp duty (China A-shares, sell only)
            stamp_duty = notional * self._stamp_duty
            total_commission = commission + stamp_duty

            # Update cash
            state.cash += notional - total_commission

            # Update or close position
            if symbol in state.positions:
                existing_pos = state.positions[symbol]
                if quantity >= existing_pos.quantity:
                    # Close position
                    del state.positions[symbol]
                else:
                    # Partial close
                    existing_pos.quantity -= quantity
            else:
                # Short position (create new)
                state.positions[symbol] = Position(
                    symbol=symbol,
                    side="short",
                    quantity=quantity,
                    entry_price=fill_price,
                    entry_time=current_date,
                    current_price=fill_price,
                )

        # Create trade record
        slippage_amount = abs(fill_price - order.limit_price if order.limit_price else 0) * quantity
        trade = Trade(
            trade_id=f"{symbol}_{current_date.strftime('%Y%m%d_%H%M%S')}",
            order_id=order.order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=fill_price,
            timestamp=current_date,
            commission=commission,
            slippage=slippage_amount,
        )
        state.trades.append(trade)

        logger.debug(f"Executed {side} {symbol}: {quantity} @ ¥{fill_price:.2f}")

    def _process_signal(
        self,
        state: BacktestState,
        signal: TradingSignal,
        current_prices: dict[str, float],
        current_date: datetime,
    ) -> None:
        """Process a trading signal"""
        if signal.signal_type == SignalType.HOLD:
            return

        if signal.symbol not in current_prices:
            logger.debug(f"No price available for {signal.symbol}")
            return

        current_price = current_prices[signal.symbol]

        # Handle exit signals
        if signal.is_exit:
            self._handle_exit(state, signal, current_price, current_date)
            return

        # Handle entry signals
        if signal.is_entry:
            self._handle_entry(state, signal, current_price, current_date)

    def _handle_entry(
        self,
        state: BacktestState,
        signal: TradingSignal,
        current_price: float,
        current_date: datetime,
    ) -> None:
        """Handle entry signal"""
        symbol = signal.symbol

        # Check if already positioned
        if symbol in state.positions:
            logger.debug(f"Already positioned in {symbol}")
            return

        # Calculate position size
        if signal.quantity:
            quantity = signal.quantity
        elif signal.position_size:
            equity = self._calculate_equity(state, {symbol: current_price})
            position_value = equity * signal.position_size
            quantity = int(position_value / current_price)
        else:
            # Default size
            quantity = int(state.cash * 0.02 / current_price)

        if quantity <= 0:
            return

        # Calculate costs
        notional = quantity * current_price
        commission = max(notional * self._commission_rate, self._min_commission)

        # Check if we have enough cash
        total_cost = notional + commission
        if total_cost > state.cash:
            # Reduce quantity
            quantity = int(
                (state.cash - self._min_commission) / (current_price * (1 + self._commission_rate))
            )
            if quantity <= 0:
                return
            notional = quantity * current_price
            commission = max(notional * self._commission_rate, self._min_commission)
            total_cost = notional + commission

        # Execute trade
        fill_price = current_price * (1 + self._slippage_rate)
        if signal.signal_type == SignalType.SELL:
            fill_price = current_price * (1 - self._slippage_rate)

        # Create trade
        trade = Trade(
            trade_id=f"{symbol}_{current_date.strftime('%Y%m%d_%H%M%S')}",
            order_id=f"ORD_{len(state.trades)}",
            symbol=symbol,
            side="BUY" if signal.signal_type == SignalType.BUY else "SELL",
            quantity=quantity,
            price=fill_price,
            timestamp=current_date,
            commission=commission,
            slippage=abs(fill_price - current_price) * quantity,
            source_signal=signal.source,
        )

        state.trades.append(trade)
        state.cash -= notional + commission

        # Create position
        position = Position(
            symbol=symbol,
            side="long" if signal.signal_type == SignalType.BUY else "short",
            quantity=quantity,
            entry_price=fill_price,
            entry_time=current_date,
            current_price=fill_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            source_signal=signal.source,
        )
        state.positions[symbol] = position

        logger.debug(f"Entered {signal.signal_type.value} {symbol}: {quantity} @ ¥{fill_price:.2f}")

    def _handle_exit(
        self,
        state: BacktestState,
        signal: TradingSignal,
        current_price: float,
        current_date: datetime,
    ) -> None:
        """Handle exit signal"""
        symbol = signal.symbol

        if symbol not in state.positions:
            return

        position = state.positions[symbol]

        # Calculate fill price
        if position.side == "long":
            fill_price = current_price * (1 - self._slippage_rate)
        else:
            fill_price = current_price * (1 + self._slippage_rate)

        # Calculate proceeds
        notional = position.quantity * fill_price
        commission = max(notional * self._commission_rate, self._min_commission)

        # Stamp duty (China A-shares, sell only)
        stamp_duty = 0.0
        if position.side == "long":
            stamp_duty = notional * self._stamp_duty

        # Calculate realized P&L
        if position.side == "long":
            realized_pnl = (fill_price - position.entry_price) * position.quantity
        else:
            realized_pnl = (position.entry_price - fill_price) * position.quantity

        realized_pnl -= commission + stamp_duty

        # Create trade
        trade = Trade(
            trade_id=f"{symbol}_{current_date.strftime('%Y%m%d_%H%M%S')}_EXIT",
            order_id=f"ORD_{len(state.trades)}",
            symbol=symbol,
            side="SELL" if position.side == "long" else "BUY",
            quantity=position.quantity,
            price=fill_price,
            timestamp=current_date,
            commission=commission + stamp_duty,
            slippage=abs(fill_price - current_price) * position.quantity,
            source_signal=signal.source,
        )

        state.trades.append(trade)
        state.cash += notional - commission - stamp_duty

        logger.debug(
            f"Exited {symbol}: {position.quantity} @ ¥{fill_price:.2f}, P&L: ¥{realized_pnl:.2f}"
        )

        # Remove position
        del state.positions[symbol]

    def _calculate_equity(
        self,
        state: BacktestState,
        current_prices: dict[str, float],
    ) -> float:
        """Calculate total equity"""
        equity = state.cash

        for symbol, position in state.positions.items():
            if symbol in current_prices:
                position.update_price(current_prices[symbol])
            equity += position.market_value

        return equity

    def _calculate_metrics(
        self,
        state: BacktestState,
        initial_capital: float,
        start: datetime,
        end: datetime,
    ) -> BacktestResult:
        """Calculate performance metrics"""
        result = BacktestResult()

        result.initial_capital = initial_capital
        result.trades = state.trades
        result.signals = state.signals
        result.equity_curve = state.equity_curve

        # Final equity
        if state.equity_curve:
            result.final_capital = state.equity_curve[-1]["equity"]
        else:
            result.final_capital = initial_capital

        # Total return
        result.total_return = (result.final_capital - initial_capital) / initial_capital

        # Annualized return
        days = (end - start).days
        years = max(days / 365.0, 1 / 252)  # At least one trading day
        result.annualized_return = (1 + result.total_return) ** (1 / years) - 1

        # Max drawdown
        result.max_drawdown = state.max_drawdown

        # Trade statistics
        if state.trades:
            result.total_trades = len(state.trades)

            # Calculate returns per trade
            trade_returns = []
            wins = 0
            total_profit = 0.0
            total_loss = 0.0

            # Match entry and exit trades
            position_entries = {}
            for trade in state.trades:
                if trade.symbol not in position_entries:
                    position_entries[trade.symbol] = []

                if trade.side == "BUY":
                    position_entries[trade.symbol].append(trade)
                else:
                    if position_entries[trade.symbol]:
                        entry_trade = position_entries[trade.symbol].pop(0)
                        pnl = (trade.price - entry_trade.price) * trade.quantity
                        pnl -= trade.commission + entry_trade.commission
                        trade_returns.append(pnl / (entry_trade.price * trade.quantity))

                        if pnl > 0:
                            wins += 1
                            total_profit += pnl
                        else:
                            total_loss += abs(pnl)

            if trade_returns:
                result.win_rate = wins / len(trade_returns)

            if total_loss > 0:
                result.profit_factor = total_profit / total_loss
            else:
                result.profit_factor = float("inf") if total_profit > 0 else 0

        # Sharpe ratio (using daily returns)
        if len(state.equity_curve) > 1:
            equity_values = [e["equity"] for e in state.equity_curve]
            daily_returns = [
                (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
                for i in range(1, len(equity_values))
            ]

            if daily_returns and np.std(daily_returns) > 0:
                # Annualize: sqrt(252) for daily returns
                result.sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)

        return result

    def _create_empty_result(self, initial_capital: float) -> BacktestResult:
        """Create empty backtest result"""
        result = BacktestResult()
        result.initial_capital = initial_capital
        result.final_capital = initial_capital
        return result

    def _save_results(self, result: BacktestResult, strategy_name: str) -> None:
        """Save backtest results to files"""
        if not self.config.save_trades and not self.config.save_equity_curve:
            return

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.config.save_equity_curve and result.equity_curve:
            equity_df = pd.DataFrame(result.equity_curve)
            equity_df.to_csv(
                output_dir / f"{strategy_name}_equity_{timestamp}.csv",
                index=False,
            )

        if self.config.save_trades and result.trades:
            trades_data = [
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "side": t.side,
                    "quantity": t.quantity,
                    "price": t.price,
                    "timestamp": t.timestamp.isoformat(),
                    "commission": t.commission,
                    "source_signal": t.source_signal,
                }
                for t in result.trades
            ]
            trades_df = pd.DataFrame(trades_data)
            trades_df.to_csv(
                output_dir / f"{strategy_name}_trades_{timestamp}.csv",
                index=False,
            )

        if self.config.save_signals and result.signals:
            signals_data = [s.to_dict() for s in result.signals]
            signals_df = pd.DataFrame(signals_data)
            signals_df.to_csv(
                output_dir / f"{strategy_name}_signals_{timestamp}.csv",
                index=False,
            )


def run_backtest(
    strategy: SignalGenerator,
    symbols: list[str],
    start: datetime,
    end: datetime,
    data_provider: DataProvider,
    initial_capital: float = 1000000.0,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """
    Convenience function to run a backtest.

    Args:
        strategy: Strategy to test
        symbols: List of symbols
        start: Start date
        end: End date
        data_provider: Data source
        initial_capital: Starting capital
        config: Backtest configuration

    Returns:
        BacktestResult
    """
    engine = BacktestEngineImpl(data_provider, config)
    return engine.run(strategy, symbols, start, end, initial_capital)
