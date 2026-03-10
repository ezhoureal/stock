"""
Data Providers Module

Provides data access implementations for the trading system.
"""

from .duckdb_provider import DuckDBDataProvider

__all__ = ["DuckDBDataProvider"]
