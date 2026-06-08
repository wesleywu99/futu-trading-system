"""ADX + MACD trend strategy.

Buy signal: EMA triple alignment (short > mid > long) AND ADX is rising but
below threshold (trend is strengthening but not yet overbought) AND MACD
histogram is rising (momentum increasing).

This strategy aims to catch trends early, before they become obvious.
The ADX filter ensures we only trade when a trend is forming, while the
EMA alignment confirms the direction.

ADX calculation (standard 14-period):
  +DM = High - PrevHigh (if > 0 and > -DM)
  -DM = PrevLow - Low (if > 0 and > +DM)
  Smooth +DM, -DM, TR over 14 periods
  +DI = 100 * smoothed(+DM) / smoothed(TR)
  -DI = 100 * smoothed(-DM) / smoothed(TR)
  DX = 100 * |+DI - -DI| / (+DI + -DI)
  ADX = smoothed average of DX
"""

import logging
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.events import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class ADXMACD(BaseStrategy):
    """
    ADX + MACD Trend Strategy.

    Parameters (from config):
        ema_short: short EMA period (default 13)
        ema_mid: middle EMA period (default 55)
        ema_long: long EMA period (default 89)
        adx_period: ADX calculation period (default 14)
        adx_threshold: ADX must be below this to buy (default 25)
        adx_rising_bars: ADX must rise for N consecutive bars to buy (default 1)
        macd_fast: MACD fast EMA period (default 12)
        macd_slow: MACD slow EMA period (default 26)
        macd_signal: MACD signal line period (default 9)
        cooldown_sec: minimum seconds between signals for same stock
    """

    def analyze(self, code):
        if not self.enabled:
            return []

        ema_short = self.config.get("ema_short", 13)
        ema_mid = self.config.get("ema_mid", 55)
        ema_long = self.config.get("ema_long", 89)
        adx_period = self.config.get("adx_period", 14)
        adx_threshold = self.config.get("adx_threshold", 25)
        adx_rising_bars = self.config.get("adx_rising_bars", 1)
        macd_fast = self.config.get("macd_fast", 12)
        macd_slow = self.config.get("macd_slow", 26)
        macd_sig = self.config.get("macd_signal", 9)
        cooldown = self.config.get("cooldown_sec", 300)

        # ADX needs 2*period + 1 bars minimum, EMA89 needs ~100 bars
        required_bars = max(ema_long + 20, 2 * adx_period + 50)
        klines = self.get_strategy_klines(code)
        if len(klines) < required_bars:
            return []

        closes = [k.get("close", 0) for k in klines]
        highs = [k.get("high", 0) for k in klines]
        lows = [k.get("low", 0) for k in klines]

        # Calculate EMA triple alignment
        ema_s = self._ema(closes, ema_short)
        ema_m = self._ema(closes, ema_mid)
        ema_l = self._ema(closes, ema_long)

        # Calculate ADX
        adx_vals = self._adx(highs, lows, closes, adx_period)

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

        # Validate all indicators at current and previous bar
        lookback = max(2, adx_rising_bars + 1)
        for idx in range(-1, -lookback - 1, -1):
            if any(
                v[idx] is None
                for v in [ema_s, ema_m, ema_l, adx_vals, histogram]
            ):
                return []

        if self.is_cooldown_active(code, cooldown):
            return []

        current_price = closes[-1]

        # BUY conditions (all must be true):
        # 1. EMA alignment: short > mid > long (bullish trend)
        # 2. ADX rising AND below threshold (trend forming, not yet overbought)
        # 3. MACD histogram rising (momentum increasing)
        ema_aligned = ema_s[-1] > ema_m[-1] > ema_l[-1]
        # ADX must be rising for N consecutive bars
        adx_rising = all(
            adx_vals[-i] > adx_vals[-i - 1]
            for i in range(1, adx_rising_bars + 1)
        )
        adx_not_overbought = adx_vals[-1] <= adx_threshold
        macd_rising = histogram[-1] > histogram[-2]

        if ema_aligned and adx_rising and adx_not_overbought and macd_rising:
            self.mark_triggered(code)
            signal = Signal(
                code=code,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"ADX+MACD buy: EMA aligned ({ema_s[-1]:.2f}>{ema_m[-1]:.2f}"
                    f">{ema_l[-1]:.2f}), ADX {adx_vals[-2]:.1f}->{adx_vals[-1]:.1f}"
                    f" (<{adx_threshold}), MACD hist rising"
                ),
            )
            logger.info(f"ADX+MACD BUY: {signal.reason}")
            return [signal]

        # SELL: EMA alignment broken (short < mid or mid < long)
        # OR ADX very high and declining (trend exhaustion)
        ema_bearish = ema_s[-1] < ema_m[-1]
        adx_exhaustion = adx_vals[-1] > 40 and adx_vals[-1] < adx_vals[-2]

        if ema_bearish or adx_exhaustion:
            self.mark_triggered(code)
            reason_detail = "EMA bearish" if ema_bearish else "ADX exhaustion"
            signal = Signal(
                code=code,
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"ADX+MACD sell ({reason_detail}): ADX={adx_vals[-1]:.1f}, "
                    f"EMA{ema_short}={ema_s[-1]:.2f}, EMA{ema_mid}={ema_m[-1]:.2f}"
                ),
            )
            logger.info(f"ADX+MACD SELL: {signal.reason}")
            return [signal]

        return []

    @staticmethod
    def _adx(highs, lows, closes, period=14):
        """Calculate ADX (Average Directional Index).

        Standard Wilder smoothing method.
        """
        n = len(closes)
        if n < 2 * period + 1:
            return [None] * n

        # Calculate True Range, +DM, -DM
        tr_list = []
        plus_dm = []
        minus_dm = []

        for i in range(n):
            if i == 0 or highs[i] == 0 or lows[i] == 0 or closes[i] == 0:
                tr_list.append(None)
                plus_dm.append(None)
                minus_dm.append(None)
                continue

            # True Range
            h_minus_l = highs[i] - lows[i]
            h_minus_pc = abs(highs[i] - closes[i - 1])
            l_minus_pc = abs(lows[i] - closes[i - 1])
            tr_list.append(max(h_minus_l, h_minus_pc, l_minus_pc))

            # +DM and -DM
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]

            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0)

            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0)

        # Wilder smoothing over `period` bars
        # First smoothed values = sum of first `period` valid values
        def wilder_smooth(data, start_offset, period):
            result = [None] * len(data)
            # Find first valid index
            first_valid = None
            for j in range(len(data)):
                if data[j] is not None:
                    first_valid = j
                    break
            if first_valid is None:
                return result

            # Accumulate first `period` valid values
            valid_vals = []
            idx = first_valid
            while idx < len(data) and len(valid_vals) < period:
                if data[idx] is not None:
                    valid_vals.append(data[idx])
                idx += 1

            if len(valid_vals) < period:
                return result

            smoothed = sum(valid_vals)
            result[idx - 1] = smoothed

            # Continue with Wilder smoothing: prev - prev/period + current
            for j in range(idx, len(data)):
                if data[j] is None:
                    continue
                smoothed = smoothed - smoothed / period + data[j]
                result[j] = smoothed

            return result

        smooth_tr = wilder_smooth(tr_list, 0, period)
        smooth_plus_dm = wilder_smooth(plus_dm, 0, period)
        smooth_minus_dm = wilder_smooth(minus_dm, 0, period)

        # +DI, -DI, DX
        dx = [None] * n
        for i in range(n):
            if smooth_tr[i] is not None and smooth_tr[i] > 0:
                pdi = 100 * (smooth_plus_dm[i] or 0) / smooth_tr[i]
                mdi = 100 * (smooth_minus_dm[i] or 0) / smooth_tr[i]
                di_sum = pdi + mdi
                if di_sum > 0:
                    dx[i] = 100 * abs(pdi - mdi) / di_sum

        # ADX = smoothed average of DX
        adx_result = [None] * n

        # Find first window of `period` consecutive valid DX values
        first_dx = None
        for i in range(n):
            if dx[i] is not None:
                if i >= period - 1:
                    window = dx[i - period + 1: i + 1]
                    if all(v is not None for v in window):
                        first_dx = i - period + 1
                        break

        if first_dx is None:
            return adx_result

        # Seed ADX with average of first period DX values
        seed_vals = dx[first_dx: first_dx + period]
        adx_val = sum(seed_vals) / period
        adx_result[first_dx + period - 1] = adx_val

        # Continue smoothing
        for i in range(first_dx + period, n):
            if dx[i] is None:
                continue
            adx_val = (adx_val * (period - 1) + dx[i]) / period
            adx_result[i] = adx_val

        return adx_result

    @staticmethod
    def _ema(data, period):
        """EMA calculation."""
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
                if data[j] is not None and not (
                    isinstance(data[j], (int, float)) and data[j] == 0
                ):
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
