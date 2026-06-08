"""Moving average crossover strategy with optional RSI filter."""

import logging
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.events import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class MACrossover(BaseStrategy):
    """
    Moving Average Crossover strategy with optional RSI filter.

    Algorithm:
    1. Get K-line close prices
    2. Calculate short SMA and long SMA
    3. Buy signal: short MA crosses above long MA
       (previous: short <= long; current: short > long)
    4. Sell signal: short MA crosses below long MA
       (previous: short >= long; current: short < long)
    5. Optional RSI filter:
       - mode="level" (default): RSI must be below upper_limit to buy
       - mode="cross": RSI must cross from below oversold to above it
    """

    def analyze(self, code):
        if not self.enabled:
            return []

        short_period = self.config.get("short_period", 5)
        long_period = self.config.get("long_period", 20)
        required_bars = long_period + 10

        klines = self.get_strategy_klines(code)
        if len(klines) < required_bars:
            return []

        closes = [k.get("close", 0) for k in klines]

        short_ma = self._sma(closes, short_period)
        long_ma = self._sma(closes, long_period)

        # Need valid values for current and previous bar
        if short_ma[-2] is None or long_ma[-2] is None:
            return []
        if short_ma[-1] is None or long_ma[-1] is None:
            return []

        # Optional RSI filter
        rsi_cfg = self.config.get("rsi_filter", {})
        rsi_vals = None
        if rsi_cfg.get("enabled", False):
            rsi_vals = self._rsi(closes, rsi_cfg.get("period", 14))
            if len(rsi_vals) < 2 or rsi_vals[-2] is None or rsi_vals[-1] is None:
                return []

        current_price = closes[-1]

        # Buy: short MA crosses above long MA
        if short_ma[-2] <= long_ma[-2] and short_ma[-1] > long_ma[-1]:
            if rsi_vals is not None:
                mode = rsi_cfg.get("mode", "level")
                if mode == "level":
                    upper_limit = rsi_cfg.get("upper_limit", 60)
                    if rsi_vals[-1] >= upper_limit:
                        return []
                else:  # "cross" mode (original behavior)
                    oversold = rsi_cfg.get("oversold", 30)
                    if not (rsi_vals[-2] < oversold <= rsi_vals[-1]):
                        return []

            signal = Signal(
                code=code,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"MA cross up: MA{short_period} ({short_ma[-1]:.2f}) "
                    f"above MA{long_period} ({long_ma[-1]:.2f})"
                ),
            )
            logger.info(f"MA CROSSOVER BUY: {signal.reason}")
            return [signal]

        # Sell: short MA crosses below long MA
        if short_ma[-2] >= long_ma[-2] and short_ma[-1] < long_ma[-1]:
            signal = Signal(
                code=code,
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"MA cross down: MA{short_period} ({short_ma[-1]:.2f}) "
                    f"below MA{long_period} ({long_ma[-1]:.2f})"
                ),
            )
            logger.info(f"MA CROSSOVER SELL: {signal.reason}")
            return [signal]

        return []

    @staticmethod
    def _sma(data, period):
        result = []
        for i in range(len(data)):
            if i < period - 1 or data[i] == 0:
                result.append(None)
            else:
                window = data[i - period + 1 : i + 1]
                if any(v == 0 for v in window):
                    result.append(None)
                else:
                    result.append(sum(window) / period)
        return result

    @staticmethod
    def _rsi(data, period=14):
        """Standard RSI formula. Returns list same length as data."""
        if len(data) < period + 1:
            return [None] * len(data)

        deltas = [data[i] - data[i - 1] for i in range(1, len(data))]
        gains, losses = [], []
        for d in deltas:
            if d > 0:
                gains.append(d)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(d))

        result = [None]
        for i in range(len(gains)):
            if i < period:
                result.append(None)
            else:
                avg_gain = sum(gains[i - period + 1 : i + 1]) / period
                avg_loss = sum(losses[i - period + 1 : i + 1]) / period
                if avg_loss == 0:
                    result.append(100.0)
                else:
                    rs = avg_gain / avg_loss
                    result.append(100 - 100 / (1 + rs))
        return result
