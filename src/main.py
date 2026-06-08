"""
Futu Trading System - Entry Point

Usage:
    python -m src.main
    set FUTU_CONFIG_PATH=config/config.yaml && python -m src.main
    set FUTU_TRADE_PASSWORD=xxx && python -m src.main
"""

import os
import sys
import time
import threading
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import Config
from src.core.logger import setup_logging
from src.data.store import MarketDataStore
from src.data.collector import MarketDataCollector
from src.strategy.crash_protection import CrashProtection
from src.strategy.spike_detection import SpikeDetection
from src.strategy.ma_crossover import MACrossover
from src.strategy.macd_trend import MACDTrend
from src.strategy.bbands_rsi import BBandsRSI
from src.strategy.kdj_macd import KDJMACD
from src.strategy.adx_macd import ADXMACD
from src.strategy.engine import StrategyEngine
from src.risk.position_tracker import PositionTracker
from src.risk.manager import RiskManager
from src.execution.executor import OrderExecutor
from src.execution.connection import ConnectionManager
from src.notify.notifier import Notifier
from futu import TrdEnv

logger = logging.getLogger(__name__)


def main():
    config = Config.load_from_env()
    setup_logging(config)

    trading_env = config.get("trading.env", "SIMULATE")
    logger.info(f"Trading environment: {trading_env}")
    logger.info(f"OpenD: {config.get('opend.host')}:{config.get('opend.port')}")

    # Initialize components
    store = MarketDataStore(
        max_kline_bars=config.get("data.kline_history_bars", 500),
        max_daily_kline_bars=config.get("data.daily_kline_history_bars", 300),
    )
    collector = MarketDataCollector(config, store)

    strategies = [
        CrashProtection("crash_protection", config.get("crash_protection", {}), store),
        SpikeDetection("spike_detection", config.get("spike_detection", {}), store),
        MACrossover("ma_crossover", config.get("ma_crossover", {}), store),
        MACDTrend("macd_trend", config.get("macd_trend", {}), store),
        BBandsRSI("bbands_rsi", config.get("bbands_rsi", {}), store),
        KDJMACD("kdj_macd", config.get("kdj_macd", {}), store),
        ADXMACD("adx_macd", config.get("adx_macd", {}), store),
    ]

    position_tracker = PositionTracker(store)
    risk_manager = RiskManager(config, position_tracker)
    executor = OrderExecutor(config, store)
    notifier = Notifier(config)

    engine = StrategyEngine(config, store, strategies)
    engine.set_risk_manager(risk_manager)
    engine.set_executor(executor)
    engine.set_notifier(notifier)

    # Log strategy-stock assignments
    strategy_map = config.get("strategy_stock_mapping", {})
    if strategy_map:
        logger.info("Strategy-stock assignments from backtest optimization:")
        for code, strat_name in strategy_map.items():
            logger.info(f"  {code} -> {strat_name}")
    else:
        logger.warning("No strategy_stock_mapping configured - all strategies will run on all stocks")

    conn_manager = ConnectionManager(config, collector, executor)

    try:
        # Start market data collection (requires OpenD running)
        try:
            collector.start()
        except Exception as e:
            logger.error(
                f"Failed to connect to OpenD at "
                f"{config.get('opend.host')}:{config.get('opend.port')}. "
                f"Please ensure OpenD is running. Error: {e}"
            )
            sys.exit(1)

        # Start order executor
        executor.start()

        # Start strategy engine
        engine.start()

        # Start connection monitor
        conn_manager.start_monitoring()

        # Periodic risk checks: update positions and check stop-loss/take-profit
        def risk_check_loop():
            while True:
                try:
                    trd_env = (
                        TrdEnv.REAL
                        if trading_env == "REAL"
                        else TrdEnv.SIMULATE
                    )
                    # Sync positions from API
                    if executor.us_trade_ctx:
                        position_tracker.update_from_api(
                            executor.us_trade_ctx, trd_env
                        )
                    if executor.hk_trade_ctx:
                        position_tracker.update_from_api(
                            executor.hk_trade_ctx, trd_env
                        )
                    # Calculate daily P&L from all positions
                    total_unrealized_pnl_pct = 0.0
                    positions = position_tracker.get_all_positions()
                    total_value = sum(p.market_value for p in positions.values())
                    if total_value > 0:
                        total_unrealized = sum(
                            p.unrealized_pnl for p in positions.values()
                        )
                        total_unrealized_pnl_pct = (
                            total_unrealized / total_value * 100
                        )
                    risk_manager.update_daily_pnl(total_unrealized_pnl_pct)

                    # Check stop-loss / take-profit / trailing stop
                    engine.check_risk_rules()
                except Exception as e:
                    logger.error(f"Risk check error: {e}", exc_info=True)
                time.sleep(30)

        risk_thread = threading.Thread(target=risk_check_loop, daemon=True)
        risk_thread.start()

        watchlist = [
            s["code"] for s in config.get("watchlist", []) if s.get("enabled", True)
        ]
        logger.info(f"Monitoring {len(watchlist)} stocks. Press Ctrl+C to stop.")

        # Status reporting loop
        while True:
            for code in watchlist:
                price = store.get_latest_price(code)
                quote = store.get_latest_quote(code)
                change_rate = quote.get("change_rate", 0)
                if price > 0:
                    logger.info(f"{code}: ${price:.2f} ({change_rate:+.2f}%)")
            time.sleep(60)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        engine.stop()
        collector.stop()
        executor.close()
        logger.info("System stopped")


if __name__ == "__main__":
    main()
