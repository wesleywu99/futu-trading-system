"""Crash protection strategy: auto-sell when price drops sharply."""

import logging
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.events import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class CrashProtection(BaseStrategy):
    """
    Monitors price drop percentage within a rolling time window.
    If price drops more than threshold% within time_window minutes,
    issues a STRONG SELL signal.

    Algorithm:
    1. Get price history for the last time_window minutes
    2. Find the highest price in that window
    3. drop_pct = (highest - current) / highest * 100
    4. If drop_pct >= threshold, emit SELL signal
    """

    def analyze(self, code):
        if not self.enabled:
            return []

        threshold = self.config.get("drop_threshold_pct", 5.0)
        window = self.config.get("time_window_min", 15)
        cooldown = self.config.get("cooldown_sec", 300)

        if self.is_cooldown_active(code, cooldown):
            return []

        prices = self.store.get_price_history_minutes(code, window)
        if len(prices) < 2:
            return []

        current_price = prices[-1]
        if current_price <= 0:
            return []

        highest_price = max(prices)
        drop_pct = (highest_price - current_price) / highest_price * 100

        if drop_pct >= threshold:
            self.mark_triggered(code)
            signal = Signal(
                code=code,
                signal_type=SignalType.SELL,
                strength=SignalStrength.STRONG,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"Crash: price dropped {drop_pct:.1f}% in {window}min "
                    f"(high={highest_price:.2f}, now={current_price:.2f})"
                ),
            )
            logger.warning(f"CRASH SIGNAL: {signal.reason}")
            return [signal]

        return []
