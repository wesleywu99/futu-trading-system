"""KDJ + MACD combo strategy.

Buy signal: MACD histogram crosses from negative to positive (golden cross)
           AND J line is below j_buy_zone (default 50) to avoid chasing highs.
Sell signal: KDJ J/D death cross when J was in overbought zone (>= j_overbought),
             OR J drops below j_sell_threshold.

This combines MACD for timing entries (momentum confirmation) with KDJ for
timing exits (sensitivity to short-term reversals). The KDJ indicator is
more responsive than MACD, making it suitable for exit timing.

KDJ calculation:
  RSV = (Close - LowestLow(9)) / (HighestHigh(9) - LowestLow(9)) * 100
  K = EMA(RSV, 3)
  D = EMA(K, 3)
  J = 3*K - 2*D
"""

import logging
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.events import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class KDJMACD(BaseStrategy):
    """
    KDJ + MACD Combo Strategy.

    Parameters (from config):
        kdj_period: lookback period for highest high / lowest low (default 9)
        kdj_smooth: EMA smoothing period for K and D (default 3)
        macd_fast: MACD fast EMA period (default 12)
        macd_slow: MACD slow EMA period (default 26)
        macd_signal: MACD signal line EMA period (default 9)
        j_buy_zone: buy only when J is below this value (default 50)
        j_overbought: sell on J/D cross only when J was above this (default 80)
        j_sell_threshold: sell when J drops below this value (default 0)
        cooldown_sec: minimum seconds between signals for same stock
    """

    def analyze(self, code):
        if not self.enabled:
            return []

        kdj_period = self.config.get("kdj_period", 9)
        kdj_smooth = self.config.get("kdj_smooth", 3)
        macd_fast = self.config.get("macd_fast", 12)
        macd_slow = self.config.get("macd_slow", 26)
        macd_sig = self.config.get("macd_signal", 9)
        j_threshold = self.config.get("j_sell_threshold", 0)
        j_buy_zone = self.config.get("j_buy_zone", 50)
        j_overbought = self.config.get("j_overbought", 80)
        cooldown = self.config.get("cooldown_sec", 300)

        required_bars = max(macd_slow + macd_sig, kdj_period) + 10
        klines = self.get_strategy_klines(code)
        if len(klines) < required_bars:
            return []

        closes = [k.get("close", 0) for k in klines]
        highs = [k.get("high", 0) for k in klines]
        lows = [k.get("low", 0) for k in klines]

        # Calculate MACD histogram
        fast_ema = self._ema(closes, macd_fast)
        slow_ema = self._ema(closes, macd_slow)
        macd_line = [
            fast_ema[i] - slow_ema[i]
            if fast_ema[i] is not None and slow_ema[i] is not None
            else None
            for i in range(len(closes))
        ]
        signal_line = self._ema(macd_line, macd_sig)
        histogram = [
            macd_line[i] - signal_line[i]
            if macd_line[i] is not None and signal_line[i] is not None
            else None
            for i in range(len(closes))
        ]

        # Calculate KDJ
        k_vals, d_vals, j_vals = self._kdj(highs, lows, closes, kdj_period, kdj_smooth)

        if histogram[-1] is None or histogram[-2] is None:
            return []
        if k_vals[-1] is None or d_vals[-1] is None or j_vals[-1] is None:
            return []
        if k_vals[-2] is None or d_vals[-2] is None or j_vals[-2] is None:
            return []

        # Check cooldown
        if self.is_cooldown_active(code, cooldown):
            return []

        current_price = closes[-1]

        # Buy: MACD histogram crosses from negative to positive AND J not overbought
        if histogram[-2] <= 0 and histogram[-1] > 0:
            if j_vals[-1] < j_buy_zone:
                self.mark_triggered(code)
                signal = Signal(
                    code=code,
                    signal_type=SignalType.BUY,
                    strength=SignalStrength.MODERATE,
                    strategy_name=self.name,
                    price=current_price,
                    timestamp=datetime.now(),
                    reason=(
                        f"KDJ+MACD buy: MACD hist cross {histogram[-2]:.4f} -> "
                        f"{histogram[-1]:.4f}, J={j_vals[-1]:.1f} < {j_buy_zone}"
                    ),
                )
                logger.info(f"KDJ+MACD BUY: {signal.reason}")
                return [signal]

        # Sell: J/D cross below only when J was in overbought zone, OR J extremely low
        j_cross_below = (j_vals[-2] >= d_vals[-2]) and (j_vals[-1] < d_vals[-1])
        j_extreme_low = j_vals[-1] < j_threshold

        if (j_cross_below and j_vals[-2] >= j_overbought) or j_extreme_low:
            self.mark_triggered(code)
            reason_detail = f"J/D cross (J was >={j_overbought})" if j_cross_below else f"J<{j_threshold}"
            signal = Signal(
                code=code,
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"KDJ+MACD sell ({reason_detail}): J={j_vals[-1]:.1f}, "
                    f"D={d_vals[-1]:.1f}, K={k_vals[-1]:.1f}"
                ),
            )
            logger.info(f"KDJ+MACD SELL: {signal.reason}")
            return [signal]

        return []

    @staticmethod
    def _kdj(highs, lows, closes, period=9, smooth=3):
        """Calculate KDJ indicator.

        Returns (K, D, J) lists same length as input.
        K = EMA(RSV, smooth), D = EMA(K, smooth), J = 3*K - 2*D
        """
        n = len(closes)
        rsv = [None] * n

        for i in range(period - 1, n):
            if highs[i] == 0 or lows[i] == 0 or closes[i] == 0:
                continue
            highest = max(highs[i - period + 1: i + 1])
            lowest = min(lows[i - period + 1: i + 1])
            if highest == lowest:
                rsv[i] = 50.0
            else:
                rsv[i] = (closes[i] - lowest) / (highest - lowest) * 100

        # K = EMA of RSV, D = EMA of K
        k_vals = KDJMACD._simple_ema(rsv, smooth)
        d_vals = KDJMACD._simple_ema(k_vals, smooth)

        # J = 3*K - 2*D
        j_vals = []
        for i in range(n):
            if k_vals[i] is not None and d_vals[i] is not None:
                j_vals.append(3 * k_vals[i] - 2 * d_vals[i])
            else:
                j_vals.append(None)

        return k_vals, d_vals, j_vals

    @staticmethod
    def _simple_ema(data, period):
        """Simple EMA for KDJ calculation. Seed with first valid value average."""
        result = [None] * len(data)
        mult = 2.0 / (period + 1)

        # Find first window of `period` consecutive valid values
        start = None
        for i in range(len(data)):
            if data[i] is not None:
                # Check if we have `period` consecutive valid from i-period+1 to i
                if i >= period - 1:
                    window = data[i - period + 1: i + 1]
                    if all(v is not None for v in window):
                        start = i - period + 1
                        break

        if start is None:
            return result

        # Seed EMA with SMA of first window
        window_vals = [data[start + j] for j in range(period)]
        ema_val = sum(window_vals) / period
        result[start + period - 1] = ema_val

        # Continue EMA
        for i in range(start + period, len(data)):
            if data[i] is None:
                continue
            ema_val = (data[i] - ema_val) * mult + ema_val
            result[i] = ema_val

        return result

    @staticmethod
    def _ema(data, period):
        """EMA reusing the same implementation as MACDTrend."""
        result = []
        multiplier = 2.0 / (period + 1)

        start_idx = None
        for i in range(len(data)):
            val = data[i]
            if val is None or (isinstance(val, (int, float)) and val == 0):
                result.append(None)
                continue
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

        while len(result) < start_idx:
            result.append(None)

        first_sum = 0.0
        for i in range(start_idx, start_idx + period):
            first_sum += data[i]
        ema_val = first_sum / period
        result.append(ema_val)

        for i in range(start_idx + period, len(data)):
            val = data[i]
            if val is None or (isinstance(val, (int, float)) and val == 0):
                result.append(None)
                continue
            ema_val = (val - ema_val) * multiplier + ema_val
            result.append(ema_val)

        return result
