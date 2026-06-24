"""Combined strategy: wraps multiple sub-strategies and merges signals.

Three combination modes:

1. ``voting`` — all sub-strategies must agree on the same direction for a
   signal to fire.  Useful for reducing false positives (e.g. ADX_MACD AND
   MACD_Trend both bullish -> buy).

2. ``entry_exit`` — sub-strategy A supplies BUY signals, sub-strategy B
   supplies SELL signals.  Lets you pair a trend-following entry with a
   mean-reversion exit.

3. ``sequential`` — sub-strategy A controls entry until the first trade is
   in profit, after which sub-strategy B controls exit.  Lets you catch the
   start of a move with one strategy, then bank profit with another.

The class is a ``BaseStrategy`` subclass so it plugs into the existing
backtest engine and live strategy engine without any further plumbing.
"""

import logging
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.events import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class CombinedStrategy(BaseStrategy):
    """Wrap a list of sub-strategies and merge their signals by mode.

    Args:
        name: strategy name (used in Signal.strategy_name).
        config: config dict (passed to BaseStrategy; ``enabled`` honored).
        store: MarketDataStore shared with every sub-strategy.
        sub_strategies: list of BaseStrategy instances. Ordering matters for
            ``entry_exit`` and ``sequential`` modes (A before B).
        mode: one of ``"voting"``, ``entry_exit``, ``sequential``.
        min_profit_pct: (``sequential`` only) unrealized profit % above which
            control flips from entry strategy to exit strategy. Default 2.0.
        label: optional human-readable description used in Signal.reason.
    """

    VOTING = "voting"
    ENTRY_EXIT = "entry_exit"
    SEQUENTIAL = "sequential"

    def __init__(self, name, config, store, sub_strategies, mode,
                 min_profit_pct=2.0, label=None):
        # Bypass our property setter during BaseStrategy.__init__
        super().__init__(name, config, store)
        if not sub_strategies:
            raise ValueError("CombinedStrategy requires at least one sub-strategy")
        self.sub_strategies = list(sub_strategies)
        self.mode = mode
        self.min_profit_pct = min_profit_pct
        self.label = label or name

        # State for sequential mode (entry price of the open position)
        self._entry_price = None

        # Point every sub-strategy at the same store we were given
        self.sync_store(store)

    # ------------------------------------------------------------------
    # Store propagation
    # ------------------------------------------------------------------
    # We override the ``store`` attribute lookup so that any rebinding
    # (e.g. BacktestEngine doing ``strategy.store = new_store``) propagates
    # to every sub-strategy.  Using ``__setattr__`` keeps the base class's
    # simple ``self.store = ...`` semantics intact while adding sync.
    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        if key == "store" and hasattr(self, "sub_strategies"):
            # Keep sub-strategies in sync with our store
            for s in self.sub_strategies:
                if s.store is not value:
                    s.store = value

    def sync_store(self, store):
        """Explicitly rebind every sub-strategy's store to ``store``."""
        self.store = store
        for s in getattr(self, "sub_strategies", []):
            s.store = store

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _reset_sub_cooldowns(self):
        """Clear cooldown state on every sub-strategy (backtest has no time)."""
        for s in self.sub_strategies:
            s.last_trigger_time = {}

    def _collect(self, code):
        """Run every sub-strategy and bucket signals by direction."""
        self._reset_sub_cooldowns()
        buys, sells = [], []
        for s in self.sub_strategies:
            try:
                signals = s.analyze(code) or []
            except Exception as e:
                logger.warning(f"Sub-strategy {s.name} raised: {e}")
                signals = []
            for sig in signals:
                if sig.signal_type == SignalType.BUY:
                    buys.append((s, sig))
                elif sig.signal_type == SignalType.SELL:
                    sells.append((s, sig))
        return buys, sells

    @staticmethod
    def _pick_strongest(signals):
        """Return the strongest signal from a list of (strategy, signal)."""
        rank = {
            SignalStrength.STRONG: 3,
            SignalStrength.MODERATE: 2,
            SignalStrength.WEAK: 1,
        }
        return max(signals, key=lambda pair: rank.get(pair[1].strength, 0))[1]

    # ------------------------------------------------------------------
    # analyze
    # ------------------------------------------------------------------
    def analyze(self, code):
        if not self.enabled:
            return []

        if self.mode == self.VOTING:
            return self._analyze_voting(code)
        if self.mode == self.ENTRY_EXIT:
            return self._analyze_entry_exit(code)
        if self.mode == self.SEQUENTIAL:
            return self._analyze_sequential(code)
        raise ValueError(f"Unknown mode: {self.mode}")

    # ------------------------------------------------------------------
    # Mode 1: voting
    # ------------------------------------------------------------------
    def _analyze_voting(self, code):
        """All sub-strategies must agree on the same direction."""
        n = len(self.sub_strategies)
        buys, sells = self._collect(code)

        if len(buys) >= n:
            sig = self._pick_strongest(buys)
            return [self._merge_signal(sig, SignalType.BUY, code,
                                       f"{self.label}: {len(buys)}/{n} agree BUY")]
        if len(sells) >= n:
            sig = self._pick_strongest(sells)
            return [self._merge_signal(sig, SignalType.SELL, code,
                                       f"{self.label}: {len(sells)}/{n} agree SELL")]
        return []

    # ------------------------------------------------------------------
    # Mode 2: entry/exit split
    # ------------------------------------------------------------------
    def _analyze_entry_exit(self, code):
        """Sub-strategy[0] -> BUY, sub-strategy[1] -> SELL."""
        entry_strat = self.sub_strategies[0]
        exit_strat = self.sub_strategies[1]

        self._reset_sub_cooldowns()

        # Entry signal
        try:
            entry_sigs = [s for s in (entry_strat.analyze(code) or [])
                          if s.signal_type == SignalType.BUY]
        except Exception:
            entry_sigs = []
        if entry_sigs:
            sig = entry_sigs[0]
            return [self._merge_signal(sig, SignalType.BUY, code,
                                       f"{self.label}: entry@{entry_strat.name}")]

        # Exit signal
        try:
            exit_sigs = [s for s in (exit_strat.analyze(code) or [])
                         if s.signal_type == SignalType.SELL]
        except Exception:
            exit_sigs = []
        if exit_sigs:
            sig = exit_sigs[0]
            return [self._merge_signal(sig, SignalType.SELL, code,
                                       f"{self.label}: exit@{exit_strat.name}")]
        return []

    # ------------------------------------------------------------------
    # Mode 3: sequential (entry strategy until profit, then exit strategy)
    # ------------------------------------------------------------------
    def _analyze_sequential(self, code):
        """A controls entry; once in profit, B controls exit."""
        entry_strat = self.sub_strategies[0]
        exit_strat = self.sub_strategies[1]

        self._reset_sub_cooldowns()

        current_price = self.store.get_latest_price(code) or 0.0

        # If we have an open position above the profit threshold, let exit_strat decide
        if self._entry_price and current_price > 0:
            profit_pct = (current_price - self._entry_price) / self._entry_price * 100
            if profit_pct >= self.min_profit_pct:
                try:
                    exit_sigs = [s for s in (exit_strat.analyze(code) or [])
                                 if s.signal_type == SignalType.SELL]
                except Exception:
                    exit_sigs = []
                if exit_sigs:
                    sig = exit_sigs[0]
                    self._entry_price = None
                    return [self._merge_signal(sig, SignalType.SELL, code,
                                               f"{self.label}: sequential exit@{exit_strat.name} "
                                               f"(profit {profit_pct:.1f}%)")]
                return []

        # Otherwise let entry strategy produce a BUY
        try:
            entry_sigs = [s for s in (entry_strat.analyze(code) or [])
                          if s.signal_type == SignalType.BUY]
        except Exception:
            entry_sigs = []
        if entry_sigs:
            sig = entry_sigs[0]
            self._entry_price = current_price
            return [self._merge_signal(sig, SignalType.BUY, code,
                                       f"{self.label}: sequential entry@{entry_strat.name}")]
        return []

    # ------------------------------------------------------------------
    # Signal construction
    # ------------------------------------------------------------------
    def _merge_signal(self, template, signal_type, code, reason):
        """Build a new Signal that reports this combined strategy as its source."""
        return Signal(
            code=code,
            signal_type=signal_type,
            strength=template.strength,
            strategy_name=self.name,
            price=template.price,
            timestamp=datetime.now(),
            reason=reason,
            suggested_qty=template.suggested_qty,
        )

    # ------------------------------------------------------------------
    # State hooks
    # ------------------------------------------------------------------
    def reset_position_state(self):
        """Clear internal position tracking (used by backtest between runs)."""
        self._entry_price = None
