"""Thread-safe in-memory market data store."""

import threading
from datetime import datetime, timedelta
from collections import deque


class MarketDataStore:
    def __init__(self, max_kline_bars=500, max_daily_kline_bars=300):
        self._lock = threading.Lock()
        self.quotes = {}       # code -> latest quote dict
        self.klines = {}       # code -> deque of 1-min K-line dicts
        self.daily_klines = {} # code -> deque of daily K-line dicts
        self.tickers = {}      # code -> deque of recent ticks
        self.rt_data = {}      # code -> latest RT data
        self.max_kline_bars = max_kline_bars
        self.max_daily_kline_bars = max_daily_kline_bars

    def update_quote(self, df):
        with self._lock:
            for _, row in df.iterrows():
                code = row["code"]
                self.quotes[code] = row.to_dict()

    def update_kline(self, df):
        with self._lock:
            for _, row in df.iterrows():
                code = row["code"]
                if code not in self.klines:
                    self.klines[code] = deque(maxlen=self.max_kline_bars)
                self.klines[code].append(row.to_dict())

    def update_ticker(self, df):
        with self._lock:
            for _, row in df.iterrows():
                code = row["code"]
                if code not in self.tickers:
                    self.tickers[code] = deque(maxlen=1000)
                entry = row.to_dict()
                entry["_timestamp"] = datetime.now()
                self.tickers[code].append(entry)

    def update_rt_data(self, df):
        with self._lock:
            for _, row in df.iterrows():
                code = row["code"]
                self.rt_data[code] = row.to_dict()

    def get_latest_price(self, code):
        with self._lock:
            q = self.quotes.get(code, {})
            return q.get("last_price", 0.0)

    def get_latest_quote(self, code):
        with self._lock:
            return self.quotes.get(code, {})

    def get_klines(self, code, num_bars=None):
        with self._lock:
            bars = list(self.klines.get(code, []))
            if num_bars:
                return bars[-num_bars:]
            return bars

    def update_daily_kline(self, df):
        with self._lock:
            for _, row in df.iterrows():
                code = row["code"]
                if code not in self.daily_klines:
                    self.daily_klines[code] = deque(maxlen=self.max_daily_kline_bars)
                self.daily_klines[code].append(row.to_dict())

    def get_daily_klines(self, code, num_bars=None):
        with self._lock:
            bars = list(self.daily_klines.get(code, []))
            if num_bars:
                return bars[-num_bars:]
            return bars

    def get_price_history_minutes(self, code, minutes):
        """Get price data within the last N minutes from ticker data.
        Falls back to K-line close prices filtered by time_key."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        with self._lock:
            ticks = list(self.tickers.get(code, []))
            prices = [
                t.get("price", 0)
                for t in ticks
                if t.get("_timestamp", datetime.min) >= cutoff
            ]
            if not prices:
                # Fallback to K-line close prices with time filtering
                klines = list(self.klines.get(code, []))
                for k in klines:
                    time_key = k.get("time_key", "")
                    if time_key:
                        try:
                            # time_key format: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD"
                            kline_time = datetime.strptime(
                                time_key, "%Y-%m-%d %H:%M:%S"
                            )
                            if kline_time >= cutoff:
                                close_price = k.get("close", 0)
                                if close_price > 0:
                                    prices.append(close_price)
                        except ValueError:
                            # Daily K-line or unexpected format - include it
                            close_price = k.get("close", 0)
                            if close_price > 0:
                                prices.append(close_price)
                # If time filtering yielded nothing, use last N bars as last resort
                if not prices and klines:
                    count = min(minutes, len(klines))
                    prices = [k.get("close", 0) for k in klines[-count:] if k.get("close", 0) > 0]
            return prices

    def get_volume_average(self, code, period_minutes):
        """Calculate average volume per K-line bar over recent period.
        Excludes the latest bar to avoid including the current spike."""
        bars = self.get_klines(code)
        if len(bars) < 2:
            return 0.0
        # Exclude the latest (current) bar from average calculation
        historical = bars[:-1][-period_minutes:]
        if not historical:
            return 0.0
        total = sum(b.get("volume", 0) for b in historical)
        return total / len(historical)

    def get_latest_volume(self, code):
        """Get the volume of the most recent K-line bar."""
        bars = self.get_klines(code, 1)
        if bars:
            return bars[0].get("volume", 0)
        return 0
