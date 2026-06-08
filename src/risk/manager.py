"""Risk manager: validates signals and enforces risk rules."""

import logging
from datetime import datetime

from src.core.events import Signal, SignalType, SignalStrength, RiskApproval, Position

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, config, position_tracker):
        self.config = config
        self.position_tracker = position_tracker
        self.daily_pnl = 0.0
        self.daily_pnl_date = None
        self._reset_daily_pnl()

    def _reset_daily_pnl(self):
        today = datetime.now().date().isoformat()
        if self.daily_pnl_date != today:
            self.daily_pnl = 0.0
            self.daily_pnl_date = today

    def update_daily_pnl(self, pnl_pct):
        """Update daily P&L percentage. Called periodically from main loop."""
        self._reset_daily_pnl()
        self.daily_pnl = pnl_pct

    def validate_signal(self, signal):
        """Validate a trading signal against all risk rules."""
        self._reset_daily_pnl()

        # Daily loss limit
        daily_limit = self.config.get("risk.daily_loss_limit_pct", 5.0)
        if self.daily_pnl < -daily_limit:
            return RiskApproval(False, f"Daily loss limit exceeded: {self.daily_pnl:.1f}%")

        # BUY checks
        if signal.signal_type == SignalType.BUY:
            return self._validate_buy(signal)

        # SELL checks
        if signal.signal_type == SignalType.SELL:
            return self._validate_sell(signal)

        return RiskApproval(False, "HOLD not actionable")

    def _validate_buy(self, signal):
        max_positions = self.config.get("risk.max_positions", 5)
        if self.position_tracker.num_positions() >= max_positions:
            return RiskApproval(False, f"Max positions reached ({max_positions})")

        pos = self.position_tracker.get_position(signal.code)
        if pos and pos.qty > 0:
            return RiskApproval(False, f"Already holding {signal.code}")

        qty = signal.suggested_qty if signal.suggested_qty > 0 else 100
        return RiskApproval(True, "Approved", adjusted_qty=qty)

    def _validate_sell(self, signal):
        pos = self.position_tracker.get_position(signal.code)
        if not pos or pos.qty <= 0:
            return RiskApproval(False, f"No position in {signal.code}")
        return RiskApproval(True, "Approved", adjusted_qty=pos.qty)

    def check_stop_loss_take_profit(self):
        """Check all positions for stop-loss and take-profit conditions."""
        signals = []
        positions = self.position_tracker.get_all_positions()

        for code, pos in positions.items():
            # Stop-loss
            sl_pct = self.config.get("risk.stop_loss.default_pct", 8.0)
            if pos.unrealized_pnl_pct <= -sl_pct:
                signals.append(Signal(
                    code=code,
                    signal_type=SignalType.SELL,
                    strength=SignalStrength.STRONG,
                    strategy_name="stop_loss",
                    price=pos.current_price,
                    timestamp=datetime.now(),
                    reason=f"Stop-loss: {code} P&L={pos.unrealized_pnl_pct:.1f}%",
                ))
                continue

            # Trailing stop
            trailing_cfg = self.config.get("risk.stop_loss.trailing", {})
            if trailing_cfg.get("enabled") and pos.unrealized_pnl_pct > 0:
                activation = trailing_cfg.get("activation_pct", 3.0)
                trail_pct = trailing_cfg.get("trailing_pct", 5.0)
                if pos.unrealized_pnl_pct >= activation:
                    trail_stop = pos.highest_price_since_buy * (1 - trail_pct / 100)
                    if pos.current_price <= trail_stop:
                        signals.append(Signal(
                            code=code,
                            signal_type=SignalType.SELL,
                            strength=SignalStrength.STRONG,
                            strategy_name="trailing_stop",
                            price=pos.current_price,
                            timestamp=datetime.now(),
                            reason=(
                                f"Trailing stop: {code} price {pos.current_price:.2f} "
                                f"below {trail_stop:.2f}"
                            ),
                        ))

            # Take-profit
            tp_pct = self.config.get("risk.take_profit.default_pct", 15.0)
            if pos.unrealized_pnl_pct >= tp_pct:
                signals.append(Signal(
                    code=code,
                    signal_type=SignalType.SELL,
                    strength=SignalStrength.MODERATE,
                    strategy_name="take_profit",
                    price=pos.current_price,
                    timestamp=datetime.now(),
                    reason=f"Take-profit: {code} P&L=+{pos.unrealized_pnl_pct:.1f}%",
                ))

        return signals
