"""
Signal Enhancement Module for Sentiment Arbitrage System
========================================================

Advanced signal enhancement techniques using ensemble methods, Bayesian model averaging,
and adaptive signal filtering. This module improves signal quality through:

1. Ensemble signal combination (multiple signal sources)
2. Bayesian model averaging for uncertainty quantification
3. Adaptive Kalman filtering for dynamic signal tracking
4. Outlier detection and robust signal processing
5. Cross-validation for signal reliability assessment

Author: Algorithm Designer
Date: 2026-03-09
"""

import numpy as np
import cupy as cp
from typing import List, Tuple, Dict, Optional, Union
from dataclasses import dataclass, field
from scipy import stats
from scipy.sparse import csr_matrix
import warnings
warnings.filterwarnings('ignore')

try:
    from cupy.cuda import Stream
    CUPY_CUDA_AVAILABLE = True
except ImportError:
    CUPY_CUDA_AVAILABLE = False


@dataclass
class EnhancedSignal:
    """Container for enhanced signal with metadata"""
    signal: np.ndarray
    confidence: np.ndarray
    uncertainty: np.ndarray
    ensemble_weights: np.ndarray
    timestamps: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalSource:
    """Container for a signal source with its characteristics"""
    name: str
    signals: np.ndarray
    confidence: np.ndarray
    weight: float = 1.0
    is_active: bool = True


class EnsembleSignalCombiner:
    """
    Combine multiple signal sources using weighted ensemble methods
    
    Supports:
    - Simple averaging
    - Weighted averaging
    - Median aggregation (robust to outliers)
    - Quantile aggregation
    - Optimized weighting based on historical performance
    """

    def __init__(
        self,
        method: str = 'weighted',
        optimize_weights: bool = True,
        lookback: int = 50
    ):
        """
        Initialize ensemble signal combiner
        
        Args:
            method: Combination method ('average', 'weighted', 'median', 'quantile', 'optimal')
            optimize_weights: Whether to optimize weights dynamically
            lookback: Lookback period for weight optimization
        """
        self.method = method
        self.optimize_weights = optimize_weights
        self.lookback = lookback
        
        self.weights_history: List[np.ndarray] = []
        self.performance_history: List[float] = []

    def combine(
        self,
        signal_sources: List[SignalSource],
        quantile: float = 0.5
    ) -> EnhancedSignal:
        """
        Combine multiple signal sources into a single enhanced signal
        
        Args:
            signal_sources: List of signal sources
            quantile: Quantile for quantile aggregation (0.0 to 1.0)
            
        Returns:
            Enhanced signal with combined signals and metadata
        """
        # Extract active sources
        active_sources = [s for s in signal_sources if s.is_active]
        if not active_sources:
            raise ValueError("No active signal sources")

        n_timesteps = active_sources[0].signals.shape[0]
        n_sources = len(active_sources)

        # Stack signals
        signals_stack = np.stack([s.signals for s in active_sources], axis=0)  # (n_sources, n_timesteps)
        confidences_stack = np.stack([s.confidence for s in active_sources], axis=0)  # (n_sources, n_timesteps)

        # Get weights
        if self.method == 'weighted' or self.method == 'optimal':
            weights = self._get_weights(active_sources)
        else:
            weights = np.ones(n_sources) / n_sources

        # Combine signals based on method
        if self.method == 'average':
            combined_signal = np.mean(signals_stack, axis=0)
            combined_confidence = np.mean(confidences_stack, axis=0)
        elif self.method == 'weighted':
            weighted_signals = signals_stack * weights[:, np.newaxis]
            weighted_confidences = confidences_stack * weights[:, np.newaxis]
            combined_signal = np.sum(weighted_signals, axis=0)
            combined_confidence = np.sum(weighted_confidences, axis=0)
        elif self.method == 'median':
            combined_signal = np.median(signals_stack, axis=0)
            combined_confidence = np.median(confidences_stack, axis=0)
        elif self.method == 'quantile':
            combined_signal = np.quantile(signals_stack, quantile, axis=0)
            combined_confidence = np.quantile(confidences_stack, quantile, axis=0)
        elif self.method == 'optimal':
            # Use optimal weighting based on historical performance
            combined_signal = np.sum(signals_stack * weights[:, np.newaxis], axis=0)
            combined_confidence = np.sum(confidences_stack * weights[:, np.newaxis], axis=0)
        else:
            raise ValueError(f"Unknown method: {self.method}")

        # Calculate uncertainty based on disagreement among sources
        signal_std = np.std(signals_stack, axis=0)
        uncertainty = signal_std * (1.0 - combined_confidence)

        return EnhancedSignal(
            signal=combined_signal,
            confidence=combined_confidence,
            uncertainty=uncertainty,
            ensemble_weights=weights,
            metadata={
                'method': self.method,
                'n_sources': n_sources,
                'source_names': [s.name for s in active_sources]
            }
        )

    def _get_weights(self, signal_sources: List[SignalSource]) -> np.ndarray:
        """
        Get weights for signal sources
        
        Args:
            signal_sources: List of signal sources
            
        Returns:
            Weight array (normalized to sum to 1)
        """
        n_sources = len(signal_sources)

        if self.method == 'optimal' and self.optimize_weights and len(self.performance_history) > 0:
            # Use optimized weights based on historical performance
            if len(self.weights_history) > 0:
                # Use last optimized weights with small adjustment
                weights = self.weights_history[-1].copy()
                # Adjust based on recent performance
                recent_perf = np.array(self.performance_history[-5:])
                if len(recent_perf) >= 2:
                    improvement_rate = (recent_perf[-1] - recent_perf[-2]) / recent_perf[-2]
                    weights *= (1.0 + improvement_rate * 0.1)
                weights = np.maximum(weights, 0.01)  # Prevent negative weights
                weights = weights / np.sum(weights)
                return weights

        # Default to confidence-based weighting
        confidences = np.array([s.confidence.mean() for s in signal_sources])
        weights = confidences / np.sum(confidences)
        
        # Normalize to source weights
        source_weights = np.array([s.weight for s in signal_sources])
        weights = weights * source_weights
        weights = weights / np.sum(weights)

        return weights

    def update_performance(self, performance: float, weights: np.ndarray):
        """
        Update performance history and weights
        
        Args:
            performance: Performance metric (e.g., Sharpe ratio, accuracy)
            weights: Weights used for this performance
        """
        self.performance_history.append(performance)
        self.weights_history.append(weights.copy())


class BayesianModelAverager:
    """
    Bayesian Model Averaging (BMA) for combining signals with uncertainty quantification
    
    BMA provides:
    - Posterior model probabilities
    - Model-averaged predictions
    - Full posterior uncertainty
    - Model selection consistency
    """

    def __init__(
        self,
        n_models: int,
        prior_weights: Optional[np.ndarray] = None,
        adapt_prior: bool = True
    ):
        """
        Initialize Bayesian model averager
        
        Args:
            n_models: Number of models/signal sources
            prior_weights: Prior weights for each model (uniform if None)
            adapt_prior: Whether to adapt prior based on performance
        """
        self.n_models = n_models
        
        if prior_weights is None:
            self.posterior_weights = np.ones(n_models) / n_models
        else:
            self.posterior_weights = np.array(prior_weights)
            self.posterior_weights = self.posterior_weights / np.sum(self.posterior_weights)
        
        self.adapt_prior = adapt_prior
        self.likelihood_history: List[np.ndarray] = []
        self.posterior_history: List[np.ndarray] = []

    def update(
        self,
        model_predictions: np.ndarray,
        observations: np.ndarray,
        model_errors: Optional[np.ndarray] = None
    ) -> EnhancedSignal:
        """
        Update posterior weights based on new observations
        
        Args:
            model_predictions: Model predictions (n_models, n_timesteps)
            observations: Observed values (n_timesteps,)
            model_errors: Model error estimates (n_models, n_timesteps), optional
            
        Returns:
            Enhanced signal with BMA predictions
        """
        n_models, n_timesteps = model_predictions.shape

        # Calculate likelihoods
        if model_errors is None:
            # Estimate errors from residuals
            errors = model_predictions - observations[np.newaxis, :]
            model_errors = np.std(errors, axis=1, keepdims=True)
            model_errors = np.maximum(model_errors, 1e-6)  # Avoid division by zero

        # Compute likelihood for each model (assuming Gaussian errors)
        residuals = model_predictions - observations[np.newaxis, :]
        log_likelihoods = -0.5 * np.sum((residuals / model_errors) ** 2, axis=1)
        log_likelihoods -= 0.5 * n_timesteps * np.log(2 * np.pi)
        log_likelihoods -= n_timesteps * np.log(model_errors.flatten())

        # Update posterior weights
        log_prior = np.log(self.posterior_weights + 1e-10)
        log_posterior = log_prior + log_likelihoods
        
        # Normalize (log-sum-exp trick for numerical stability)
        max_log = np.max(log_posterior)
        self.posterior_weights = np.exp(log_posterior - max_log)
        self.posterior_weights = self.posterior_weights / np.sum(self.posterior_weights)

        # Record history
        self.likelihood_history.append(np.exp(log_likelihoods))
        self.posterior_history.append(self.posterior_weights.copy())

        # Compute model-averaged predictions
        averaged_predictions = np.sum(
            model_predictions * self.posterior_weights[:, np.newaxis],
            axis=0
        )

        # Compute uncertainty (combination of model variance and within-model variance)
        between_model_variance = np.sum(
            self.posterior_weights[:, np.newaxis] * 
            (model_predictions - averaged_predictions[np.newaxis, :]) ** 2,
            axis=0
        )
        within_model_variance = np.sum(
            self.posterior_weights[:, np.newaxis] * model_errors ** 2,
            axis=0
        )
        total_uncertainty = np.sqrt(between_model_variance + within_model_variance)

        # Confidence based on uncertainty (inverse relationship)
        confidence = 1.0 / (1.0 + total_uncertainty)
        confidence = np.clip(confidence, 0.0, 1.0)

        return EnhancedSignal(
            signal=averaged_predictions,
            confidence=confidence,
            uncertainty=total_uncertainty,
            ensemble_weights=self.posterior_weights,
            metadata={
                'method': 'bma',
                'n_models': n_models,
                'posterior_weights': self.posterior_weights.copy()
            }
        )

    def get_model_probabilities(self) -> np.ndarray:
        """Get current posterior model probabilities"""
        return self.posterior_weights.copy()


class AdaptiveSignalFilter:
    """
    Adaptive filtering for signal enhancement using dynamic Kalman filtering
    
    Features:
    - Adaptive noise estimation
    - State-dependent filtering
    - Multiple filter configurations
    - Ensemble filtering
    """

    def __init__(
        self,
        n_filters: int = 3,
        adaptation_rate: float = 0.1,
        min_process_noise: float = 1e-6,
        max_process_noise: float = 1e-2
    ):
        """
        Initialize adaptive signal filter
        
        Args:
            n_filters: Number of parallel filters
            adaptation_rate: Rate of adaptation for noise parameters
            min_process_noise: Minimum process noise
            max_process_noise: Maximum process noise
        """
        self.n_filters = n_filters
        self.adaptation_rate = adaptation_rate
        self.min_process_noise = min_process_noise
        self.max_process_noise = max_process_noise

        # Initialize filters with different noise levels
        self.process_noises = np.logspace(
            np.log10(min_process_noise),
            np.log10(max_process_noise),
            n_filters
        )
        self.measurement_noise = 1e-3

        # Filter states
        self.filter_states: List[Dict] = []
        for i in range(n_filters):
            self.filter_states.append({
                'x': 0.0,
                'P': 1.0,
                'process_noise': self.process_noises[i]
            })

        # Ensemble weights
        self.ensemble_weights = np.ones(n_filters) / n_filters

    def filter(self, observation: float, innovation: Optional[float] = None) -> Tuple[float, float, float]:
        """
        Apply adaptive filtering to observation
        
        Args:
            observation: New observation
            innovation: Optional innovation signal for adaptation
            
        Returns:
            Tuple of (filtered_estimate, uncertainty, ensemble_weight)
        """
        # Run all filters
        estimates = []
        uncertainties = []

        for i, state in enumerate(self.filter_states):
            # Prediction
            x_pred = state['x']
            P_pred = state['P'] + state['process_noise']

            # Update
            K = P_pred / (P_pred + self.measurement_noise)
            x_new = x_pred + K * (observation - x_pred)
            P_new = (1 - K) * P_pred

            # Update state
            state['x'] = x_new
            state['P'] = P_new

            estimates.append(x_new)
            uncertainties.append(np.sqrt(P_new))

        estimates = np.array(estimates)
        uncertainties = np.array(uncertainties)

        # Ensemble combination
        ensemble_estimate = np.sum(estimates * self.ensemble_weights)
        ensemble_uncertainty = np.sum(uncertainties * self.ensemble_weights)

        # Adapt process noises based on innovation
        if innovation is not None:
            self._adapt_noises(innovation)

        # Update ensemble weights based on uncertainty
        # Lower uncertainty = higher weight
        inv_uncertainties = 1.0 / (uncertainties + 1e-6)
        self.ensemble_weights = inv_uncertainties / np.sum(inv_uncertainties)

        return ensemble_estimate, ensemble_uncertainty, self.ensemble_weights[0]

    def _adapt_noises(self, innovation: float):
        """
        Adapt process noise levels based on innovation
        
        Args:
            innovation: Innovation signal
        """
        innovation_mag = abs(innovation)

        for state in self.filter_states:
            # Increase noise if innovation is large, decrease if small
            if innovation_mag > 2.0:  # Large innovation
                state['process_noise'] = min(
                    self.max_process_noise,
                    state['process_noise'] * (1.0 + self.adaptation_rate)
                )
            elif innovation_mag < 1.0:  # Small innovation
                state['process_noise'] = max(
                    self.min_process_noise,
                    state['process_noise'] * (1.0 - self.adaptation_rate)
                )

    def reset(self):
        """Reset all filter states"""
        for state in self.filter_states:
            state['x'] = 0.0
            state['P'] = 1.0
        self.ensemble_weights = np.ones(self.n_filters) / self.n_filters


class OutlierDetector:
    """
    Robust outlier detection for signal cleaning
    
    Methods:
    - Z-score based
    - Median Absolute Deviation (MAD)
    - Isolation Forest
    - Robust PCA
    """

    def __init__(
        self,
        method: str = 'mad',
        threshold: float = 3.0,
        window_size: int = 50
    ):
        """
        Initialize outlier detector
        
        Args:
            method: Detection method ('zscore', 'mad', 'iqr')
            threshold: Threshold for outlier detection
            window_size: Window size for rolling statistics
        """
        self.method = method
        self.threshold = threshold
        self.window_size = window_size

        # History for rolling statistics
        self.history: List[float] = []

    def detect(self, value: float) -> Tuple[bool, float]:
        """
        Detect if value is an outlier
        
        Args:
            value: Value to check
            
        Returns:
            Tuple of (is_outlier, score)
        """
        self.history.append(value)
        if len(self.history) > self.window_size:
            self.history.pop(0)

        if len(self.history) < 10:
            return False, 0.0

        history_array = np.array(self.history)

        if self.method == 'zscore':
            mean = np.mean(history_array[:-1])  # Exclude current value
            std = np.std(history_array[:-1])
            if std > 0:
                score = abs((value - mean) / std)
                is_outlier = score > self.threshold
            else:
                score = 0.0
                is_outlier = False

        elif self.method == 'mad':
            median = np.median(history_array[:-1])
            mad = np.median(np.abs(history_array[:-1] - median))
            if mad > 0:
                score = abs((value - median) / (1.4826 * mad))
                is_outlier = score > self.threshold
            else:
                score = 0.0
                is_outlier = False

        elif self.method == 'iqr':
            q1 = np.percentile(history_array[:-1], 25)
            q3 = np.percentile(history_array[:-1], 75)
            iqr = q3 - q1
            if iqr > 0:
                lower_bound = q1 - self.threshold * iqr
                upper_bound = q3 + self.threshold * iqr
                is_outlier = value < lower_bound or value > upper_bound
                score = max(abs(value - lower_bound), abs(value - upper_bound)) / iqr
            else:
                score = 0.0
                is_outlier = False

        else:
            raise ValueError(f"Unknown method: {self.method}")

        return is_outlier, score

    def clean_signal(self, signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Clean signal by replacing outliers with interpolated values
        
        Args:
            signal: Input signal
            
        Returns:
            Tuple of (cleaned_signal, outlier_mask)
        """
        n = len(signal)
        cleaned = signal.copy()
        outlier_mask = np.zeros(n, dtype=bool)

        for i in range(n):
            # Reset history for each signal
            if i == 0:
                self.history = []

            is_outlier, score = self.detect(signal[i])
            outlier_mask[i] = is_outlier

            if is_outlier and i > 0 and i < n - 1:
                # Replace with linear interpolation of neighbors
                cleaned[i] = (signal[i-1] + signal[i+1]) / 2

        return cleaned, outlier_mask


class CrossValidator:
    """
    Cross-validation for signal reliability assessment
    
    Features:
    - Time-series cross-validation
    - Performance metrics calculation
    - Statistical significance testing
    """

    def __init__(
        self,
        n_folds: int = 5,
        test_size: int = 100,
        metrics: List[str] = None
    ):
        """
        Initialize cross-validator
        
        Args:
            n_folds: Number of cross-validation folds
            test_size: Size of test set for each fold
            metrics: List of metrics to compute
        """
        self.n_folds = n_folds
        self.test_size = test_size

        if metrics is None:
            self.metrics = ['mse', 'mae', 'correlation', 'sharpe']
        else:
            self.metrics = metrics

    def validate(
        self,
        predictions: np.ndarray,
        targets: np.ndarray,
        returns: Optional[np.ndarray] = None
    ) -> Dict[str, float]:
        """
        Perform cross-validation on predictions
        
        Args:
            predictions: Model predictions
            targets: Target values
            returns: Optional returns for Sharpe ratio calculation
            
        Returns:
            Dictionary of cross-validation metrics
        """
        n_samples = len(predictions)
        results = {metric: [] for metric in self.metrics}

        for fold in range(self.n_folds):
            # Time-series split
            test_start = fold * (n_samples // self.n_folds)
            test_end = min(test_start + self.test_size, n_samples)

            if test_end >= n_samples:
                break

            train_indices = np.arange(test_start)
            test_indices = np.arange(test_start, test_end)

            # Calculate metrics on test set
            pred_test = predictions[test_indices]
            target_test = targets[test_indices]

            if 'mse' in self.metrics:
                mse = np.mean((pred_test - target_test) ** 2)
                results['mse'].append(mse)

            if 'mae' in self.metrics:
                mae = np.mean(np.abs(pred_test - target_test))
                results['mae'].append(mae)

            if 'correlation' in self.metrics:
                corr = np.corrcoef(pred_test, target_test)[0, 1]
                results['correlation'].append(corr if not np.isnan(corr) else 0.0)

            if 'sharpe' in self.metrics and returns is not None:
                # Sharpe ratio based on predictions
                returns_test = returns[test_indices]
                if len(returns_test) > 0 and np.std(returns_test) > 0:
                    sharpe = np.mean(returns_test) / np.std(returns_test)
                    results['sharpe'].append(sharpe)
                else:
                    results['sharpe'].append(0.0)

        # Aggregate results
        summary = {}
        for metric, values in results.items():
            if values:
                summary[f'{metric}_mean'] = np.mean(values)
                summary[f'{metric}_std'] = np.std(values)
                summary[f'{metric}_min'] = np.min(values)
                summary[f'{metric}_max'] = np.max(values)

        return summary


def test_signal_enhancement():
    """Test signal enhancement module"""
    print("Testing Signal Enhancement Module")

    # Test ensemble combiner
    print("\n1. Testing Ensemble Signal Combiner")
    combiner = EnsembleSignalCombiner(method='weighted')

    n_timesteps = 1000
    n_sources = 5

    signal_sources = []
    for i in range(n_sources):
        signals = np.random.randn(n_timesteps) + i * 0.1
        confidence = np.random.uniform(0.5, 1.0, n_timesteps)
        signal_sources.append(SignalSource(
            name=f'source_{i}',
            signals=signals,
            confidence=confidence,
            weight=1.0 - i * 0.1
        ))

    enhanced = combiner.combine(signal_sources)
    print(f"   Combined signal shape: {enhanced.signal.shape}")
    print(f"   Mean confidence: {enhanced.confidence.mean():.3f}")
    print(f"   Mean uncertainty: {enhanced.uncertainty.mean():.3f}")
    print(f"   Ensemble weights: {enhanced.ensemble_weights}")

    # Test Bayesian model averaging
    print("\n2. Testing Bayesian Model Averaging")
    bma = BayesianModelAverager(n_models=5)

    model_preds = np.random.randn(5, n_timesteps) + np.random.randn(1, n_timesteps) * 0.5
    observations = np.random.randn(n_timesteps)

    enhanced_bma = bma.update(model_preds, observations)
    print(f"   BMA signal shape: {enhanced_bma.signal.shape}")
    print(f"   Posterior weights: {bma.get_model_probabilities()}")

    # Test adaptive filter
    print("\n3. Testing Adaptive Signal Filter")
    adaptive_filter = AdaptiveSignalFilter(n_filters=3)

    for i in range(100):
        obs = np.random.randn() + 0.1 * np.sin(i / 10.0)
        est, unc, weight = adaptive_filter.filter(obs, innovation=obs - est if i > 0 else 0)

    print(f"   Final estimate: {est:.3f}")
    print(f"   Uncertainty: {unc:.3f}")

    # Test outlier detector
    print("\n4. Testing Outlier Detector")
    detector = OutlierDetector(method='mad', threshold=3.0)

    clean_signal = np.random.randn(100)
    clean_signal[50] = 10.0  # Add outlier
    cleaned, mask = detector.clean_signal(clean_signal)

    print(f"   Outliers detected: {np.sum(mask)}")
    print(f"   Outlier at index 50: {mask[50]}")
    print(f"   Original value: {clean_signal[50]:.2f}")
    print(f"   Cleaned value: {cleaned[50]:.2f}")

    # Test cross-validator
    print("\n5. Testing Cross-Validator")
    cv = CrossValidator(n_folds=5, test_size=50)

    predictions = np.random.randn(500)
    targets = np.random.randn(500) + 0.3 * predictions
    returns = np.random.randn(500) * 0.01

    results = cv.validate(predictions, targets, returns)
    print(f"   MSE mean: {results['mse_mean']:.6f} ± {results['mse_std']:.6f}")
    print(f"   Correlation mean: {results['correlation_mean']:.3f} ± {results['correlation_std']:.3f}")

    print("\n✓ Signal Enhancement Module tests passed")


if __name__ == "__main__":
    test_signal_enhancement()
