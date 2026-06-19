"""GOOGL multi-strategy comparison backtest (3-Year AI Era).

Usage:
    python tools/googl_backtest.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yfinance as yf
from src.backtest.engine import BacktestEngine

from src.strategy.ma_crossover import MACrossover
from src.strategy.macd_trend import MACDTrend
from src.strategy.bbands_rsi import BBandsRSI
from src.strategy.kdj_macd import KDJMACD
from src.strategy.adx_macd import ADXMACD

TICKER = "GOOGL"
START_3Y = "2023-06-01"
END_DATE = "2026-06-07"
POSITION_SIZES = [0.5]

ALL_STRATEGIES = {
    "BBands_RSI": (BBandsRSI, {
        "bb_period": 20, "bb_std_mult": 2.0,
        "rsi_period": 14, "rsi_oversold": 30, "rsi_buy_max": 45,
        "rsi_overbought": 70,
    }),
    "MACD_Trend": (MACDTrend, {
        "fast_period": 12, "slow_period": 26, "signal_period": 9,
        "trend_ema_period": 30,
    }),
    "MA_Crossover": (MACrossover, {
        "short_period": 5, "long_period": 20,
        "rsi_filter": {"enabled": True, "period": 14, "mode": "level", "upper_limit": 60},
    }),
    "ADX_MACD": (ADXMACD, {
        "ema_short": 13, "ema_mid": 55, "ema_long": 89,
        "adx_period": 14, "adx_threshold": 30, "adx_rising_bars": 2,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    }),
    "KDJ_MACD": (KDJMACD, {
        "kdj_period": 9,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "j_buy_threshold": 20, "j_sell_threshold": 80,
    }),
}


def download_data(ticker, start, end):
    print(f"  Downloading {ticker} from {start}...")
    df = yf.download(ticker, start=start, end=end, auto_adjust=True)
    if df.empty:
        print(f"  WARNING: No data for {ticker}")
        return []
    klines = []
    for idx, row in df.iterrows():
        close_val = row["Close"]
        high_val = row["High"]
        low_val = row["Low"]
        vol_val = row["Volume"]
        if hasattr(close_val, "item"):
            close_val = close_val.item()
            high_val = high_val.item()
            low_val = low_val.item()
            vol_val = vol_val.item()
        klines.append({
            "date": idx.strftime("%Y-%m-%d"),
            "close": float(close_val),
            "high": float(high_val),
            "low": float(low_val),
            "volume": int(vol_val),
        })
    return klines


def main():
    print("=" * 100)
    print(f"  {TICKER} MULTI-STRATEGY BACKTEST (3-Year AI Era)")
    print("=" * 100)

    klines = download_data(TICKER, START_3Y, END_DATE)
    if not klines:
        print("ERROR: No data downloaded.")
        return

    print(f"\n  {len(klines)} bars, {klines[0]['date']} to {klines[-1]['date']}")
    print(f"\n  {'Strategy':<14} {'Return%':>10} {'Annual%':>10} {'MaxDD%':>9} "
          f"{'Sharpe':>9} {'Sortino':>9} {'Trades':>7} {'WinRate%':>9} {'PF':>7} {'AvgRet%':>9}")
    print(f"  {'-'*105}")

    results = {}
    ranking = []

    for strat_name, (strat_cls, config) in ALL_STRATEGIES.items():
        engine = BacktestEngine(
            strategy_cls=strat_cls,
            strategy_config=config,
            code=TICKER,
            initial_cash=100000,
            commission=0.001,
            position_pct=0.5,
        )
        result = engine.run(klines)
        results[strat_name] = result
        ranking.append((result.sharpe_ratio, strat_name))

    ranking.sort(key=lambda x: x[0], reverse=True)

    for sharpe, strat_name in ranking:
        r = results[strat_name]
        pf = r.profit_factor if r.profit_factor != float("inf") else 999
        print(
            f"  {strat_name:<14} "
            f"{r.total_return_pct:>9.2f}% "
            f"{r.annual_return_pct:>9.2f}% "
            f"{r.max_drawdown_pct:>8.2f}% "
            f"{r.sharpe_ratio:>9.4f} "
            f"{r.sortino_ratio:>9.4f} "
            f"{r.num_trades:>7} "
            f"{r.win_rate:>8.2f}% "
            f"{pf:>7.2f} "
            f"{r.avg_trade_return_pct:>8.2f}%"
        )

    # Show trades for each strategy
    for sharpe, strat_name in ranking:
        r = results[strat_name]
        if r.num_trades == 0:
            print(f"\n  {strat_name}: No trades generated.")
            continue
        print(f"\n  {strat_name} trades ({r.num_trades} total, showing last 10):")
        recent = r.trades[-10:]
        for t in recent:
            pnl_str = f"+{t.pnl:.2f}" if t.pnl > 0 else f"{t.pnl:.2f}"
            print(f"    {t.entry_date} -> {t.exit_date} | "
                  f"{t.entry_price:.2f} -> {t.exit_price:.2f} | "
                  f"P&L: {pnl_str} ({t.pnl_pct:+.2f}%)")
        # Win/loss breakdown
        wins = [t for t in r.trades if t.pnl > 0]
        losses = [t for t in r.trades if t.pnl <= 0]
        print(f"    Wins: {len(wins)} | Losses: {len(losses)} | "
              f"Avg win: {sum(t.pnl_pct for t in wins)/len(wins):.2f}%" if wins else "", end="")
        if losses:
            print(f" | Avg loss: {sum(t.pnl_pct for t in losses)/len(losses):.2f}%")
        else:
            print()

    # Buy & Hold comparison
    bh_return = (klines[-1]["close"] - klines[0]["close"]) / klines[0]["close"] * 100
    print(f"\n  Buy & Hold: {bh_return:.2f}%")
    print(f"  Best strategy: {ranking[0][1]} (Sharpe={ranking[0][0]:.4f})")


if __name__ == "__main__":
    main()
