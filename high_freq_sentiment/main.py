"""
Vectorized Sentiment Arbitrage System - Main Integration Module
===============================================================

Main module that integrates all components of the sentiment arbitrage system:
- Kalman filters for state estimation
- Vectorized z-scoring across 500+ stocks
- Sentiment extraction with Distil-FinBERT
- Echo chamber elimination through orthogonalization
- Signal generation with entry/exit conditions
- Comprehensive testing framework

This is the entry point for running the complete system.

Author: Algorithm Designer (Subagent)
Date: 2026-03-09
"""

import json
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import cupy as cp
import numpy as np

warnings.filterwarnings("ignore")

# Import all components
from src.echo_chamber import (
    EchoChamberEliminator,
    OrthogonalizationConfig,
)
from src.kalman_filter import SquareRootKalmanFilter, VectorizedKalmanFilterBank
from src.sentiment_extraction import (
    create_mock_sentiment_layer,
)
from src.signal_generation import (
    SignalConfig,
    SignalEvaluator,
    SignalGenerator,
)
from src.z_scoring import (
    ExponentialZScorer,
    RollingZScorer,
    VectorizedZScoreLayer,
    ZScoreConfig,
)


@dataclass
class SystemConfig:
    """Configuration for the entire system"""

    # Universe
    n_stocks: int = 500

    # Kalman Filter
    kalman_process_noise: float = 1e-5
    kalman_measurement_noise: float = 1e-3
    use_kalman_ensemble: bool = False
    n_kalman_filters: int = 5

    # Z-Score
    z_score_lookback: int = 20
    z_score_method: str = "rolling"  # 'rolling', 'exponential', or 'layer'
    z_score_decay: float = 0.94
    use_cross_sectional: bool = True

    # Echo Chamber Elimination
    orthogonalization_method: str = "projection"  # 'projection', 'pca', 'combined'
    n_factors: int = 3

    # Signal Generation
    long_sentiment_threshold: float = 1.5
    long_price_threshold: float = -0.5
    long_dislocation_threshold: float = 2.0
    short_sentiment_threshold: float = -1.5
    short_price_threshold: float = 0.5
    short_dislocation_threshold: float = -2.0
    exit_z_cross: bool = True
    exit_time_stop_hours: int = 48
    exit_stop_loss_pct: float = 0.15

    # Risk Management
    max_position_size: float = 0.05
    max_portfolio_exposure: float = 1.0

    # Sentiment Extraction
    use_triton: bool = False  # Set to True for production with Triton
    triton_url: str = "localhost:8001"


class SentimentArbitrageSystem:
    """
    Main sentiment arbitrage system.

    Integrates all components for end-to-end signal generation.
    """

    def __init__(self, config: SystemConfig | None = None):
        """
        Initialize the system

        Args:
            config: System configuration
        """
        self.config = config or SystemConfig()

        # Initialize components
        print("Initializing Vectorized Sentiment Arbitrage System...")
        print(f"  Universe size: {self.config.n_stocks} stocks")

        # Kalman Filter
        if self.config.use_kalman_ensemble:
            self.kalman = VectorizedKalmanFilterBank(
                n_stocks=self.config.n_stocks, n_filters=self.config.n_kalman_filters
            )
        else:
            self.kalman = SquareRootKalmanFilter(
                n_stocks=self.config.n_stocks,
                process_noise=self.config.kalman_process_noise,
                measurement_noise=self.config.kalman_measurement_noise,
            )

        # Z-Score Layer
        if self.config.z_score_method == "layer":
            z_config = ZScoreConfig(
                lookback=self.config.z_score_lookback,
                decay=self.config.z_score_decay,
                winsorize=True,
            )
            methods = ["rolling"]
            if self.config.use_cross_sectional:
                methods.append("cross_sectional")

            self.z_scorer = VectorizedZScoreLayer(
                n_stocks=self.config.n_stocks, methods=methods, configs=[z_config, z_config]
            )
        elif self.config.z_score_method == "exponential":
            z_config = ZScoreConfig(
                method="exponential", decay=self.config.z_score_decay, winsorize=True
            )
            self.z_scorer = ExponentialZScorer(n_stocks=self.config.n_stocks, config=z_config)
        else:  # rolling
            z_config = ZScoreConfig(
                method="rolling", lookback=self.config.z_score_lookback, winsorize=True
            )
            self.z_scorer = RollingZScorer(n_stocks=self.config.n_stocks, config=z_config)

        # Echo Chamber Eliminator
        echo_config = OrthogonalizationConfig(
            method=self.config.orthogonalization_method, n_factors=self.config.n_factors
        )
        self.eliminator = EchoChamberEliminator(
            n_stocks=self.config.n_stocks,
            methods=[self.config.orthogonalization_method],
            config=echo_config,
        )

        # Signal Generator
        signal_config = SignalConfig(
            long_sentiment_threshold=self.config.long_sentiment_threshold,
            long_price_threshold=self.config.long_price_threshold,
            long_dislocation_threshold=self.config.long_dislocation_threshold,
            short_sentiment_threshold=self.config.short_sentiment_threshold,
            short_price_threshold=self.config.short_price_threshold,
            short_dislocation_threshold=self.config.short_dislocation_threshold,
            exit_z_cross=self.config.exit_z_cross,
            exit_time_stop_hours=self.config.exit_time_stop_hours,
            exit_stop_loss_pct=self.config.exit_stop_loss_pct,
            max_position_size=self.config.max_position_size,
            max_portfolio_exposure=self.config.max_portfolio_exposure,
        )
        self.signal_generator = SignalGenerator(n_stocks=self.config.n_stocks, config=signal_config)

        # Sentiment Extraction Layer
        if self.config.use_triton:
            # Production mode with Triton
            # Note: Requires Triton server to be running
            print("  Warning: Triton mode enabled but not yet connected")
            self.sentiment_layer = None  # Would create Triton client here
        else:
            # Mock mode for testing
            self.sentiment_layer = create_mock_sentiment_layer(n_stocks=self.config.n_stocks)

        # Performance tracking
        self.n_updates = 0
        self.total_signals = 0
        self.execution_times = []

        print("  ✓ System initialized successfully")

    def update(
        self,
        stock_prices: np.ndarray,
        sentiment_texts: list[str] | None = None,
        market_sentiment: float | None = None,
        sector_sentiments: np.ndarray | None = None,
        timestamp: int = 0,
    ) -> dict:
        """
        Update system with new market data and generate signals

        Args:
            stock_prices: Current stock prices (n_stocks,)
            sentiment_texts: Optional text data for sentiment extraction
            market_sentiment: Market-wide sentiment score
            sector_sentiments: Sector sentiment scores (n_sectors,)
            timestamp: Current timestamp

        Returns:
            Dictionary with signals and system state
        """
        start_time = time.time()

        # Validate input
        stock_prices = np.asarray(stock_prices)
        assert stock_prices.shape[0] == self.config.n_stocks, "Price dimension mismatch"

        # Step 1: Extract sentiment (from texts or use provided scores)
        if sentiment_texts is not None and self.sentiment_layer is not None:
            # Extract sentiment from text
            sentiment_output = self.sentiment_layer.extract_sentiment_batch(
                sentiment_texts, return_confidence=True
            )
            sentiment_scores = sentiment_output.sentiment_scores
            confidence_scores = sentiment_output.confidence_scores
        else:
            # Use provided sentiment scores or generate mock scores
            if market_sentiment is None:
                # Generate mock sentiment if not provided
                sentiment_scores = np.random.randn(self.config.n_stocks) * 0.5
            else:
                sentiment_scores = np.full(self.config.n_stocks, market_sentiment)
                sentiment_scores += np.random.randn(self.config.n_stocks) * 0.3

            confidence_scores = np.ones(self.config.n_stocks) * 0.8

        # Convert to GPU
        stock_prices_gpu = cp.array(stock_prices)
        sentiment_scores_gpu = cp.array(sentiment_scores)
        confidence_scores_gpu = cp.array(confidence_scores)

        # Step 2: Update Kalman filter (estimate beta)
        if self.config.use_kalman_ensemble:
            beta = self.kalman.update_ensemble(sentiment_scores_gpu)
        else:
            beta_pred, P_pred_sqrt = self.kalman.predict_step()
            beta = self.kalman.update_step(sentiment_scores_gpu, P_pred_sqrt)

        # Step 3: Calculate z-scores
        if isinstance(self.z_scorer, VectorizedZScoreLayer):
            z_dict = self.z_scorer.update(sentiment_scores_gpu)
            z_sentiment = self.z_scorer.get_combined_z_score(z_dict)
        elif isinstance(self.z_scorer, ExponentialZScorer):
            z_sentiment = self.z_scorer.update(sentiment_scores_gpu)
        else:  # RollingZScorer
            z_sentiment = self.z_scorer.update(sentiment_scores_gpu)

        # Calculate price z-scores (simple rolling)
        price_changes = cp.diff(stock_prices_gpu)
        if price_changes.shape[0] < self.config.z_score_lookback:
            z_price = cp.zeros(self.config.n_stocks)
        else:
            # Use recent price changes for z-score
            recent_changes = price_changes[-self.config.z_score_lookback :]
            z_price = (recent_changes[-1] - cp.mean(recent_changes)) / cp.std(recent_changes)
            z_price = cp.tile(z_price, self.config.n_stocks)  # Broadcast to all stocks

        # Step 4: Calculate dislocation
        dislocation = z_sentiment - z_price

        # Step 5: Remove echo chamber effects
        idio_sentiment = self.eliminator.eliminate_echo_chamber(
            sentiment_scores_gpu,
            market_sentiment=market_sentiment or float(cp.mean(sentiment_scores_gpu)),
            sector_sentiments=cp.array(sector_sentiments)
            if sector_sentiments is not None
            else None,
        )

        # Recalculate dislocation with idiosyncratic sentiment
        z_idio_sentiment = (idio_sentiment - cp.mean(idio_sentiment)) / cp.std(idio_sentiment)
        dislocation = z_idio_sentiment - z_price

        # Step 6: Generate trading signals
        signals, stocks_to_close = self.signal_generator.generate_signals(
            z_idio_sentiment,
            z_price,
            dislocation,
            stock_prices_gpu,
            confidence_scores_gpu,
            timestamp,
        )

        # Step 7: Check exit conditions for existing positions
        if stocks_to_close:
            for stock_id in stocks_to_close:
                self.signal_generator.close_position(stock_id, float(stock_prices[stock_id]))

        # Track performance
        execution_time = time.time() - start_time
        self.execution_times.append(execution_time)
        self.n_updates += 1
        self.total_signals += len(signals)

        # Prepare results
        results = {
            "timestamp": timestamp,
            "n_signals": len(signals),
            "n_stocks_to_close": len(stocks_to_close),
            "signals": signals,
            "execution_time": execution_time,
            "avg_dislocation": float(cp.mean(cp.abs(dislocation))),
            "avg_sentiment": float(cp.mean(z_idio_sentiment)),
            "portfolio_exposure": self.signal_generator.get_portfolio_exposure(),
            "kalman_beta": beta.get() if isinstance(beta, cp.ndarray) else beta,
            "n_active_positions": len(self.signal_generator.active_positions),
        }

        return results

    def run_backtest(
        self,
        price_data: np.ndarray,
        sentiment_data: np.ndarray | None = None,
        initial_portfolio_value: float = 1000000.0,
    ) -> dict:
        """
        Run backtest on historical data

        Args:
            price_data: Historical price data (n_timesteps, n_stocks)
            sentiment_data: Historical sentiment data (n_timesteps, n_stocks)
            initial_portfolio_value: Starting portfolio value

        Returns:
            Backtest results
        """
        print(f"\nRunning backtest on {price_data.shape[0]} timesteps...")

        n_timesteps = price_data.shape[0]
        portfolio_value = initial_portfolio_value
        portfolio_values = [portfolio_value]
        signal_evaluator = SignalEvaluator()

        all_results = []

        for t in range(n_timesteps):
            if t < self.config.z_score_lookback:
                continue

            # Extract sentiment
            if sentiment_data is not None:
                sentiment_scores = sentiment_data[t, :]
            else:
                # Generate mock sentiment correlated with price
                price_changes = np.diff(price_data[: t + 1, :], axis=0)
                if price_changes.shape[0] > 0:
                    sentiment_scores = (
                        price_changes[-1, :] * 0.5 + np.random.randn(self.config.n_stocks) * 0.3
                    )
                else:
                    sentiment_scores = np.random.randn(self.config.n_stocks) * 0.5

            # Update system
            results = self.update(
                stock_prices=price_data[t, :],
                sentiment_texts=None,
                market_sentiment=float(np.mean(sentiment_scores)),
                timestamp=t,
            )

            # Execute signals
            for signal in results["signals"]:
                quantity, cost = self.signal_generator.execute_signal(signal, portfolio_value)
                portfolio_value -= cost

            # Close positions
            for stock_id in (
                results["n_stocks_to_close"]
                if isinstance(results["n_stocks_to_close"], list)
                else []
            ):
                pnl, value = self.signal_generator.close_position(
                    stock_id, float(price_data[t, stock_id])
                )
                portfolio_value += value

            portfolio_values.append(portfolio_value)
            all_results.append(results)

        # Calculate returns
        returns = np.diff(portfolio_values) / portfolio_values[:-1]

        backtest_results = {
            "final_portfolio_value": portfolio_value,
            "total_return": (portfolio_value - initial_portfolio_value) / initial_portfolio_value,
            "annualized_return": (
                (portfolio_value / initial_portfolio_value) ** (252 / n_timesteps) - 1
            )
            if n_timesteps > 0
            else 0,
            "sharpe_ratio": float(np.mean(returns) / np.std(returns) * np.sqrt(252))
            if np.std(returns) > 0
            else 0,
            "max_drawdown": float(np.min(np.diff(portfolio_values) / portfolio_values[:-1])),
            "total_signals": sum(r["n_signals"] for r in all_results),
            "avg_execution_time": np.mean(self.execution_times),
            "portfolio_values": portfolio_values,
            "all_results": all_results,
        }

        print(f"  Final Portfolio Value: ${portfolio_value:,.2f}")
        print(f"  Total Return: {backtest_results['total_return']:.2%}")
        print(f"  Sharpe Ratio: {backtest_results['sharpe_ratio']:.3f}")
        print(f"  Max Drawdown: {backtest_results['max_drawdown']:.2%}")
        print(f"  Total Signals: {backtest_results['total_signals']}")
        print(f"  Avg Execution Time: {backtest_results['avg_execution_time'] * 1000:.2f}ms")

        return backtest_results

    def get_system_status(self) -> dict:
        """Get current system status"""
        return {
            "n_stocks": self.config.n_stocks,
            "n_updates": self.n_updates,
            "total_signals": self.total_signals,
            "avg_execution_time": np.mean(self.execution_times) if self.execution_times else 0,
            "active_positions": len(self.signal_generator.active_positions),
            "portfolio_exposure": self.signal_generator.get_portfolio_exposure(),
        }


def generate_synthetic_data(
    n_stocks: int = 500, n_timesteps: int = 200, trend: float = 0.001, volatility: float = 0.02
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic price and sentiment data for testing

    Args:
        n_stocks: Number of stocks
        n_timesteps: Number of timesteps
        trend: Price trend per timestep
        volatility: Price volatility

    Returns:
        Tuple of (price_data, sentiment_data)
    """
    np.random.seed(42)

    # Generate price data with trend
    price_changes = np.random.randn(n_timesteps, n_stocks) * volatility + trend
    price_data = np.cumprod(1 + price_changes, axis=0) * 100

    # Generate sentiment data correlated with prices
    sentiment_changes = np.random.randn(n_timesteps, n_stocks) * 0.3
    sentiment_changes += 0.3 * np.random.randn(n_timesteps, 1)  # Add market component
    sentiment_data = np.cumsum(sentiment_changes, axis=0)

    # Add some mispricings for arbitrage opportunities
    for i in range(10):
        stock_id = np.random.randint(0, n_stocks)
        start_t = np.random.randint(20, n_timesteps - 20)
        sentiment_data[start_t : start_t + 10, stock_id] += 2.0  # High sentiment
        price_data[start_t : start_t + 10, stock_id] *= 0.95  # Low price

    return price_data, sentiment_data


def main():
    """Main function to demonstrate the system"""
    print("=" * 80)
    print("Vectorized Sentiment Arbitrage System - Demonstration")
    print("=" * 80)

    # Create system configuration
    config = SystemConfig(
        n_stocks=100,  # Smaller universe for demo
        kalman_process_noise=1e-5,
        kalman_measurement_noise=1e-3,
        z_score_lookback=20,
        z_score_method="rolling",
        orthogonalization_method="projection",
        long_sentiment_threshold=1.2,
        short_sentiment_threshold=-1.2,
        use_triton=False,  # Use mock sentiment for demo
    )

    # Initialize system
    system = SentimentArbitrageSystem(config)

    # Generate synthetic data
    print("\nGenerating synthetic market data...")
    price_data, sentiment_data = generate_synthetic_data(n_stocks=config.n_stocks, n_timesteps=100)

    # Run backtest
    print("\nRunning backtest...")
    results = system.run_backtest(
        price_data=price_data, sentiment_data=sentiment_data, initial_portfolio_value=1000000.0
    )

    # Print system status
    print("\nFinal System Status:")
    status = system.get_system_status()
    for key, value in status.items():
        if key != "portfolio_exposure":
            print(f"  {key}: {value}")

    print("\nPortfolio Exposure:")
    exposure = status["portfolio_exposure"]
    for key, value in exposure.items():
        print(f"  {key}: {value}")

    # Save results
    output_dir = Path("/home/zireael/.openclaw/workspace/sentiment_arbitrage/data")
    output_dir.mkdir(exist_ok=True)

    results_file = output_dir / "backtest_results.json"
    with open(results_file, "w") as f:
        # Convert non-serializable objects
        serializable_results = {
            k: v for k, v in results.items() if k not in ["portfolio_values", "all_results"]
        }
        serializable_results["n_timesteps"] = len(results["portfolio_values"])
        json.dump(serializable_results, f, indent=2)

    print(f"\nResults saved to: {results_file}")
    print("\n" + "=" * 80)
    print("Demonstration Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
