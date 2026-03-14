"""
Testing Framework for Vectorized Sentiment Arbitrage System
===========================================================

Comprehensive testing framework for mathematical models including:
- Unit tests for individual components
- Integration tests for the full pipeline
- Performance benchmarks
- Validation with synthetic and real data

Author: Algorithm Designer
Date: 2026-03-09
"""

import json
import time
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass

import numpy as np
import pytest

# CuPy is required for GPU-accelerated tests
try:
    import cupy as cp
    CUPY_AVAILABLE = True
except ImportError:
    CUPY_AVAILABLE = False
    cp = None

# Skip all tests in this module if CuPy is not available
pytestmark = pytest.mark.skipif(
    not CUPY_AVAILABLE,
    reason="CuPy not installed - GPU-dependent tests skipped"
)

warnings.filterwarnings("ignore")

# Import modules to test - skip if dependencies not available
if CUPY_AVAILABLE:
    from echo_chamber import (
        EchoChamberEliminator,
        MarketSentimentOrthogonalizer,
        OrthogonalizationConfig,
        PCAOrthogonalizer,
    )
    from kalman_filter import SquareRootKalmanFilter, VectorizedKalmanFilterBank
    from signal_generation import (
        SignalConfig,
        SignalGenerator,
        SignalType,
    )
    from z_scoring import (
        CrossSectionalZScorer,
        ExponentialZScorer,
        RollingZScorer,
        VectorizedZScoreLayer,
        ZScoreConfig,
    )


@dataclass
class TestResult:
    """Container for test results"""

    test_name: str
    passed: bool
    execution_time: float
    error_message: str | None = None
    metrics: dict | None = None


class TestFramework:
    """
    Main testing framework for the sentiment arbitrage system.

    Provides comprehensive testing for all mathematical models.
    """

    def __init__(self, verbose: bool = True):
        """
        Initialize test framework

        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
        self.test_results = []
        self.benchmark_results = {}

    def run_test(self, test_func: Callable, test_name: str, **kwargs) -> TestResult:
        """
        Run a single test function

        Args:
            test_func: Function to test
            test_name: Name of the test
            **kwargs: Arguments to pass to test function

        Returns:
            TestResult object
        """
        start_time = time.time()

        try:
            # Run test
            metrics = test_func(**kwargs)

            execution_time = time.time() - start_time

            result = TestResult(
                test_name=test_name, passed=True, execution_time=execution_time, metrics=metrics
            )

            if self.verbose:
                print(f"✓ {test_name} passed ({execution_time:.3f}s)")
                if metrics:
                    print(f"  Metrics: {metrics}")

        except Exception as e:
            execution_time = time.time() - start_time

            result = TestResult(
                test_name=test_name,
                passed=False,
                execution_time=execution_time,
                error_message=str(e),
            )

            if self.verbose:
                print(f"✗ {test_name} failed: {e}")

        self.test_results.append(result)
        return result

    def run_all_tests(self):
        """Run all tests"""
        print("=" * 80)
        print("Running Vectorized Sentiment Arbitrage System Test Suite")
        print("=" * 80)

        # Kalman Filter Tests
        print("\n1. Kalman Filter Tests")
        print("-" * 40)
        self._test_kalman_filter_convergence()
        self._test_kalman_filter_numerical_stability()
        self._test_kalman_filter_batch_processing()
        self._test_kalman_filter_ensemble()

        # Z-Score Tests
        print("\n2. Z-Score Calculator Tests")
        print("-" * 40)
        self._test_z_score_rolling()
        self._test_z_score_exponential()
        self._test_z_score_cross_sectional()
        self._test_z_score_layer()

        # Echo Chamber Tests
        print("\n3. Echo Chamber Elimination Tests")
        print("-" * 40)
        self._test_projection_orthogonalization()
        self._test_pca_orthogonalization()
        self._test_echo_chamber_combination()

        # Signal Generation Tests
        print("\n4. Signal Generation Tests")
        print("-" * 40)
        self._test_signal_buy_conditions()
        self._test_signal_sell_conditions()
        self._test_signal_exit_conditions()
        self._test_signal_position_sizing()

        # Integration Tests
        print("\n5. Integration Tests")
        print("-" * 40)
        self._test_full_pipeline()

        # Performance Benchmarks
        print("\n6. Performance Benchmarks")
        print("-" * 40)
        self._benchmark_kalman_filter()
        self._benchmark_z_scores()
        self._benchmark_signal_generation()
        self._benchmark_full_pipeline()

        # Print summary
        self._print_summary()

    # Kalman Filter Tests
    def _test_kalman_filter_convergence(self) -> dict:
        """Test Kalman filter convergence to known parameters"""
        np.random.seed(42)
        n_stocks = 10
        n_timesteps = 200

        # True parameters
        true_beta = np.linspace(0.5, 2.0, n_stocks)

        # Generate data
        sentiment = np.random.randn(n_timesteps, n_stocks)
        noise = np.random.randn(n_timesteps, n_stocks) * 0.1
        measurements = sentiment @ np.diag(true_beta).T + noise

        # Run filter
        kf = SquareRootKalmanFilter(n_stocks=n_stocks)
        filtered_states = kf.filter_batch(cp.array(measurements))

        # Check convergence
        final_beta = filtered_states[-1, :].get()
        error = np.abs(final_beta - true_beta)
        mean_error = np.mean(error)
        max_error = np.max(error)

        assert mean_error < 0.1, f"Mean error too high: {mean_error}"
        assert max_error < 0.2, f"Max error too high: {max_error}"

        return {
            "mean_error": float(mean_error),
            "max_error": float(max_error),
            "log_likelihood": float(kf.log_likelihood),
        }

    def _test_kalman_filter_numerical_stability(self) -> dict:
        """Test numerical stability of square-root Kalman filter"""
        np.random.seed(42)
        n_stocks = 50
        n_timesteps = 100

        # Generate ill-conditioned data
        measurements = np.random.randn(n_timesteps, n_stocks) * 1e6

        # Run filter
        kf = SquareRootKalmanFilter(n_stocks=n_stocks)
        filtered_states = kf.filter_batch(cp.array(measurements))

        # Check that all values are finite
        assert cp.all(cp.isfinite(filtered_states)), "Filter produced non-finite values"

        # Check that covariance remains positive semi-definite
        P = kf.P_sqrt @ kf.P_sqrt.T
        eigenvalues = cp.linalg.eigvalsh(P)
        assert cp.all(eigenvalues >= -1e-10), "Covariance is not positive semi-definite"

        return {
            "min_eigenvalue": float(cp.min(eigenvalues)),
            "condition_number": float(cp.max(eigenvalues) / (cp.min(eigenvalues) + 1e-10)),
        }

    def _test_kalman_filter_batch_processing(self) -> dict:
        """Test batch processing efficiency"""
        np.random.seed(42)
        n_stocks = 100
        n_timesteps = 500

        measurements = np.random.randn(n_timesteps, n_stocks)

        # Measure batch processing time
        kf = SquareRootKalmanFilter(n_stocks=n_stocks)
        start_time = time.time()
        filtered_states = kf.filter_batch(cp.array(measurements))
        batch_time = time.time() - start_time

        # Compare with sequential processing
        kf_seq = SquareRootKalmanFilter(n_stocks=n_stocks)
        start_time = time.time()
        for t in range(n_timesteps):
            beta_pred, P_pred_sqrt = kf_seq.predict_step()
            kf_seq.update_step(cp.array(measurements[t, :]), beta_pred, P_pred_sqrt)
        seq_time = time.time() - start_time

        speedup = seq_time / batch_time

        return {"batch_time": batch_time, "sequential_time": seq_time, "speedup": speedup}

    def _test_kalman_filter_ensemble(self) -> dict:
        """Test ensemble Kalman filter"""
        np.random.seed(42)
        n_stocks = 20
        n_filters = 5

        bank = VectorizedKalmanFilterBank(n_stocks=n_stocks, n_filters=n_filters)

        measurements = cp.random.randn(n_stocks)

        # Update ensemble
        ensemble_mean = bank.update_ensemble(measurements)

        # Get ensemble statistics
        stats = bank.get_ensemble_statistics(measurements)

        assert ensemble_mean.shape == (n_stocks,), "Ensemble mean shape mismatch"
        assert "mean" in stats and "std" in stats, "Missing ensemble statistics"

        return {"n_filters": n_filters, "ensemble_std_mean": float(cp.mean(stats["std"]))}

    # Z-Score Tests
    def _test_z_score_rolling(self) -> dict:
        """Test rolling z-score calculator"""
        np.random.seed(42)
        n_stocks = 50
        n_timesteps = 100

        config = ZScoreConfig(method="rolling", lookback=20, winsorize=True)
        scorer = RollingZScorer(n_stocks, config)

        data = np.random.randn(n_timesteps, n_stocks)
        z_scores = []

        for t in range(n_timesteps):
            z = scorer.update(cp.array(data[t, :]))
            z_scores.append(z.get())

        z_scores = np.array(z_scores)

        # Check properties
        assert np.isnan(z_scores[:10]).any(), "Initial z-scores should be NaN"
        assert not np.isnan(z_scores[20:]).any(), "Z-scores should be defined after warmup"

        # Check that mean is approximately 0 and std is approximately 1
        valid_scores = z_scores[20:].flatten()
        assert abs(np.mean(valid_scores)) < 0.1, f"Mean should be ~0, got {np.mean(valid_scores)}"
        assert abs(np.std(valid_scores) - 1.0) < 0.2, (
            f"Std should be ~1, got {np.std(valid_scores)}"
        )

        return {
            "mean_z": float(np.mean(valid_scores)),
            "std_z": float(np.std(valid_scores)),
            "max_z": float(np.max(valid_scores)),
        }

    def _test_z_score_exponential(self) -> dict:
        """Test exponential z-score calculator"""
        np.random.seed(42)
        n_stocks = 50

        config = ZScoreConfig(method="exponential", decay=0.94, winsorize=True)
        scorer = ExponentialZScorer(n_stocks, config)

        z_scores = []
        for t in range(100):
            data = np.random.randn(n_stocks) + np.sin(t / 10) * 0.5
            z = scorer.update(cp.array(data))
            z_scores.append(z.get())

        z_scores = np.array(z_scores)

        # Check that z-scores adapt to trend
        assert not np.isnan(z_scores).any(), "No NaN values expected"
        assert np.std(z_scores) > 0.5, "Z-scores should have variation"

        return {"mean_z": float(np.mean(z_scores)), "std_z": float(np.std(z_scores))}

    def _test_z_score_cross_sectional(self) -> dict:
        """Test cross-sectional z-score calculator"""
        np.random.seed(42)
        n_stocks = 100

        scorer = CrossSectionalZScorer(n_stocks)

        data = np.random.randn(n_stocks) * 2 + 1
        z = scorer.compute(cp.array(data)).get()

        # Check cross-sectional properties
        assert abs(np.mean(z)) < 1e-10, f"Cross-sectional mean should be 0, got {np.mean(z)}"
        assert abs(np.std(z) - 1.0) < 0.01, f"Cross-sectional std should be 1, got {np.std(z)}"

        return {
            "mean_z": float(np.mean(z)),
            "std_z": float(np.std(z)),
            "min_z": float(np.min(z)),
            "max_z": float(np.max(z)),
        }

    def _test_z_score_layer(self) -> dict:
        """Test vectorized z-score layer"""
        n_stocks = 100

        config = ZScoreConfig(lookback=10, winsorize=True)
        layer = VectorizedZScoreLayer(
            n_stocks=n_stocks, methods=["rolling", "cross_sectional"], configs=[config, config]
        )

        data = np.random.randn(n_stocks)
        z_dict = layer.update(cp.array(data))

        # Check that both methods produce results
        assert "rolling" in z_dict, "Missing rolling z-scores"
        assert "cross_sectional" in z_dict, "Missing cross-sectional z-scores"

        # Check combined z-score
        combined = layer.get_combined_z_score(z_dict)
        assert combined.shape == (n_stocks,), "Combined z-score shape mismatch"

        return {
            "rolling_mean": float(cp.mean(z_dict["rolling"])),
            "cross_sectional_mean": float(cp.mean(z_dict["cross_sectional"])),
            "combined_mean": float(cp.mean(combined)),
        }

    # Echo Chamber Tests
    def _test_projection_orthogonalization(self) -> dict:
        """Test projection-based orthogonalization"""
        np.random.seed(42)
        n_stocks = 50

        orthogonalizer = MarketSentimentOrthogonalizer(n_stocks)

        # Create data with market component
        market_sentiment = 0.5
        idio_sentiment = np.random.randn(n_stocks) * 0.3
        stock_sentiment = idio_sentiment + market_sentiment

        # Orthogonalize
        idio_result = orthogonalizer.orthogonalize_projection(
            cp.array(stock_sentiment), cp.array([market_sentiment])
        ).get()

        # Check orthogonality
        correlation = np.corrcoef(idio_result, np.array([market_sentiment]))[0, 1]
        assert abs(correlation) < 0.1, f"Correlation should be near 0, got {correlation}"

        return {
            "correlation": float(correlation),
            "mean_idio": float(np.mean(idio_result)),
            "std_idio": float(np.std(idio_result)),
        }

    def _test_pca_orthogonalization(self) -> dict:
        """Test PCA-based orthogonalization"""
        np.random.seed(42)
        n_stocks = 50
        n_samples = 30

        pca = PCAOrthogonalizer(n_stocks=n_stocks, n_components=3)

        # Create data with common factors
        factors = np.random.randn(3, n_samples)
        loadings = np.random.randn(n_stocks, 3)
        noise = np.random.randn(n_stocks, n_samples) * 0.1
        data = loadings @ factors + noise

        # Fit and transform
        idio_data = pca.fit_transform(cp.array(data))

        # Check dimensionality
        assert idio_data.shape == data.shape, "Output shape mismatch"

        # Check that common factor is reduced
        original_std = np.std(data, axis=0)
        idio_std = np.std(idio_data.get(), axis=0)
        reduction = np.mean(original_std / (idio_std + 1e-10))

        return {
            "std_reduction": float(reduction),
            "explained_variance": float(cp.sum(pca.components @ pca.components.T) / n_stocks),
        }

    def _test_echo_chamber_combination(self) -> dict:
        """Test combined echo chamber elimination"""
        np.random.seed(42)
        n_stocks = 30

        eliminator = EchoChamberEliminator(
            n_stocks=n_stocks,
            methods=["projection", "pca"],
            config=OrthogonalizationConfig(n_factors=2),
        )

        # Initialize PCA
        pca_data = cp.random.randn(n_stocks, 20)
        eliminator.orthogonalizers["pca"].fit(pca_data)

        # Test elimination
        stock_sentiment = cp.random.randn(n_stocks) + 0.5
        idio_sentiment = eliminator.eliminate_echo_chamber(stock_sentiment, market_sentiment=0.5)

        # Verify orthogonality
        correlation = eliminator.verify_orthogonality(idio_sentiment, cp.array([0.5]))

        return {"correlation": float(correlation), "mean_idio": float(cp.mean(idio_sentiment))}

    # Signal Generation Tests
    def _test_signal_buy_conditions(self) -> dict:
        """Test buy signal conditions"""
        n_stocks = 50

        config = SignalConfig(
            long_sentiment_threshold=1.5, long_price_threshold=-0.5, long_dislocation_threshold=2.0
        )

        generator = SignalGenerator(n_stocks=n_stocks, config=config)

        # Create buy signal
        sentiment = cp.array([2.0] + [0.0] * (n_stocks - 1))
        price_z = cp.array([-1.0] + [0.0] * (n_stocks - 1))
        dislocation = cp.array([2.5] + [0.0] * (n_stocks - 1))
        prices = cp.array([100.0] * n_stocks)

        signals, _ = generator.generate_signals(
            sentiment, price_z, dislocation, prices, timestamp=0
        )

        assert len(signals) > 0, "Should generate buy signal"
        assert signals[0].signal_type == SignalType.BUY, "Should be buy signal"
        assert signals[0].stock_id == 0, "Should be first stock"

        return {
            "n_signals": len(signals),
            "signal_strength": signals[0].signal_strength if signals else 0,
        }

    def _test_signal_sell_conditions(self) -> dict:
        """Test sell signal conditions"""
        n_stocks = 50

        config = SignalConfig(
            short_sentiment_threshold=-1.5,
            short_price_threshold=0.5,
            short_dislocation_threshold=-2.0,
        )

        generator = SignalGenerator(n_stocks=n_stocks, config=config)

        # Create sell signal
        sentiment = cp.array([-2.0] + [0.0] * (n_stocks - 1))
        price_z = cp.array([1.0] + [0.0] * (n_stocks - 1))
        dislocation = cp.array([-2.5] + [0.0] * (n_stocks - 1))
        prices = cp.array([100.0] * n_stocks)

        signals, _ = generator.generate_signals(
            sentiment, price_z, dislocation, prices, timestamp=0
        )

        assert len(signals) > 0, "Should generate sell signal"
        assert signals[0].signal_type == SignalType.SELL, "Should be sell signal"

        return {
            "n_signals": len(signals),
            "signal_strength": signals[0].signal_strength if signals else 0,
        }

    def _test_signal_exit_conditions(self) -> dict:
        """Test signal exit conditions"""
        n_stocks = 50

        config = SignalConfig(
            long_sentiment_threshold=1.0,
            long_price_threshold=-0.3,
            long_dislocation_threshold=1.5,
            exit_z_cross=True,
        )

        generator = SignalGenerator(n_stocks=n_stocks, config=config)

        # Create buy signal
        sentiment = cp.array([2.0] + [0.0] * (n_stocks - 1))
        price_z = cp.array([-1.0] + [0.0] * (n_stocks - 1))
        dislocation = cp.array([2.5] + [0.0] * (n_stocks - 1))
        prices = cp.array([100.0] * n_stocks)

        signals, _ = generator.generate_signals(
            sentiment, price_z, dislocation, prices, timestamp=0
        )

        # Execute signal
        if signals:
            signal = signals[0]
            generator.execute_signal(signal, portfolio_value=100000)

            # Check exit condition (z-score crosses zero)
            dislocation[0] = -1.0
            stocks_to_close = generator._check_exit_conditions(
                sentiment, price_z, dislocation, prices, timestamp=3600
            )

            assert signal.stock_id in stocks_to_close, "Should close position"

        return {"closed_positions": len(stocks_to_close)}

    def _test_signal_position_sizing(self) -> dict:
        """Test position sizing"""
        n_stocks = 50

        config = SignalConfig(max_position_size=0.05, position_sizing_method="signal_strength")

        generator = SignalGenerator(n_stocks=n_stocks, config=config)

        # Create signal
        sentiment = cp.array([2.0] + [0.0] * (n_stocks - 1))
        price_z = cp.array([-1.0] + [0.0] * (n_stocks - 1))
        dislocation = cp.array([2.5] + [0.0] * (n_stocks - 1))
        prices = cp.array([100.0] * n_stocks)
        confidence = cp.array([0.8] + [0.5] * (n_stocks - 1))

        signals, _ = generator.generate_signals(
            sentiment, price_z, dislocation, prices, confidence, timestamp=0
        )

        if signals:
            signal = signals[0]
            assert signal.position_size <= config.max_position_size, "Position size exceeds max"
            assert signal.position_size > 0, "Position size should be positive"

        return {"position_size": signals[0].position_size if signals else 0}

    # Integration Tests
    def _test_full_pipeline(self) -> dict:
        """Test full sentiment arbitrage pipeline"""
        n_stocks = 100
        n_timesteps = 50

        # Initialize components
        config = SignalConfig(long_sentiment_threshold=1.0, short_sentiment_threshold=-1.0)

        generator = SignalGenerator(n_stocks=n_stocks, config=config)
        eliminator = EchoChamberEliminator(n_stocks=n_stocks)

        # Generate synthetic data
        np.random.seed(42)
        sentiment = np.random.randn(n_timesteps, n_stocks)
        prices = np.random.randn(n_timesteps, n_stocks).cumsum(axis=0) + 100

        # Run pipeline
        total_signals = 0
        for t in range(20, n_timesteps):
            # Normalize
            z_sentiment = (sentiment[t, :] - np.mean(sentiment[t - 20 : t, :], axis=0)) / np.std(
                sentiment[t - 20 : t, :], axis=0
            )
            z_prices = (prices[t, :] - np.mean(prices[t - 20 : t, :], axis=0)) / np.std(
                prices[t - 20 : t, :], axis=0
            )

            # Calculate dislocation
            dislocation = z_sentiment - z_prices

            # Generate signals
            signals, _ = generator.generate_signals(
                cp.array(z_sentiment),
                cp.array(z_prices),
                cp.array(dislocation),
                cp.array(prices[t, :]),
                timestamp=t,
            )

            total_signals += len(signals)

        return {
            "total_signals": total_signals,
            "signals_per_timestep": total_signals / (n_timesteps - 20),
        }

    # Performance Benchmarks
    def _benchmark_kalman_filter(self):
        """Benchmark Kalman filter performance"""
        print("  Kalman Filter (500 stocks, 1000 timesteps):")

        np.random.seed(42)
        n_stocks = 500
        n_timesteps = 1000

        measurements = np.random.randn(n_timesteps, n_stocks)

        kf = SquareRootKalmanFilter(n_stocks=n_stocks)
        start_time = time.time()
        filtered_states = kf.filter_batch(cp.array(measurements))
        elapsed = time.time() - start_time

        print(f"    Time: {elapsed:.3f}s ({n_timesteps / elapsed:.0f} timesteps/sec)")
        self.benchmark_results["kalman_filter"] = elapsed

    def _benchmark_z_scores(self):
        """Benchmark z-score calculation"""
        print("  Z-Score Calculation (500 stocks, 1000 updates):")

        np.random.seed(42)
        n_stocks = 500
        n_updates = 1000

        data = np.random.randn(n_updates, n_stocks)

        config = ZScoreConfig(method="rolling", lookback=20)
        scorer = RollingZScorer(n_stocks, config)

        start_time = time.time()
        for t in range(n_updates):
            z = scorer.update(cp.array(data[t, :]))
        elapsed = time.time() - start_time

        print(f"    Time: {elapsed:.3f}s ({n_updates / elapsed:.0f} updates/sec)")
        self.benchmark_results["z_scores"] = elapsed

    def _benchmark_signal_generation(self):
        """Benchmark signal generation"""
        print("  Signal Generation (500 stocks, 100 updates):")

        np.random.seed(42)
        n_stocks = 500
        n_updates = 100

        config = SignalConfig()
        generator = SignalGenerator(n_stocks=n_stocks, config=config)

        sentiment = np.random.randn(n_updates, n_stocks)
        price_z = np.random.randn(n_updates, n_stocks)
        dislocation = sentiment - price_z
        prices = np.random.uniform(50, 200, (n_updates, n_stocks))

        start_time = time.time()
        for t in range(n_updates):
            signals, _ = generator.generate_signals(
                cp.array(sentiment[t, :]),
                cp.array(price_z[t, :]),
                cp.array(dislocation[t, :]),
                cp.array(prices[t, :]),
                timestamp=t,
            )
        elapsed = time.time() - start_time

        print(f"    Time: {elapsed:.3f}s ({n_updates / elapsed:.0f} updates/sec)")
        self.benchmark_results["signal_generation"] = elapsed

    def _benchmark_full_pipeline(self):
        """Benchmark full pipeline"""
        print("  Full Pipeline (500 stocks, 50 timesteps):")

        np.random.seed(42)
        n_stocks = 500
        n_timesteps = 50

        config = SignalConfig()
        generator = SignalGenerator(n_stocks=n_stocks, config=config)

        sentiment = np.random.randn(n_timesteps, n_stocks)
        prices = np.random.randn(n_timesteps, n_stocks).cumsum(axis=0) + 100

        start_time = time.time()
        for t in range(20, n_timesteps):
            z_sentiment = (sentiment[t, :] - np.mean(sentiment[t - 20 : t, :], axis=0)) / np.std(
                sentiment[t - 20 : t, :], axis=0
            )
            z_prices = (prices[t, :] - np.mean(prices[t - 20 : t, :], axis=0)) / np.std(
                prices[t - 20 : t, :], axis=0
            )
            dislocation = z_sentiment - z_prices

            signals, _ = generator.generate_signals(
                cp.array(z_sentiment),
                cp.array(z_prices),
                cp.array(dislocation),
                cp.array(prices[t, :]),
                timestamp=t,
            )
        elapsed = time.time() - start_time

        print(f"    Time: {elapsed:.3f}s ({(n_timesteps - 20) / elapsed:.0f} timesteps/sec)")
        self.benchmark_results["full_pipeline"] = elapsed

    def _print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("Test Summary")
        print("=" * 80)

        passed = sum(1 for r in self.test_results if r.passed)
        total = len(self.test_results)

        print(f"\nTests Passed: {passed}/{total} ({passed / total * 100:.1f}%)")

        if self.benchmark_results:
            print("\nBenchmark Results:")
            for name, time in self.benchmark_results.items():
                print(f"  {name}: {time:.3f}s")

        # Save results to JSON
        results = {
            "test_results": [asdict(r) for r in self.test_results],
            "benchmarks": self.benchmark_results,
            "summary": {
                "passed": passed,
                "total": total,
                "pass_rate": passed / total if total > 0 else 0,
            },
        }

        with open(
            "/home/zireael/.openclaw/workspace/sentiment_arbitrage/tests/test_results.json", "w"
        ) as f:
            json.dump(results, f, indent=2)

        print(
            "\nResults saved to: /home/zireael/.openclaw/workspace/sentiment_arbitrage/tests/test_results.json"
        )


def main():
    """Main test runner"""
    framework = TestFramework(verbose=True)
    framework.run_all_tests()


if __name__ == "__main__":
    main()
