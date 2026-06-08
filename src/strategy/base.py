"""Abstract base class for all trading strategies."""

from abc import ABC, abstractmethod
from datetime import datetime


class BaseStrategy(ABC):
    def __init__(self, name, config, store):
        self.name = name
        self.config = config
        self.store = store
        self.enabled = config.get("enabled", True)
        self.last_trigger_time = {}
        self.use_daily_klines = config.get("use_daily_klines", True)

    @abstractmethod
    def analyze(self, code):
        """Analyze a stock and return a list of Signal objects."""
        pass

    def get_strategy_klines(self, code, num_bars=None):
        """Get K-line data for strategy indicators.

        Indicator-based strategies use daily K-lines (matching backtest calibration).
        Intraday strategies (CrashProtection, SpikeDetection) should call
        self.store.get_klines() directly for minute-level data.
        """
        if self.use_daily_klines:
            return self.store.get_daily_klines(code, num_bars)
        return self.store.get_klines(code, num_bars)

    def is_cooldown_active(self, code, cooldown_sec):
        last = self.last_trigger_time.get(code)
        if last is None:
            return False
        return (datetime.now() - last).total_seconds() < cooldown_sec

    def mark_triggered(self, code):
        self.last_trigger_time[code] = datetime.now()
