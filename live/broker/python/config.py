"""
Configuration for Broker Integration System
"""
import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class BrokerConfig:
    """Broker configuration"""
    broker_type: str = os.getenv("BROKER_TYPE", "futu")  # 'futu', 'mock', etc.
    host: str = os.getenv("FUTU_HOST", "127.0.0.1")
    port: int = int(os.getenv("FUTU_PORT", "11111"))
    paper_trading: bool = os.getenv("PAPER_TRADING", "true").lower() == "true"
    env_type: str = "SIMULATE" if os.getenv("PAPER_TRADING", "true").lower() == "true" else "REAL"


@dataclass
class RiskConfig:
    """Risk control configuration"""
    max_position_size: int = int(os.getenv("MAX_POSITION_SIZE", "10000"))
    max_total_position_value: float = float(os.getenv("MAX_TOTAL_POSITION_VALUE", "1000000"))
    max_positions: int = int(os.getenv("MAX_POSITIONS", "10"))
    max_daily_loss: float = float(os.getenv("MAX_DAILY_LOSS", "5000"))
    stop_loss_percent: float = float(os.getenv("STOP_LOSS_PERCENT", "5.0"))


@dataclass
class OrderConfig:
    """Order configuration"""
    default_order_type: str = os.getenv("DEFAULT_ORDER_TYPE", "limit")
    slippage_tolerance: float = float(os.getenv("SLIPPAGE_TOLERANCE", "0.01"))
    order_timeout_seconds: int = int(os.getenv("ORDER_TIMEOUT_SECONDS", "300"))


@dataclass
class LoggingConfig:
    """Logging configuration"""
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "broker.log")
    log_to_console: bool = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"


class Config:
    """Main configuration class"""
    broker: BrokerConfig = BrokerConfig()
    risk: RiskConfig = RiskConfig()
    order: OrderConfig = OrderConfig()
    logging: LoggingConfig = LoggingConfig()

    @classmethod
    def load_from_env(cls):
        """Load configuration from environment variables"""
        cls.broker = BrokerConfig()
        cls.risk = RiskConfig()
        cls.order = OrderConfig()
        cls.logging = LoggingConfig()
        return cls

    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        if cls.broker.broker_type not in ["futu", "mock"]:
            raise ValueError(f"Invalid broker type: {cls.broker.broker_type}")

        if cls.broker.port < 1 or cls.broker.port > 65535:
            raise ValueError(f"Invalid port: {cls.broker.port}")

        if cls.risk.max_position_size <= 0:
            raise ValueError(f"Invalid max position size: {cls.risk.max_position_size}")

        if cls.risk.stop_loss_percent <= 0:
            raise ValueError(f"Invalid stop loss percent: {cls.risk.stop_loss_percent}")

        return True


# Global configuration instance
config = Config.load_from_env()
