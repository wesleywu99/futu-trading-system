"""Spike detection strategy: buy on volume + price breakout."""

import logging
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.events import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class SpikeDetection(BaseStrategy):
    """
    Detects breakout opportunities based on:
    1. Volume spike: current 1-min volume > avg_volume * multiplier
    2. Price breakout: price up > threshold% within time window

    Both conditions must be true simultaneously.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.daily_trade_count = {}
        self.daily_reset_date = None

    def analyze(self, code):
        if not self.enabled:
            return []

        self._check_daily_reset()

        max_daily = self.config.get("max_daily_trades", 5)
        if self.daily_trade_count.get(code, 0) >= max_daily:
            return []

        cooldown = self.config.get("cooldown_sec", 600)
        if self.is_cooldown_active(code, cooldown):
            return []

        # Volume check
        vol_multiplier = self.config.get("volume_multiplier", 3.0)
        vol_period = self.config.get("volume_avg_period_min", 30)
        klines = self.store.get_klines(code)
        if len(klines) < vol_period:
            return []

        recent_volumes = [k.get("volume", 0) for k in klines[-vol_period:]]
        avg_volume = sum(recent_volumes) / len(recent_volumes)
        current_volume = self.store.get_latest_volume(code)

        if avg_volume <= 0 or current_volume < avg_volume * vol_multiplier:
            return []

        # Price breakout check
        price_threshold = self.config.get("price_breakout_pct", 2.0)
        price_window = self.config.get("price_time_window_min", 10)
        prices = self.store.get_price_history_minutes(code, price_window)

        if len(prices) < 2:
            return []

        price_change_pct = (prices[-1] - prices[0]) / prices[0] * 100
        if price_change_pct < price_threshold:
            return []

        # Both conditions met
        self.mark_triggered(code)
        self.daily_trade_count[code] = self.daily_trade_count.get(code, 0) + 1

        signal = Signal(
            code=code,
            signal_type=SignalType.BUY,
            strength=SignalStrength.MODERATE,
            strategy_name=self.name,
            price=prices[-1],
            timestamp=datetime.now(),
            reason=(
                f"Spike: vol {current_volume / avg_volume:.1f}x avg, "
                f"price +{price_change_pct:.1f}% in {price_window}min"
            ),
            suggested_qty=self.config.get("max_buy_qty", 100),
        )
        logger.info(f"SPIKE BUY SIGNAL: {signal.reason}")
        return [signal]

    def _check_daily_reset(self):
        today = datetime.now().date().isoformat()
        if self.daily_reset_date != today:
            self.daily_trade_count = {}
            self.daily_reset_date = today
