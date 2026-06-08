"""Strategy engine: orchestrates all strategies in a polling loop."""

import threading
import time
import logging

from src.core.events import SignalType

logger = logging.getLogger(__name__)


class StrategyEngine:
    def __init__(self, config, store, strategies):
        self.config = config
        self.store = store
        self.strategies = strategies
        self.risk_manager = None
        self.executor = None
        self.notifier = None
        self.running = False

    def set_risk_manager(self, manager):
        self.risk_manager = manager

    def set_executor(self, executor):
        self.executor = executor

    def set_notifier(self, notifier):
        self.notifier = notifier

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()
        logger.info("Strategy engine started")

    def _check_loop(self):
        while self.running:
            try:
                watchlist = self.config.get("watchlist", [])
                strategy_map = self.config.get("strategy_stock_mapping", {})

                for stock in watchlist:
                    if not stock.get("enabled", True):
                        continue
                    code = stock["code"]

                    for strategy in self.strategies:
                        # Always-run safety strategies
                        if strategy.name in ("crash_protection", "spike_detection"):
                            signals = strategy.analyze(code)
                            for signal in signals:
                                self._process_signal(signal)
                            continue

                        # Indicator strategies: only run if assigned to this stock
                        assigned_strategy = strategy_map.get(code)
                        if assigned_strategy and strategy.name == assigned_strategy:
                            signals = strategy.analyze(code)
                            for signal in signals:
                                self._process_signal(signal)
            except Exception as e:
                logger.error(f"Strategy engine error: {e}", exc_info=True)

            interval = self.config.get("strategy.check_interval_sec", 5)
            time.sleep(interval)

    def _process_signal(self, signal):
        signal_type_str = (
            signal.signal_type.value
            if hasattr(signal.signal_type, "value")
            else str(signal.signal_type)
        )
        logger.info(
            f"Signal: {signal_type_str} {signal.code} "
            f"from {signal.strategy_name} - {signal.reason}"
        )

        # Risk validation
        if self.risk_manager:
            approval = self.risk_manager.validate_signal(signal)
            if not approval.approved:
                logger.info(f"Signal rejected by risk: {approval.reason}")
                return
            signal.suggested_qty = approval.adjusted_qty

        # Notify before execution
        if self.notifier:
            self.notifier.send(
                f"{signal_type_str}_SIGNAL",
                f"{signal.reason} | qty={signal.suggested_qty}",
            )

        # Execute order
        if self.executor:
            self.executor.execute(signal)

    def check_risk_rules(self):
        """Periodic check: stop-loss, take-profit, trailing stop."""
        if not self.risk_manager:
            return
        signals = self.risk_manager.check_stop_loss_take_profit()
        for signal in signals:
            self._process_signal(signal)

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Strategy engine stopped")
