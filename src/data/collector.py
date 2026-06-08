"""Market data collector: manages subscriptions and historical data warming."""

import logging
from datetime import datetime, timedelta

from futu import (
    OpenQuoteContext,
    SubType,
    KLType,
    AuType,
    KL_FIELD,
    RET_OK,
)

from src.data.handlers import (
    TradingQuoteHandler,
    TradingKlineHandler,
    TradingTickerHandler,
    TradingRTDataHandler,
)

logger = logging.getLogger(__name__)

SUB_TYPE_MAP = {
    "QUOTE": SubType.QUOTE,
    "TICKER": SubType.TICKER,
    "K_1M": SubType.K_1M,
    "K_DAY": SubType.K_DAY,
    "RT_DATA": SubType.RT_DATA,
    "ORDER_BOOK": SubType.ORDER_BOOK,
}


class MarketDataCollector:
    def __init__(self, config, store):
        self.config = config
        self.store = store
        self.quote_ctx = None
        self.is_running = False

    def start(self):
        host = self.config.get("opend.host", "127.0.0.1")
        port = self.config.get("opend.port", 11111)

        logger.info(f"Connecting to OpenD at {host}:{port}")
        self.quote_ctx = OpenQuoteContext(host=host, port=port)

        # Register handlers
        self.quote_ctx.set_handler(TradingQuoteHandler(self.store))
        self.quote_ctx.set_handler(TradingKlineHandler(self.store))
        self.quote_ctx.set_handler(TradingTickerHandler(self.store))
        self.quote_ctx.set_handler(TradingRTDataHandler(self.store))

        # Subscribe to watchlist
        codes = [
            s["code"] for s in self.config.get("watchlist", []) if s.get("enabled", True)
        ]
        sub_types = self._parse_sub_types()

        logger.info(f"Subscribing to {len(codes)} stocks: {codes}")
        ret, data = self.quote_ctx.subscribe(codes, sub_types)
        if ret != RET_OK:
            raise RuntimeError(f"Subscription failed: {data}")
        logger.info("Subscription successful")

        # Fetch historical K-line data to warm up the store
        self._fetch_historical_klines(codes)
        self.is_running = True

    def _parse_sub_types(self):
        raw = self.config.get("data.subscription_types", ["QUOTE"])
        return [SUB_TYPE_MAP[t] for t in raw if t in SUB_TYPE_MAP]

    def _fetch_historical_klines(self, codes):
        bars = self.config.get("data.kline_history_bars", 500)
        # US market: ~390 1-min bars per day (6.5 hours)
        days_back = max(bars // 390 + 10, 30)
        start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        for code in codes:
            try:
                ret, klines, _ = self.quote_ctx.request_history_kline(
                    code=code,
                    start=start,
                    end=None,
                    ktype=KLType.K_1M,
                    autype=AuType.QFQ,
                    fields=[KL_FIELD.ALL],
                    max_count=bars,
                )
                if ret == RET_OK and klines is not None and len(klines) > 0:
                    self.store.update_kline(klines)
                    logger.info(f"Loaded {len(klines)} historical 1-min K-lines for {code}")
                else:
                    logger.warning(f"No 1-min K-line data for {code}")
            except Exception as e:
                logger.error(f"Failed to fetch 1-min history for {code}: {e}")

        # Fetch daily K-lines for strategy indicators
        daily_bars = self.config.get("data.daily_kline_history_bars", 300)
        daily_days_back = max(int(daily_bars * 1.5), 450)
        daily_start = (datetime.now() - timedelta(days=daily_days_back)).strftime("%Y-%m-%d")

        for code in codes:
            try:
                ret, klines, _ = self.quote_ctx.request_history_kline(
                    code=code,
                    start=daily_start,
                    end=None,
                    ktype=KLType.K_DAY,
                    autype=AuType.QFQ,
                    fields=[KL_FIELD.ALL],
                    max_count=daily_bars,
                )
                if ret == RET_OK and klines is not None and len(klines) > 0:
                    self.store.update_daily_kline(klines)
                    logger.info(f"Loaded {len(klines)} historical daily K-lines for {code}")
                else:
                    logger.warning(f"No daily K-line data for {code}")
            except Exception as e:
                logger.error(f"Failed to fetch daily history for {code}: {e}")

    def stop(self):
        if self.quote_ctx:
            self.quote_ctx.close()
            self.quote_ctx = None
        self.is_running = False
        logger.info("Market data collector stopped")

    def reconnect(self):
        logger.info("Reconnecting market data collector...")
        self.stop()
        self.start()
