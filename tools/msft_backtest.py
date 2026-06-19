"""MSFT multi-strategy comparison backtest.

Tests all 5 strategies against Microsoft stock to find the optimal strategy.

Usage:
    python tools/msft_backtest.py
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

TICKER = "MSFT"
START_3Y = "2023-06-01"
START_10Y = "2016-01-01"
START_25Y = "2001-01-01"
END_DATE = "2026-06-07"
POSITION_SIZES = [0.2, 0.5, 0.8]

# All strategies with default (optimized) parameters
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


def run_comparison(klines, label):
    print(f"\n{'='*100}")
    print(f"  MSFT Strategy Comparison — {label} ({len(klines)} bars, {klines[0]['date']} to {klines[-1]['date']})")
    print(f"{'='*100}")

    results = {}

    for strat_name, (strat_cls, config) in ALL_STRATEGIES.items():
        for pos_pct in POSITION_SIZES:
            engine = BacktestEngine(
                strategy_cls=strat_cls,
                strategy_config=config,
                code=TICKER,
                initial_cash=100000,
                commission=0.001,
                position_pct=pos_pct,
            )
            result = engine.run(klines)
            results[(strat_name, pos_pct)] = result

    # Print results table sorted by Sharpe (pos=50%)
    print(f"\n  {'Strategy':<14} {'Pos':>4} {'Return%':>10} {'Annual%':>10} {'MaxDD%':>9} "
          f"{'Sharpe':>9} {'Sortino':>9} {'Trades':>7} {'WinRate%':>9} {'PF':>7} {'AvgRet%':>9}")
    print(f"  {'-'*100}")

    # Sort by Sharpe ratio at pos=50%
    ranking = []
    for strat_name in ALL_STRATEGIES:
        r50 = results[(strat_name, 0.5)]
        ranking.append((r50.sharpe_ratio, strat_name))
    ranking.sort(key=lambda x: x[0], reverse=True)

    for _, strat_name in ranking:
        for pos_pct in POSITION_SIZES:
            r = results[(strat_name, pos_pct)]
            pf = r.profit_factor if r.profit_factor != float("inf") else 999
            marker = " <<<" if pos_pct == 0.5 else ""
            print(
                f"  {strat_name:<14} {pos_pct*100:>3.0f}% "
                f"{r.total_return_pct:>9.2f}% "
                f"{r.annual_return_pct:>9.2f}% "
                f"{r.max_drawdown_pct:>8.2f}% "
                f"{r.sharpe_ratio:>9.4f} "
                f"{r.sortino_ratio:>9.4f} "
                f"{r.num_trades:>7} "
                f"{r.win_rate:>8.2f}% "
                f"{pf:>7.2f} "
                f"{r.avg_trade_return_pct:>8.2f}%"
                f"{marker}"
            )

    # Best strategy
    best_sharpe, best_name = ranking[0]
    best_r = results[(best_name, 0.5)]
    print(f"\n  BEST STRATEGY: {best_name}")
    print(f"    Sharpe: {best_r.sharpe_ratio:.4f} | Return: {best_r.total_return_pct:.2f}% | "
          f"MaxDD: {best_r.max_drawdown_pct:.2f}% | Trades: {best_r.num_trades} | WinRate: {best_r.win_rate:.1f}%")

    # Show recent trades for the best strategy
    print(f"\n  Recent trades ({best_name}, pos=50%):")
    recent = results[(best_name, 0.5)].trades[-10:]
    for t in recent:
        pnl_str = f"+{t.pnl:.2f}" if t.pnl > 0 else f"{t.pnl:.2f}"
        print(f"    {t.entry_date} -> {t.exit_date} | {t.entry_price:.2f} -> {t.exit_price:.2f} | "
              f"P&L: {pnl_str} ({t.pnl_pct:+.2f}%) | {t.shares} shares")

    return results, ranking


def main():
    print("=" * 100)
    print("  MSFT MULTI-STRATEGY BACKTEST COMPARISON")
    print("=" * 100)

    # 3-year backtest (AI era)
    klines_3y = download_data(TICKER, START_3Y, END_DATE)
    results_3y, ranking_3y = None, None
    if klines_3y:
        results_3y, ranking_3y = run_comparison(klines_3y, "3-Year (AI Era)")

    # 10-year backtest
    klines_10y = download_data(TICKER, START_10Y, END_DATE)
    results_10y, ranking_10y = None, None
    if klines_10y:
        results_10y, ranking_10y = run_comparison(klines_10y, "10-Year")

    # 25-year backtest
    klines_25y = download_data(TICKER, START_25Y, END_DATE)
    results_25y, ranking_25y = None, None
    if klines_25y:
        results_25y, ranking_25y = run_comparison(klines_25y, "25-Year (Max)")

    # Final recommendation
    print(f"\n{'='*100}")
    print("  FINAL RECOMMENDATION FOR MSFT")
    print(f"{'='*100}")

    if ranking_3y:
        best_3 = ranking_3y[0][1]
        r3 = results_3y[(best_3, 0.5)]
        print(f"\n  3-Year (AI Era) Best: {best_3} (Sharpe={r3.sharpe_ratio:.4f})")

    if ranking_10y:
        best_10 = ranking_10y[0][1]
        r10 = results_10y[(best_10, 0.5)]
        print(f"  10-Year Best: {best_10} (Sharpe={r10.sharpe_ratio:.4f})")

    if ranking_25y:
        best_25 = ranking_25y[0][1]
        r25 = results_25y[(best_25, 0.5)]
        print(f"  25-Year Best: {best_25} (Sharpe={r25.sharpe_ratio:.4f})")

    # Show top 3 for 3-year
    if ranking_3y:
        print(f"\n  Top 3 Strategies (3-Year AI Era):")
        for i, (sharpe, name) in enumerate(ranking_3y[:3]):
            r = results_3y[(name, 0.5)]
            print(f"    {i+1}. {name}: Sharpe={sharpe:.4f}, Return={r.total_return_pct:.2f}%, MaxDD={r.max_drawdown_pct:.2f}%, Trades={r.num_trades}, WinRate={r.win_rate:.1f}%")

    if ranking_10y:
        print(f"\n  Top 3 Strategies (10-Year):")
        for i, (sharpe, name) in enumerate(ranking_10y[:3]):
            r = results_10y[(name, 0.5)]
            print(f"    {i+1}. {name}: Sharpe={sharpe:.4f}, Return={r.total_return_pct:.2f}%, MaxDD={r.max_drawdown_pct:.2f}%")

    if ranking_25y:
        print(f"\n  Top 3 Strategies (25-Year):")
        for i, (sharpe, name) in enumerate(ranking_25y[:3]):
            r = results_25y[(name, 0.5)]
            print(f"    {i+1}. {name}: Sharpe={sharpe:.4f}, Return={r.total_return_pct:.2f}%, MaxDD={r.max_drawdown_pct:.2f}%")

    # Recommendation
    if ranking_3y:
        best_3_name = ranking_3y[0][1]
        best_3_sharpe = ranking_3y[0][0]
        print(f"\n  >>> RECOMMENDED FOR AI ERA: {best_3_name} (3-Year Sharpe={best_3_sharpe:.4f})")


if __name__ == "__main__":
    main()
