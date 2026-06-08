"""Backtest engine: bar-by-bar strategy simulation with position tracking."""

import math
from dataclasses import dataclass, field
from datetime import datetime

from src.data.store import MarketDataStore


@dataclass
class Trade:
    """A single round-trip trade."""
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    direction: str  # "LONG"
    pnl: float
    pnl_pct: float
    commission: float
    reason_entry: str
    reason_exit: str


@dataclass
class BacktestResult:
    """Performance metrics from a backtest run."""
    strategy_name: str
    code: str
    initial_cash: float
    final_value: float
    total_return_pct: float
    annual_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    num_trades: int
    win_rate: float
    profit_factor: float
    avg_trade_return_pct: float
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)

    def summary(self):
        """Print a summary of backtest results."""
        print(f"\n{'='*60}")
        print(f"  {self.strategy_name} on {self.code}")
        print(f"{'='*60}")
        print(f"  Initial Cash:    ${self.initial_cash:>12,.2f}")
        print(f"  Final Value:     ${self.final_value:>12,.2f}")
        print(f"  Total Return:    {self.total_return_pct:>11.2f}%")
        print(f"  Annual Return:   {self.annual_return_pct:>11.2f}%")
        print(f"  Max Drawdown:    {self.max_drawdown_pct:>11.2f}%")
        print(f"  Sharpe Ratio:    {self.sharpe_ratio:>11.4f}")
        print(f"  Sortino Ratio:   {self.sortino_ratio:>11.4f}")
        print(f"  Num Trades:      {self.num_trades:>11}")
        print(f"  Win Rate:        {self.win_rate:>11.2f}%")
        print(f"  Profit Factor:   {self.profit_factor:>11.4f}")
        print(f"  Avg Trade Ret:   {self.avg_trade_return_pct:>11.2f}%")
        print(f"{'='*60}")


class BacktestStore(MarketDataStore):
    """Market data store for backtesting that reveals data bar-by-bar."""

    def __init__(self):
        super().__init__(max_kline_bars=10000, max_daily_kline_bars=10000)
        self._all_klines = {}  # code -> list of all kline dicts
        self._current_bar = {}  # code -> current bar index

    def load_data(self, code, klines):
        """Load full historical data for a stock.

        Args:
            code: Stock code (e.g. "AAPL")
            klines: List of dicts with keys: close, high, low, volume, date
        """
        self._all_klines[code] = klines
        self._current_bar[code] = 0
        # Pre-populate klines as empty
        self.klines[code] = []

    def advance_to(self, code, bar_index):
        """Reveal data up to and including bar_index."""
        all_data = self._all_klines.get(code, [])
        if not all_data:
            return
        bar_index = min(bar_index, len(all_data) - 1)
        # Rebuild klines deque up to bar_index
        self.klines[code] = []
        for i in range(bar_index + 1):
            self.klines[code].append(all_data[i])
        self._current_bar[code] = bar_index

    def get_klines(self, code, num_bars=None):
        """Return klines revealed so far."""
        data = list(self.klines.get(code, []))
        if num_bars:
            return data[-num_bars:]
        return data

    def get_latest_price(self, code):
        """Get latest close price from revealed data."""
        bars = list(self.klines.get(code, []))
        if bars:
            return bars[-1].get("close", 0)
        return 0.0

    def get_latest_quote(self, code):
        """Return the latest revealed bar as a quote dict."""
        bars = list(self.klines.get(code, []))
        if bars:
            bar = bars[-1]
            return {
                "code": code,
                "last_price": bar.get("close", 0),
                "high": bar.get("high", 0),
                "low": bar.get("low", 0),
                "volume": bar.get("volume", 0),
            }
        return {}

    def get_price_history_minutes(self, code, minutes):
        """Fallback for strategies that use time-windowed data.

        In backtesting with daily bars, return last N close prices.
        """
        bars = list(self.klines.get(code, []))
        count = min(minutes, len(bars))
        return [b.get("close", 0) for b in bars[-count:] if b.get("close", 0) > 0]

    def get_volume_average(self, code, period_minutes):
        """Return average volume of last N bars (excluding latest)."""
        bars = list(self.klines.get(code, []))
        if len(bars) < 2:
            return 0.0
        historical = bars[:-1][-period_minutes:]
        if not historical:
            return 0.0
        return sum(b.get("volume", 0) for b in historical) / len(historical)

    def get_latest_volume(self, code):
        bars = list(self.klines.get(code, []))
        if bars:
            return bars[-1].get("volume", 0)
        return 0


class BacktestEngine:
    """Run strategy backtests on historical data."""

    def __init__(self, strategy_cls, strategy_config, code,
                 initial_cash=100000, commission=0.001, position_pct=0.2):
        self.strategy_cls = strategy_cls
        self.strategy_config = strategy_config
        self.code = code
        self.initial_cash = initial_cash
        self.commission = commission
        self.position_pct = position_pct

    def run(self, klines):
        """Run backtest and return BacktestResult.

        Args:
            klines: list of dicts with keys: close, high, low, volume, date
        """
        store = BacktestStore()
        store.load_data(self.code, klines)

        # Ensure cooldown is 0 for backtesting
        config = dict(self.strategy_config)
        config["cooldown_sec"] = 0
        config["enabled"] = True

        strategy = self.strategy_cls(
            f"bt_{self.strategy_cls.__name__}", config, store
        )

        cash = self.initial_cash
        position = 0  # number of shares held
        entry_price = 0.0
        entry_date = ""
        reason_entry = ""

        trades = []
        equity_curve = []
        daily_returns = []

        for bar_idx in range(len(klines)):
            # Reveal data up to this bar
            store.advance_to(self.code, bar_idx)
            current_price = klines[bar_idx].get("close", 0)
            if current_price <= 0:
                continue

            # Get strategy signals
            signals = strategy.analyze(self.code)

            # Reset cooldown for next bar
            strategy.last_trigger_time = {}

            # Process signals
            for signal in signals:
                if signal.signal_type.value == "BUY" and position == 0:
                    # Buy: invest position_pct of current cash
                    invest_amount = cash * self.position_pct
                    shares = int(invest_amount / current_price)
                    if shares <= 0:
                        continue
                    cost = shares * current_price
                    comm = cost * self.commission
                    cash -= (cost + comm)
                    position = shares
                    entry_price = current_price
                    entry_date = klines[bar_idx].get("date", str(bar_idx))
                    reason_entry = signal.reason

                elif signal.signal_type.value == "SELL" and position > 0:
                    # Sell all shares at next bar's open (or current close for simplicity)
                    revenue = position * current_price
                    comm = revenue * self.commission
                    cash += (revenue - comm)
                    pnl = revenue - position * entry_price - comm * 2
                    pnl_pct = (current_price - entry_price) / entry_price * 100

                    trades.append(Trade(
                        entry_date=entry_date,
                        exit_date=klines[bar_idx].get("date", str(bar_idx)),
                        entry_price=entry_price,
                        exit_price=current_price,
                        shares=position,
                        direction="LONG",
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        commission=comm * 2,
                        reason_entry=reason_entry,
                        reason_exit=signal.reason,
                    ))
                    position = 0
                    entry_price = 0.0

            # Track equity
            market_value = position * current_price
            total_equity = cash + market_value
            equity_curve.append(total_equity)

            # Daily return
            if len(equity_curve) >= 2:
                daily_ret = equity_curve[-1] / equity_curve[-2] - 1
                daily_returns.append(daily_ret)

        # Calculate metrics
        final_value = equity_curve[-1] if equity_curve else self.initial_cash
        total_return_pct = (final_value - self.initial_cash) / self.initial_cash * 100

        # Annualized return
        num_days = len(equity_curve)
        years = num_days / 252
        if years > 0:
            annual_return_pct = ((final_value / self.initial_cash) ** (1 / years) - 1) * 100
        else:
            annual_return_pct = 0

        # Max drawdown
        peak = self.initial_cash
        max_dd = 0
        for eq in equity_curve:
            peak = max(peak, eq)
            dd = (peak - eq) / peak * 100
            max_dd = max(max_dd, dd)

        # Sharpe and Sortino
        risk_free_rate = 0.02 / 252  # daily risk-free rate
        if daily_returns:
            avg_ret = sum(daily_returns) / len(daily_returns)
            std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in daily_returns) / len(daily_returns))
            sharpe = (avg_ret - risk_free_rate) / std_ret * math.sqrt(252) if std_ret > 0 else 0

            downside = [r for r in daily_returns if r < 0]
            downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(daily_returns)) if downside else 0
            sortino = (avg_ret - risk_free_rate) / downside_std * math.sqrt(252) if downside_std > 0 else 0
        else:
            sharpe = 0
            sortino = 0

        # Win rate and profit factor
        if trades:
            wins = [t for t in trades if t.pnl > 0]
            losses = [t for t in trades if t.pnl <= 0]
            win_rate = len(wins) / len(trades) * 100
            total_profit = sum(t.pnl for t in wins) if wins else 0
            total_loss = abs(sum(t.pnl for t in losses)) if losses else 0
            profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")
            avg_trade_ret = sum(t.pnl_pct for t in trades) / len(trades)
        else:
            win_rate = 0
            profit_factor = 0
            avg_trade_ret = 0

        return BacktestResult(
            strategy_name=self.strategy_cls.__name__,
            code=self.code,
            initial_cash=self.initial_cash,
            final_value=final_value,
            total_return_pct=total_return_pct,
            annual_return_pct=annual_return_pct,
            max_drawdown_pct=max_dd,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            num_trades=len(trades),
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_trade_return_pct=avg_trade_ret,
            trades=trades,
            equity_curve=equity_curve,
        )
