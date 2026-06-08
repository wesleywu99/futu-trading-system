"""Bollinger Bands + RSI swing breakout strategy.

Buy when price touches/crosses below the lower Bollinger Band AND RSI is oversold.
Sell when price touches/crosses above the upper Bollinger Band AND RSI is overbought.

This is a mean-reversion strategy that aims to buy oversold bounces and sell
overbought reversals, using Bollinger Bands to define the volatility envelope
and RSI to confirm the extreme condition.
"""

import logging
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.events import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class BBandsRSI(BaseStrategy):
    """
    Bollinger Bands + RSI Swing Breakout Strategy.

    Parameters (from config):
        bb_period: SMA period for Bollinger Bands middle band (default 20)
        bb_std_mult: Number of standard deviations for bands (default 2.0)
        rsi_period: RSI calculation period (default 14)
        rsi_oversold: RSI threshold for oversold / sell signal (default 30)
        rsi_buy_max: RSI upper limit for buy signal (default 45, less strict than rsi_oversold)
        rsi_overbought: RSI threshold for overbought / sell signal (default 70)
        cooldown_sec: minimum seconds between signals for same stock
    """

    def analyze(self, code):
        if not self.enabled:
            return []

        bb_period = self.config.get("bb_period", 20)
        bb_std = self.config.get("bb_std_mult", 2.0)
        rsi_period = self.config.get("rsi_period", 14)
        rsi_oversold = self.config.get("rsi_oversold", 30)
        rsi_buy_max = self.config.get("rsi_buy_max", 45)
        rsi_overbought = self.config.get("rsi_overbought", 70)
        cooldown = self.config.get("cooldown_sec", 300)

        required_bars = max(bb_period, rsi_period) + 10
        klines = self.get_strategy_klines(code)
        if len(klines) < required_bars:
            return []

        closes = [k.get("close", 0) for k in klines]

        # Calculate Bollinger Bands
        middle, upper, lower = self._bollinger_bands(closes, bb_period, bb_std)

        # Calculate RSI
        rsi_vals = self._rsi(closes, rsi_period)

        # Need valid values for current bar
        if middle[-1] is None or rsi_vals[-1] is None:
            return []

        # Check cooldown
        if self.is_cooldown_active(code, cooldown):
            return []

        current_price = closes[-1]
        current_rsi = rsi_vals[-1]

        # Buy: price at or below lower band AND RSI below buy max threshold
        if current_price <= lower[-1] and current_rsi < rsi_buy_max:
            self.mark_triggered(code)
            signal = Signal(
                code=code,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"BB+RSI oversold bounce: price {current_price:.2f} <= "
                    f"lower band {lower[-1]:.2f}, RSI {current_rsi:.1f} < {rsi_buy_max}"
                ),
            )
            logger.info(f"BBANDS+RSI BUY: {signal.reason}")
            return [signal]

        # Sell: price at or above upper band AND RSI overbought
        if current_price >= upper[-1] and current_rsi > rsi_overbought:
            self.mark_triggered(code)
            signal = Signal(
                code=code,
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                strategy_name=self.name,
                price=current_price,
                timestamp=datetime.now(),
                reason=(
                    f"BB+RSI overbought reversal: price {current_price:.2f} >= "
                    f"upper band {upper[-1]:.2f}, RSI {current_rsi:.1f} > {rsi_overbought}"
                ),
            )
            logger.info(f"BBANDS+RSI SELL: {signal.reason}")
            return [signal]

        return []

    @staticmethod
    def _bollinger_bands(data, period, std_mult):
        """Calculate Bollinger Bands. Returns (middle, upper, lower) lists."""
        n = len(data)
        middle = [None] * n
        upper = [None] * n
        lower = [None] * n

        for i in range(period - 1, n):
            if data[i] == 0:
                continue
            window = data[i - period + 1: i + 1]
            if any(v == 0 for v in window):
                continue
            avg = sum(window) / period
            variance = sum((v - avg) ** 2 for v in window) / period
            std = variance ** 0.5
            middle[i] = avg
            upper[i] = avg + std_mult * std
            lower[i] = avg - std_mult * std

        return middle, upper, lower

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
                avg_gain = sum(gains[i - period + 1: i + 1]) / period
                avg_loss = sum(losses[i - period + 1: i + 1]) / period
                if avg_loss == 0:
                    result.append(100.0)
                else:
                    rs = avg_gain / avg_loss
                    result.append(100 - 100 / (1 + rs))
        return result
