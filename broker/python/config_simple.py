"""
Simple Configuration for Broker Integration System (without dotenv)
"""
from typing import Optional
from dataclasses import dataclass


@dataclass
class BrokerConfig:
    """Broker configuration"""
    broker_type: str = "mock"  # Default to mock for testing
    host: str = "127.0.0.1"
    port: int = 11111
    paper_trading: bool = True


@dataclass
class RiskConfig:
    """Risk control configuration"""
    max_position_size: int = 10000
    max_total_position_value: float = 1000000.0
    max_positions: int = 10
    max_daily_loss: float = 5000.0
    stop_loss_percent: float = 5.0


@dataclass
class OrderConfig:
    """Order configuration"""
    default_order_type: str = "limit"
    slippage_tolerance: float = 0.01
    order_timeout_seconds: int = 300


@dataclass
class LoggingConfig:
    """Logging configuration"""
    log_level: str = "INFO"
    log_file: str = "broker.log"
    log_to_console: bool = True


class Config:
    """Main configuration class"""
    broker: BrokerConfig = BrokerConfig()
    risk: RiskConfig = RiskConfig()
    order: OrderConfig = OrderConfig()
    logging: LoggingConfig = LoggingConfig()

    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        if cls.broker.broker_type not in ["futu", "mock"]:
            raise ValueError(f"Invalid broker type: {cls.broker.broker_type}")
        return True


# Global configuration instance
config = Config()
