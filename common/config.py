"""
Configuration Classes for Trading System

Centralized configuration management for all components.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from pathlib import Path
import json


@dataclass
class RouterConfig:
    """Configuration for signal routing and aggregation"""

    # Strategy weights
    sentiment_arb_weight: float = 0.6
    strategy_weight: float = 0.4

    # Signal filtering
    min_conviction: float = 0.3
    min_strength: float = 30.0  # Minimum signal strength (0-100)
    require_agreement: bool = False  # Both strategies must agree

    # Risk limits
    max_position_pct: float = 0.05  # Max 5% per position
    max_sector_exposure: float = 0.25  # Max 25% per sector
    max_total_exposure: float = 1.0  # Max 100% total exposure
    max_long_short_ratio: float = 2.0  # Max long/short ratio

    # Position sizing
    position_sizing_method: str = "signal_strength"  # "signal_strength", "equal", "risk_parity"
    base_position_size: float = 0.02  # Base position size as fraction

    # Execution
    max_signals_per_run: int = 50  # Maximum signals per execution
    signal_cooldown_minutes: int = 60  # Cooldown between signals for same symbol


@dataclass
class BacktestConfig:
    """Configuration for backtesting"""

    # Capital
    initial_capital: float = 1000000.0  # ¥1,000,000
    benchmark: str = "csi300"  # Benchmark for comparison

    # Costs
    commission_rate: float = 0.0003  # 0.03% commission
    min_commission: float = 5.0  # ¥5 minimum commission
    slippage_rate: float = 0.001  # 0.1% slippage
    stamp_duty: float = 0.001  # 0.1% stamp duty (China A-shares, sell only)

    # Execution
    fill_model: str = "next_open"  # "next_open", "close", "vwap"
    partial_fills: bool = False

    # Data
    price_field: str = "adj_close"  # "close", "adj_close"
    handle_missing_data: str = "skip"  # "skip", "fill", "error"

    # Risk
    max_position_pct: float = 0.10  # Max 10% per position in backtest
    max_drawdown_stop: Optional[float] = 0.20  # Stop backtest at 20% drawdown

    # Output
    save_trades: bool = True
    save_equity_curve: bool = True
    save_signals: bool = True
    output_dir: str = "backtest_results"


@dataclass
class DataConfig:
    """Configuration for data provider"""

    # Database
    db_path: str = "data/stocks.duckdb"
    db_type: str = "duckdb"  # "duckdb", "parquet", "sqlite"

    # Cache
    enable_cache: bool = True
    cache_dir: str = "data/cache"
    cache_expiry_hours: int = 24

    # Data sources
    price_source: str = "baostock"  # "baostock", "akshare", "tushare"
    sentiment_source: str = "local"  # "local", "api"
    fundamentals_source: str = "baostock"

    # Universe
    default_universe: str = "csi300"
    universe_update_freq: str = "monthly"


@dataclass
class ExecutionConfig:
    """Configuration for execution/broker"""

    # Broker
    broker_type: str = "mock"  # "mock", "futu", "xtp"
    paper_trading: bool = True

    # Connection
    host: str = "127.0.0.1"
    port: int = 11111

    # Risk limits
    max_position_size: float = 0.05  # Max 5% per position
    max_daily_loss: float = 0.02  # Max 2% daily loss
    max_daily_trades: int = 50
    stop_loss_pct: float = 0.08  # 8% stop loss
    take_profit_pct: float = 0.15  # 15% take profit

    # Order settings
    default_order_type: str = "MARKET"  # "MARKET", "LIMIT"
    limit_order_timeout_seconds: int = 60
    allow_partial_fills: bool = True


@dataclass
class StrategyConfig:
    """Base configuration for strategies"""

    # Identification
    name: str = "base_strategy"
    version: str = "1.0.0"

    # Signal generation
    signal_frequency: str = "daily"  # "tick", "1m", "5m", "hourly", "daily"
    lookback_days: int = 252  # ~1 year of trading days

    # Risk
    max_positions: int = 20
    max_sector_concentration: float = 0.30

    # State
    persist_state: bool = True
    state_dir: str = "state"


@dataclass
class SentimentArbConfig(StrategyConfig):
    """Configuration for sentiment arbitrage strategy"""

    name: str = "sentiment_arbitrage"

    # Kalman filter
    kalman_process_noise: float = 0.01
    kalman_measurement_noise: float = 0.1
    kalman_initial_variance: float = 1.0

    # Z-scoring
    z_score_window: int = 20
    z_score_method: str = "rolling"  # "rolling", "expanding", "ewma"

    # Signal thresholds
    long_sentiment_threshold: float = 1.5
    long_price_threshold: float = -0.5
    long_dislocation_threshold: float = 2.0
    short_sentiment_threshold: float = -1.5
    short_price_threshold: float = 0.5
    short_dislocation_threshold: float = -2.0

    # Exit conditions
    exit_z_cross: bool = True
    exit_time_stop_hours: int = 48
    exit_stop_loss_pct: float = 0.15
    exit_take_profit_pct: float = 0.20

    # GPU
    use_gpu: bool = True
    gpu_device: int = 0


@dataclass
class ContrarianConfig(StrategyConfig):
    """Configuration for contrarian fundamental strategy"""

    name: str = "contrarian_strategy"

    # Sentiment thresholds
    sentiment_threshold: float = 1.5
    roc_threshold: float = 1.0
    min_deviation_std: float = 1.5

    # Valuation thresholds
    undervalued_threshold: float = 0.10
    overvalued_threshold: float = -0.10

    # Confirmation
    confirmation_periods: int = 2

    # Exit conditions
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.15
    sentiment_reversal_threshold: float = 1.0
    valuation_reversal_threshold: float = 0.05

    # Position sizing
    base_position_size: float = 0.01
    max_position_size: float = 0.05

    # Weights
    sentiment_weight: float = 0.5
    valuation_weight: float = 0.5


@dataclass
class SystemConfig:
    """Top-level system configuration"""

    # Environment
    environment: str = "development"  # "development", "staging", "production"

    # Logging
    log_level: str = "INFO"
    log_dir: str = "logs"

    # Component configs
    data: DataConfig = field(default_factory=DataConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)

    # Strategies
    sentiment_arb: SentimentArbConfig = field(default_factory=SentimentArbConfig)
    contrarian: ContrarianConfig = field(default_factory=ContrarianConfig)

    @classmethod
    def from_file(cls, path: str) -> "SystemConfig":
        """Load configuration from JSON file"""
        with open(path, "r") as f:
            data = json.load(f)

        return cls(
            environment=data.get("environment", "development"),
            log_level=data.get("log_level", "INFO"),
            log_dir=data.get("log_dir", "logs"),
            data=DataConfig(**data.get("data", {})),
            router=RouterConfig(**data.get("router", {})),
            backtest=BacktestConfig(**data.get("backtest", {})),
            execution=ExecutionConfig(**data.get("execution", {})),
            sentiment_arb=SentimentArbConfig(**data.get("sentiment_arb", {})),
            contrarian=ContrarianConfig(**data.get("contrarian", {})),
        )

    def to_file(self, path: str) -> None:
        """Save configuration to JSON file"""
        data = {
            "environment": self.environment,
            "log_level": self.log_level,
            "log_dir": self.log_dir,
            "data": {
                "db_path": self.data.db_path,
                "db_type": self.data.db_type,
                "enable_cache": self.data.enable_cache,
                "cache_dir": self.data.cache_dir,
                "cache_expiry_hours": self.data.cache_expiry_hours,
                "price_source": self.data.price_source,
                "sentiment_source": self.data.sentiment_source,
                "fundamentals_source": self.data.fundamentals_source,
                "default_universe": self.data.default_universe,
            },
            "router": {
                "sentiment_arb_weight": self.router.sentiment_arb_weight,
                "strategy_weight": self.router.strategy_weight,
                "min_conviction": self.router.min_conviction,
                "min_strength": self.router.min_strength,
                "max_position_pct": self.router.max_position_pct,
                "max_sector_exposure": self.router.max_sector_exposure,
            },
            "backtest": {
                "initial_capital": self.backtest.initial_capital,
                "commission_rate": self.backtest.commission_rate,
                "slippage_rate": self.backtest.slippage_rate,
                "stamp_duty": self.backtest.stamp_duty,
            },
            "execution": {
                "broker_type": self.execution.broker_type,
                "paper_trading": self.execution.paper_trading,
                "max_position_size": self.execution.max_position_size,
                "max_daily_loss": self.execution.max_daily_loss,
            },
            "sentiment_arb": {
                "kalman_process_noise": self.sentiment_arb.kalman_process_noise,
                "z_score_window": self.sentiment_arb.z_score_window,
                "long_sentiment_threshold": self.sentiment_arb.long_sentiment_threshold,
            },
            "contrarian": {
                "sentiment_threshold": self.contrarian.sentiment_threshold,
                "undervalued_threshold": self.contrarian.undervalued_threshold,
                "stop_loss_pct": self.contrarian.stop_loss_pct,
            },
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
