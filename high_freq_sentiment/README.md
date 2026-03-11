# Vectorized Sentiment Arbitrage System

A high-performance sentiment arbitrage trading system for 500+ stocks using GPU-optimized vectorized processing, Kalman filters, and machine learning-based sentiment extraction.

## 🎯 System Overview

This system implements sophisticated mathematical models to identify mispricing opportunities when investor sentiment deviates from intrinsic value. The system uses:

- **Kalman Filters**: For adaptive state estimation (P_t = β * S_t + ε)
- **Vectorized Z-Scoring**: Cross-sectional normalization across 500+ stocks
- **Sentiment Extraction**: Distil-FinBERT with Triton Inference Server
- **Echo Chamber Elimination**: Orthogonalization to remove market-wide effects
- **Signal Generation**: Entry/exit conditions with risk management

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Ingestion Layer                      │
│         (News feeds, Social media, Market data)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               Sentiment Extraction Layer                     │
│              (Distil-FinBERT + Triton)                      │
│         • GPU-accelerated inference                          │
│         • Dynamic batching                                   │
│         • FP16/INT8 quantization                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   State Estimation Layer                     │
│                 (Square-Root Kalman Filter)                  │
│         • Numerical stability                                │
│         • Vectorized operations                              │
│         • Adaptive noise estimation                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Signal Processing Layer                      │
│         ┌──────────────┐  ┌──────────────────┐              │
│         │ Z-Scoring    │  │ Echo Chamber     │              │
│         │ (Rolling/Exp)│  │ Elimination      │              │
│         │              │  │ (Projection/PCA) │              │
│         └──────────────┘  └──────────────────┘              │
│                           │                                   │
│                           ▼                                   │
│                   Dislocation = S - P                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Signal Generation Layer                     │
│         ┌──────────────┐  ┌──────────────────┐              │
│         │ Buy Signals  │  │ Sell Signals     │              │
│         │ High S       │  │ Low S            │              │
│         │ Low P        │  │ High P           │              │
│         └──────────────┘  └──────────────────┘              │
│                           │                                   │
│                           ▼                                   │
│                 Risk Management & Position Sizing           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     Execution Layer                         │
│              (Order Management, Risk Controls)               │
└─────────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
sentiment_arbitrage/
├── src/
│   ├── kalman_filter.py          # Square-root Kalman filter implementation
│   ├── z_scoring.py               # Vectorized z-score calculators
│   ├── sentiment_extraction.py   # Triton + Distil-FinBERT integration
│   ├── echo_chamber.py           # Orthogonalization methods
│   └── signal_generation.py      # Signal generation & risk management
├── tests/
│   └── test_framework.py         # Comprehensive testing framework
├── data/
│   └── backtest_results.json     # Backtest results storage
├── configs/
│   ├── default_config.json       # Default system configuration
│   └── triton_config.json       # Triton server configuration
├── main.py                       # Main integration module
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## 🚀 Quick Start

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install CuPy for GPU acceleration (choose appropriate version)
pip install cupy-cuda12x  # For CUDA 12.x
# or
pip install cupy-rocm-5-0  # For ROCm 5.0
```

### Running the System

```bash
# Run demonstration
python main.py

# Run tests
python tests/test_framework.py

# Run with custom configuration
python main.py --config configs/default_config.json
```

## 🧮 Mathematical Models

### Kalman Filter

**State Equation**: P_t = β * S_t + ε

**Prediction Step**:
- x̂_t|t-1 = F * x̂_t-1|t-1
- P_t|t-1 = F * P_t-1|t-1 * F^T + Q

**Update Step**:
- K_t = P_t|t-1 * H^T * (H * P_t|t-1 * H^T + R)^-1
- x̂_t|t = x̂_t|t-1 + K_t * (z_t - H * x̂_t|t-1)
- P_t|t = (I - K_t * H) * P_t|t-1

Where:
- β: State coefficient (relationship between sentiment and price)
- S_t: Sentiment score at time t
- ε: Process noise
- Q: Process noise covariance
- R: Measurement noise covariance
- K_t: Kalman gain

### Vectorized Z-Scoring

**Rolling Z-Score**:
z_t = (x_t - μ_t-lookback:t-1) / σ_t-lookback:t-1

**Exponential Z-Score**:
- EMA_t = α * x_t + (1-α) * EMA_t-1
- EMSD_t = α * (x_t - EMA_t)^2 + (1-α) * EMSD_t-1
- z_t = (x_t - EMA_t) / √EMSD_t

**Cross-Sectional Z-Score**:
z_i = (x_i - μ_universe) / σ_universe

### Echo Chamber Elimination

**Projection Method**:
s_idio = s - F * β

Where β = (F^T * F)^-1 * F^T * s

**PCA Method**:
1. Compute principal components of sentiment matrix
2. Project sentiment onto top N components
3. Subtract projection to get idiosyncratic component

### Signal Generation

**Buy Signal Conditions**:
- Sentiment > 1.5σ (high positive sentiment)
- Price Z-score < -0.5σ (low relative price)
- Dislocation > 2.0 (sentiment-price divergence)

**Sell Signal Conditions**:
- Sentiment < -1.5σ (high negative sentiment)
- Price Z-score > 0.5σ (high relative price)
- Dislocation < -2.0 (sentiment-price divergence)

**Exit Conditions**:
- Z-score crosses zero
- Position held > 48 hours
- 15% stop-loss triggered
- 20% take-profit reached

## ⚡ Performance Optimization

### GPU Acceleration

The system leverages CuPy for GPU-accelerated operations:

```python
import cupy as cp

# Vectorized operations on GPU
data_gpu = cp.array(data_cpu)
result_gpu = cp.mean(data_gpu, axis=0)
result_cpu = result_gpu.get()
```

### Dynamic Batching

Triton Inference Server automatically batches inference requests:

```python
# Batch sentiment extraction for 500+ stocks
texts = [news_text_1, news_text_2, ..., news_text_500]
output = sentiment_layer.extract_sentiment_batch(texts)
```

### Memory Efficiency

- Circular buffers for rolling calculations
- FP16/INT8 quantization for inference
- Sparse factor representations

## 🧪 Testing

The system includes a comprehensive testing framework:

```bash
# Run all tests
python tests/test_framework.py

# Test specific components
python -c "from src.kalman_filter import test_kalman_filter; test_kalman_filter()"
python -c "from src.z_scoring import test_z_scorers; test_z_scorers()"
python -c "from src.echo_chamber import test_echo_chamber_elimination; test_echo_chamber_elimination()"
python -c "from src.signal_generation import test_signal_generation; test_signal_generation()"
```

### Test Coverage

- **Unit Tests**: Individual component functionality
- **Integration Tests**: Full pipeline validation
- **Performance Tests**: Latency and throughput benchmarks
- **Numerical Tests**: Stability and accuracy validation

## 📊 Performance Targets

| Metric | Target | Status |
|--------|--------|--------|
| End-to-end latency | <100ms | ✓ Achieved |
| Throughput | 500 stocks/batch | ✓ Achieved |
| GPU utilization | >80% | ⚠ Needs tuning |
| Signal accuracy | >95% | ⚠ Needs validation |
| System availability | 99% | ⚠ In development |

## 🔧 Configuration

### System Configuration

Edit `configs/default_config.json`:

```json
{
  "n_stocks": 500,
  "kalman_process_noise": 1e-5,
  "kalman_measurement_noise": 1e-3,
  "z_score_lookback": 20,
  "z_score_method": "rolling",
  "orthogonalization_method": "projection",
  "long_sentiment_threshold": 1.5,
  "short_sentiment_threshold": -1.5,
  "exit_z_cross": true,
  "exit_time_stop_hours": 48,
  "exit_stop_loss_pct": 0.15,
  "max_position_size": 0.05,
  "use_triton": false
}
```

### Triton Configuration

For production deployment with Triton:

```json
{
  "model_name": "distil_finbert",
  "max_batch_size": 512,
  "preferred_batch_size": [64, 128, 256],
  "instance_group": [
    {
      "count": 1,
      "kind": "GPU"
    }
  ],
  "dynamic_batching": {
    "max_queue_delay_microseconds": 1000
  }
}
```

## 🚦 Risk Management

### Position Sizing

- Maximum 5% of portfolio per stock
- Dynamic sizing based on signal strength
- Volatility-adjusted position limits

### Portfolio Controls

- Maximum 100% portfolio exposure
- Maximum 20% exposure per sector
- Long/short ratio limits (2:1)

### Exit Conditions

- Z-score cross zero (convergence)
- Time stop (48 hours)
- Stop-loss (15%)
- Take-profit (20%)

## 📈 Backtesting

Run historical backtests:

```python
from main import SentimentArbitrageSystem, generate_synthetic_data

# Generate synthetic data
price_data, sentiment_data = generate_synthetic_data(
    n_stocks=500,
    n_timesteps=1000
)

# Run backtest
system = SentimentArbitrageSystem()
results = system.run_backtest(price_data, sentiment_data)

# Print results
print(f"Total Return: {results['total_return']:.2%}")
print(f"Sharpe Ratio: {results['sharpe_ratio']:.3f}")
print(f"Max Drawdown: {results['max_drawdown']:.2%}")
```

## 🔍 Monitoring

### System Metrics

- Number of signals generated
- Signal execution time
- Portfolio exposure
- Active positions count
- Signal accuracy

### Performance Metrics

- Sharpe ratio
- Maximum drawdown
- Win rate
- Average holding period
- Signal decay rate

## 🐛 Troubleshooting

### Common Issues

**Issue**: Out of memory errors
**Solution**: Reduce batch size or use gradient checkpointing

**Issue**: Low signal accuracy
**Solution**: Adjust sentiment thresholds or retrain sentiment model

**Issue**: High latency
**Solution**: Enable GPU acceleration, optimize batch sizes

## 📝 API Reference

### SentimentArbitrageSystem

```python
class SentimentArbitrageSystem:
    def __init__(config: SystemConfig = None)
    def update(stock_prices, sentiment_texts=None, market_sentiment=None, 
               sector_sentiments=None, timestamp=0) -> Dict
    def run_backtest(price_data, sentiment_data=None, 
                     initial_portfolio_value=1e6) -> Dict
    def get_system_status() -> Dict
```

### SignalGenerator

```python
class SignalGenerator:
    def generate_signals(sentiment_scores, price_z_scores, dislocation,
                         current_prices, confidence_scores=None, 
                         timestamp=0) -> Tuple[List[Signal], List[int]]
    def execute_signal(signal: TradingSignal, portfolio_value: float) -> Tuple[int, float]
    def close_position(stock_id: int, current_price: float) -> Tuple[float, float]
    def get_portfolio_exposure() -> Dict[str, float]
```

## 🤝 Contributing

When contributing to this project:

1. Follow the existing code style
2. Add tests for new features
3. Update documentation
4. Ensure all tests pass
5. Submit pull requests with clear descriptions

## 📄 License

This project is part of the OpenClaw workspace. All rights reserved.

## 📞 Support

For issues or questions:

1. Check the documentation
2. Review test cases for examples
3. Check MEMORY.md for context
4. Contact the main agent

## 🎯 Roadmap

### Phase 1: Core Implementation ✅
- [x] Kalman filter with square-root covariance
- [x] Vectorized z-score calculators
- [x] Echo chamber elimination methods
- [x] Signal generation logic
- [x] Testing framework

### Phase 2: Production Deployment (In Progress)
- [ ] Triton inference server setup
- [ ] Real-time data integration
- [ ] Broker API integration
- [ ] Risk management system
- [ ] Monitoring dashboard

### Phase 3: Optimization
- [ ] Hyperparameter tuning
- [ ] Model retraining pipeline
- [ ] Performance optimization
- [ ] Scaling to 1000+ stocks

### Phase 4: Advanced Features
- [ ] Multi-timeframe analysis
- [ ] Regime detection
- [ ] Ensemble strategies
- [ ] Explainability tools

---

**Author**: Algorithm Designer (Subagent)
**Date**: 2026-03-09
**Version**: 1.0.0
