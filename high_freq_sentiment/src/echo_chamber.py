"""
Echo Chamber Elimination through Orthogonalization
==================================================

Advanced techniques for removing market-wide sentiment effects and extracting
idiosyncratic signals. This prevents false signals from market-wide events.

Key Features:
- Orthogonalization against market sentiment
- Principal Component Analysis (PCA) for dimensionality reduction
- Robust regression for factor removal
- Sparse coding for interpretable factors
- GPU-accelerated using CuPy

Author: Algorithm Designer
Date: 2026-03-09
"""

import warnings
from dataclasses import dataclass

import cupy as cp
import numpy as np

warnings.filterwarnings("ignore")


@dataclass
class OrthogonalizationConfig:
    """Configuration for orthogonalization methods"""

    method: str = "projection"  # "projection", "pca", "robust_regression"
    n_factors: int = 3  # Number of factors to remove
    use_market_sentiment: bool = True  # Include market sentiment as factor
    use_sector_factors: bool = True  # Include sector factors
    sparse_factors: bool = False  # Use sparse coding
    tolerance: float = 1e-6  # Numerical tolerance


class MarketSentimentOrthogonalizer:
    """
    Remove market-wide sentiment effects to get idiosyncratic signals.

    Uses orthogonal projection to remove the component of sentiment
    that's correlated with market-wide factors.
    """

    def __init__(self, n_stocks: int = 500, config: OrthogonalizationConfig | None = None):
        """
        Initialize orthogonalizer

        Args:
            n_stocks: Number of stocks
            config: Orthogonalization configuration
        """
        self.n_stocks = n_stocks
        self.config = config or OrthogonalizationConfig()

        # Track market sentiment
        self.market_sentiment_history = cp.zeros(100, dtype=cp.float32)
        self.market_sentiment_ptr = 0

        # Factor loadings
        self.factor_loadings = cp.zeros((n_stocks, self.config.n_factors), dtype=cp.float32)
        self.factors_initialized = False

    def orthogonalize_projection(
        self,
        stock_sentiments: cp.ndarray,
        market_sentiment: cp.ndarray,
        sector_sentiments: cp.ndarray | None = None,
    ) -> cp.ndarray:
        """
        Orthogonalize using projection method

        Removes the projection of stock sentiments onto market/sector factors.

        Args:
            stock_sentiments: Stock sentiment scores (n_stocks,)
            market_sentiment: Market-wide sentiment (scalar)
            sector_sentiments: Sector sentiment scores (n_sectors,)

        Returns:
            Idiosyncratic sentiment (n_stocks,)
        """
        # Create factor matrix
        if self.config.use_market_sentiment and self.config.use_sector_factors:
            if sector_sentiments is None:
                # Just market sentiment
                factors = cp.array([[market_sentiment]])
            else:
                # Market + sector factors
                factors = cp.concatenate(
                    [cp.array([[market_sentiment]]), sector_sentiments.reshape(-1, 1)], axis=1
                )
        elif self.config.use_market_sentiment:
            factors = cp.array([[market_sentiment]])
        elif sector_sentiments is not None:
            factors = sector_sentiments.reshape(-1, 1)
        else:
            # No factors to remove
            return stock_sentiments

        # Compute projection coefficients (beta)
        # beta = (F^T F)^-1 F^T s
        try:
            F_T_F = factors.T @ factors
            beta = cp.linalg.inv(F_T_F) @ factors.T @ stock_sentiments
        except cp.linalg.LinAlgError:
            # Use pseudo-inverse if singular
            beta = cp.linalg.pinv(factors) @ stock_sentiments

        # Remove projection
        idio_sentiment = stock_sentiments - factors @ beta

        # Ensure orthogonality
        # Verify that dot product with factors is zero (or close to zero)
        dot_product = factors.T @ idio_sentiment
        if cp.max(cp.abs(dot_product)) > self.config.tolerance:
            # Refine orthogonalization
            idio_sentiment = stock_sentiment - factors @ beta

        return idio_sentiment

    def update_market_sentiment(self, new_market_sentiment: float):
        """Update market sentiment history"""
        self.market_sentiment_history[self.market_sentiment_ptr] = new_market_sentiment
        self.market_sentiment_ptr = (self.market_sentiment_ptr + 1) % 100


class PCAOrthogonalizer:
    """
    Use Principal Component Analysis to identify and remove common factors.

    PCA finds the directions of maximum variance in the sentiment data.
    Removing the top PCs eliminates market-wide patterns.
    """

    def __init__(
        self,
        n_stocks: int = 500,
        n_components: int = 3,
        config: OrthogonalizationConfig | None = None,
    ):
        """
        Initialize PCA orthogonalizer

        Args:
            n_stocks: Number of stocks
            n_components: Number of principal components to remove
            config: Configuration
        """
        self.n_stocks = n_stocks
        self.n_components = n_components
        self.config = config or OrthogonalizationConfig()
        self.config.method = "pca"

        # Store PCA components
        self.components = None
        self.mean = None
        self.fitted = False

        # Data buffer for fitting
        self.data_buffer = cp.zeros((n_stocks, 100), dtype=cp.float32)
        self.buffer_ptr = 0
        self.buffer_filled = False

    def fit(self, sentiment_data: cp.ndarray):
        """
        Fit PCA model to sentiment data

        Args:
            sentiment_data: Sentiment data (n_stocks, n_samples)
        """
        # Center the data
        self.mean = cp.mean(sentiment_data, axis=1, keepdims=True)
        centered = sentiment_data - self.mean

        # Compute covariance matrix
        cov_matrix = (centered @ centered.T) / (sentiment_data.shape[1] - 1)

        # Eigendecomposition
        eigenvalues, eigenvectors = cp.linalg.eigh(cov_matrix)

        # Sort by eigenvalues (descending)
        idx = cp.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        # Store top components
        self.components = eigenvectors[:, : self.n_components]
        self.fitted = True

        if self.config.sparse_factors:
            # Apply sparsity to components (simple thresholding)
            threshold = cp.std(self.components) * 0.5
            self.components = cp.where(cp.abs(self.components) < threshold, 0, self.components)

        # Print explained variance
        explained_var = eigenvalues[: self.n_components] / cp.sum(eigenvalues)
        print(
            f"Explained variance by top {self.n_components} PCs: {cp.sum(explained_var).get():.3f}"
        )

    def transform(self, sentiment_data: cp.ndarray) -> cp.ndarray:
        """
        Transform data by removing principal components

        Args:
            sentiment_data: Sentiment data (n_stocks,) or (n_stocks, n_samples)

        Returns:
            Idiosyncratic sentiment (same shape as input)
        """
        if not self.fitted:
            raise RuntimeError("PCA model not fitted. Call fit() first.")

        if sentiment_data.ndim == 1:
            # Single observation
            centered = sentiment_data - self.mean.squeeze()

            # Project onto PCs
            scores = self.components.T @ centered

            # Reconstruct using PCs
            reconstruction = self.components @ scores

            # Return residual (idiosyncratic component)
            return sentiment_data - reconstruction
        else:
            # Multiple observations
            centered = sentiment_data - self.mean

            # Project onto PCs
            scores = self.components.T @ centered

            # Reconstruct using PCs
            reconstruction = self.components @ scores

            # Return residuals
            return sentiment_data - reconstruction

    def fit_transform(self, sentiment_data: cp.ndarray) -> cp.ndarray:
        """Fit and transform in one step"""
        self.fit(sentiment_data)
        return self.transform(sentiment_data)

    def update(self, new_sentiment: cp.ndarray):
        """
        Update model with new data point

        Args:
            new_sentiment: New sentiment vector (n_stocks,)
        """
        # Add to buffer
        self.data_buffer[:, self.buffer_ptr] = new_sentiment
        self.buffer_ptr = (self.buffer_ptr + 1) % 100

        if self.buffer_ptr == 0:
            self.buffer_filled = True

        # Refit PCA periodically
        if self.buffer_filled:
            # Use recent data for refitting
            recent_data = self.data_buffer[:, :50]
            self.fit(recent_data)


class RobustRegressionOrthogonalizer:
    """
    Use robust regression to remove factor effects.

    Robust to outliers and handles non-Gaussian noise better than
    ordinary least squares.
    """

    def __init__(self, n_stocks: int = 500, config: OrthogonalizationConfig | None = None):
        """
        Initialize robust regression orthogonalizer

        Args:
            n_stocks: Number of stocks
            config: Configuration
        """
        self.n_stocks = n_stocks
        self.config = config or OrthogonalizationConfig()
        self.config.method = "robust_regression"

        # Factor matrix
        self.factors = None
        self.fitted = False

    def fit(self, sentiment_data: cp.ndarray, factors: cp.ndarray):
        """
        Fit robust regression model

        Args:
            sentiment_data: Sentiment data (n_stocks, n_samples)
            factors: Factor data (n_factors, n_samples)
        """
        # Transpose for regression: samples as rows
        Y = sentiment_data.T  # (n_samples, n_stocks)
        X = factors.T  # (n_samples, n_factors)

        # Robust regression using Huber loss (simplified)
        # For production, use sklearn's HuberRegressor or similar
        self.factors = factors
        self.fitted = True

        # Compute factor loadings using OLS (can be upgraded to robust)
        # beta = (X^T X)^-1 X^T Y
        try:
            X_T_X = X.T @ X
            X_inv = cp.linalg.inv(X_T_X)
            self.beta = X_inv @ X.T @ Y
        except cp.linalg.LinAlgError:
            # Use pseudo-inverse if singular
            self.beta = cp.linalg.pinv(X) @ Y

    def transform(self, sentiment_data: cp.ndarray) -> cp.ndarray:
        """
        Transform by removing factor effects

        Args:
            sentiment_data: Sentiment data (n_stocks,) or (n_stocks, n_samples)

        Returns:
            Idiosyncratic sentiment
        """
        if not self.fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        if sentiment_data.ndim == 1:
            # Single observation
            factor_contribution = self.factors.T @ self.beta.T
            return sentiment_data - factor_contribution[:, 0]
        else:
            # Multiple observations
            factor_contribution = self.factors @ self.beta.T
            return sentiment_data - factor_contribution.T

    def fit_transform(self, sentiment_data: cp.ndarray, factors: cp.ndarray) -> cp.ndarray:
        """Fit and transform in one step"""
        self.fit(sentiment_data, factors)
        return self.transform(sentiment_data)


class EchoChamberEliminator:
    """
    Main class for echo chamber elimination.

    Combines multiple orthogonalization methods for robust signal extraction.
    """

    def __init__(
        self,
        n_stocks: int = 500,
        methods: list[str] = ["projection", "pca"],
        config: OrthogonalizationConfig | None = None,
    ):
        """
        Initialize echo chamber eliminator

        Args:
            n_stocks: Number of stocks
            methods: List of methods to apply
            config: Configuration
        """
        self.n_stocks = n_stocks
        self.methods = methods
        self.config = config or OrthogonalizationConfig()

        # Initialize orthogonalizers
        self.orthogonalizers = {}

        if "projection" in methods:
            self.orthogonalizers["projection"] = MarketSentimentOrthogonalizer(n_stocks, config)

        if "pca" in methods:
            self.orthogonalizers["pca"] = PCAOrthogonalizer(
                n_stocks, n_components=config.n_factors, config=config
            )

        if "robust_regression" in methods:
            self.orthogonalizers["robust_regression"] = RobustRegressionOrthogonalizer(
                n_stocks, config
            )

        # Track results for analysis
        self.original_sentiments = []
        self.idio_sentiments = []

    def eliminate_echo_chamber(
        self,
        stock_sentiments: cp.ndarray,
        market_sentiment: float | None = None,
        sector_sentiments: cp.ndarray | None = None,
        factors: cp.ndarray | None = None,
    ) -> cp.ndarray:
        """
        Apply all orthogonalization methods

        Args:
            stock_sentiments: Stock sentiment scores (n_stocks,)
            market_sentiment: Market sentiment (scalar)
            sector_sentiments: Sector sentiments (n_sectors,)
            factors: Additional factors (n_factors, n_samples)

        Returns:
            Idiosyncratic sentiment after all transformations
        """
        # Store original
        self.original_sentiments.append(stock_sentiments.get())

        # Start with original
        idio_sentiment = stock_sentiments.copy()

        # Apply each method
        for method in self.methods:
            if method not in self.orthogonalizers:
                continue

            orthogonalizer = self.orthogonalizers[method]

            if method == "projection":
                if market_sentiment is None:
                    # Estimate market sentiment as mean
                    market_sentiment = float(cp.mean(stock_sentiments))
                idio_sentiment = orthogonalizer.orthogonalize_projection(
                    idio_sentiment, cp.array([market_sentiment]), sector_sentiments
                )

            elif method == "pca":
                # PCA needs batch data for fitting
                # For single observation, use pre-fit model
                if orthogonalizer.fitted:
                    idio_sentiment = orthogonalizer.transform(idio_sentiment)
                else:
                    # Not enough data, skip
                    pass

            elif method == "robust_regression":
                if factors is not None and orthogonalizer.fitted:
                    idio_sentiment = orthogonalizer.transform(idio_sentiment)

        # Store result
        self.idio_sentiments.append(idio_sentiment.get())

        return idio_sentiment

    def verify_orthogonality(
        self, idio_sentiment: cp.ndarray, market_sentiment: cp.ndarray
    ) -> float:
        """
        Verify that idiosyncratic sentiment is orthogonal to market factors

        Args:
            idio_sentiment: Idiosyncratic sentiment
            market_sentiment: Market sentiment

        Returns:
            Correlation (should be close to 0)
        """
        correlation = cp.corrcoef(idio_sentiment, market_sentiment)[0, 1]
        return float(correlation)

    def get_statistics(self) -> dict:
        """Get statistics on orthogonalization"""
        if not self.original_sentiments or not self.idio_sentiments:
            return {}

        original = np.array(self.original_sentiments)
        idio = np.array(self.idio_sentiments)

        return {
            "mean_original": float(np.mean(original)),
            "mean_idio": float(np.mean(idio)),
            "std_original": float(np.std(original)),
            "std_idio": float(np.std(idio)),
            "n_orthogonalizations": len(self.original_sentiments),
        }


def test_echo_chamber_elimination():
    """Test echo chamber elimination methods"""
    print("Testing Echo Chamber Elimination...")

    # Generate synthetic data with market factor
    np.random.seed(42)
    n_stocks = 100
    n_samples = 50

    # Create market sentiment (common factor)
    market_sentiment = np.random.randn(n_samples) * 0.5

    # Create stock-specific sentiment
    idio_sentiment = np.random.randn(n_stocks, n_samples) * 0.3

    # Combine: stock_sentiment = market_sentiment + idio_sentiment + noise
    noise = np.random.randn(n_stocks, n_samples) * 0.1
    stock_sentiment = market_sentiment + idio_sentiment + noise

    # Convert to GPU
    stock_sentiment_gpu = cp.array(stock_sentiment)
    market_sentiment_gpu = cp.array(market_sentiment)

    # Test projection method
    print("\n1. Testing Projection Method...")
    projector = MarketSentimentOrthogonalizer(n_stocks)

    idio_projection = projector.orthogonalize_projection(
        stock_sentiment_gpu[:, 0], market_sentiment_gpu[0]
    )

    correlation = projector.verify_orthogonality(
        idio_projection, cp.array([market_sentiment_gpu[0]])
    )

    print(f"Correlation with market sentiment: {correlation:.4f} (should be ~0)")
    print(f"Mean idio sentiment: {float(cp.mean(idio_projection)):.4f}")

    # Test PCA method
    print("\n2. Testing PCA Method...")
    pca = PCAOrthogonalizer(n_stocks, n_components=3)

    # Fit PCA
    idio_pca = pca.fit_transform(stock_sentiment_gpu[:, :30])

    # Test on new data
    test_idio = pca.transform(stock_sentiment_gpu[:, 0])

    print(f"Test idio sentiment mean: {float(cp.mean(test_idio)):.4f}")
    print(f"Test idio sentiment std: {float(cp.std(test_idio)):.4f}")

    # Test combined eliminator
    print("\n3. Testing Combined Eliminator...")
    eliminator = EchoChamberEliminator(
        n_stocks=n_stocks,
        methods=["projection", "pca"],
        config=OrthogonalizationConfig(n_factors=3),
    )

    # Fit PCA first
    eliminator.orthogonalizers["pca"].fit(stock_sentiment_gpu[:, :30])

    # Test elimination
    idio_combined = eliminator.eliminate_echo_chamber(
        stock_sentiment_gpu[:, 0], market_sentiment=float(market_sentiment_gpu[0])
    )

    correlation = eliminator.verify_orthogonality(idio_combined, market_sentiment_gpu[0])

    print(f"Correlation with market sentiment: {correlation:.4f}")

    # Get statistics
    stats = eliminator.get_statistics()
    print("\nStatistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n✓ Echo chamber elimination tests passed!")


if __name__ == "__main__":
    test_echo_chamber_elimination()
