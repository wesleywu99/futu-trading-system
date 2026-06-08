"""MACD trend following strategy with EMA filter.

Buy when MACD histogram turns positive AND price is above EMA trend line.
Sell when MACD histogram turns negative AND price is below EMA trend line.

This is a classic trend-following approach that aims to capture medium-term
momentum moves while filtering out false signals in sideways markets.
"""

import logging
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.events import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class MACDTrend(BaseStrategy):
    """
    MACD + EMA Trend Following Strategy.

    Parameters (from config):
        fast_period: EMA fast period for MACD (default 12)
        slow_period: EMA slow period for MACD (default 26)
        signal_period: EMA signal line period (default 9)
        trend_ema_period: EMA period for trend filter (default 20)
        cooldown_sec: minimum seconds between signals for same stock
    """

    def analyze(self, code):
        if not self.enabled:
            return []

        fast_p = self.config.get("fast_period", 12)
        slow_p = self.config.get("slow_period", 26)
        signal_p = self.config.get("signal_period", 9)
        trend_p = self.config.get("trend_ema_period", 20)
        cooldown = self.config.get("cooldown_sec", 300)

        required_bars = slow_p + signal_p + 10
        klines = self.get_strategy_klines(code)
        if len(klines) < required_bars:
            return []

        closes = [k.get("close", 0) for k in klines]

        # Calculate indicators
        fast_ema = self._ema(closes, fast_p)
        slow_ema = self._ema(closes, slow_p)

        # MACD line = fast EMA - slow EMA
        macd_line = []
        for i in range(len(closes)):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                macd_line.append(fast_ema[i] - slow_ema[i])
            else:
                macd_line.append(None)

        # Signal line = EMA of MACD line
        signal_line = self._ema(macd_line, signal_p)

        # Histogram = MACD - Signal
        histogram = []
        for i in range(len(closes)):
            if macd_line[i] is not None and signal_line[i] is not None:
                histogram.append(macd_line[i] - signal_line[i])
            else:
                histogram.append(None)

        # Trend filter: EMA of close prices
        trend_ema = self._ema(closes, trend_p)

        # Need at least 2 valid histogram values and current trend value
        if histogram[-1] is None or histogram[-2] is None:
            return []
        if trend_ema[-1] is None:
            return []

        # Check cooldown
        if self.is_cooldown_active(code, cooldown):
            return []

        current_price = closes[-1]
        above_trend = current_price > trend_ema[-1]

        # Buy signal: histogram crosses from negative to positive + above trend
        if histogram[-2] <= 0 and histogram[-1] > 0 and above_trend:
            self.mark_triggered(code)
            signal = Signal(
                code=code,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"MACD bullish cross: histogram {histogram[-2]:.4f} -> "
                    f"{histogram[-1]:.4f}, price {current_price:.2f} > "
                    f"EMA{trend_p} {trend_ema[-1]:.2f}"
                ),
            )
            logger.info(f"MACD TREND BUY: {signal.reason}")
            return [signal]

        # Sell signal: histogram crosses from positive to negative + below trend
        if histogram[-2] >= 0 and histogram[-1] < 0 and not above_trend:
            self.mark_triggered(code)
            signal = Signal(
                code=code,
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"MACD bearish cross: histogram {histogram[-2]:.4f} -> "
                    f"{histogram[-1]:.4f}, price {current_price:.2f} < "
                    f"EMA{trend_p} {trend_ema[-1]:.2f}"
                ),
            )
            logger.info(f"MACD TREND SELL: {signal.reason}")
            return [signal]

        return []

    @staticmethod
    def _ema(data, period):
        """Exponential Moving Average. Returns list same length as data."""
        result = []
        multiplier = 2.0 / (period + 1)

        # Find the first valid index with enough preceding data
        start_idx = None
        for i in range(len(data)):
            val = data[i]
            if val is None or (isinstance(val, (int, float)) and val == 0):
                result.append(None)
                continue
            # Count consecutive valid values
            valid_count = 0
            for j in range(i, -1, -1):
                if data[j] is not None and not (isinstance(data[j], (int, float)) and data[j] == 0):
                    valid_count += 1
                else:
                    break
                if valid_count == period:
                    start_idx = j
                    break
            if start_idx is not None:
                break
            result.append(None)

        if start_idx is None:
            return [None] * len(data)

        # Fill None until start_idx
        while len(result) < start_idx:
            result.append(None)

        # First EMA value = SMA of first 'period' valid values
        first_sum = 0.0
        for i in range(start_idx, start_idx + period):
            first_sum += data[i]
        ema_val = first_sum / period
        result.append(ema_val)

        # Continue calculating EMA
        for i in range(start_idx + period, len(data)):
            val = data[i]
            if val is None or (isinstance(val, (int, float)) and val == 0):
                result.append(None)
                continue
            ema_val = (val - ema_val) * multiplier + ema_val
            result.append(ema_val)

        return result
