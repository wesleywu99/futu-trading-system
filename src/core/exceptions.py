"""Custom exceptions for the trading system."""


class ConfigError(Exception):
    """Configuration validation error."""
    pass


class ConnectionError(Exception):
    """OpenD connection error."""
    pass


class OrderError(Exception):
    """Order placement/modification error."""
    pass


class RiskLimitError(Exception):
    """Risk limit exceeded error."""
    pass
