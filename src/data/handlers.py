"""Futu SDK callback handlers for real-time market data."""

from futu import (
    StockQuoteHandlerBase,
    CurKlineHandlerBase,
    TickerHandlerBase,
    RTDataHandlerBase,
    RET_OK,
)


class TradingQuoteHandler(StockQuoteHandlerBase):
    """Handles real-time quote pushes from OpenD."""

    def __init__(self, store):
        self.store = store

    def on_recv_rsp(self, rsp_pb):
        ret_code, content = super().on_recv_rsp(rsp_pb)
        if ret_code == RET_OK:
            self.store.update_quote(content)
        return ret_code, content


class TradingKlineHandler(CurKlineHandlerBase):
    """Handles K-line (candlestick) pushes from OpenD.

    Routes daily K-lines (K_DAY) to store.update_daily_kline()
    and intraday K-lines (K_1M etc.) to store.update_kline()
    based on the time_key format.
    """

    def __init__(self, store):
        self.store = store

    def on_recv_rsp(self, rsp_pb):
        ret_code, content = super().on_recv_rsp(rsp_pb)
        if ret_code == RET_OK and content is not None and not content.empty:
            # K_DAY time_key: "YYYY-MM-DD" (no space)
            # K_1M time_key: "YYYY-MM-DD HH:MM:SS" (has space)
            time_key = str(content.iloc[0].get("time_key", ""))
            if " " not in time_key:
                self.store.update_daily_kline(content)
            else:
                self.store.update_kline(content)
        return ret_code, content


class TradingTickerHandler(TickerHandlerBase):
    """Handles tick-by-tick trade data."""

    def __init__(self, store):
        self.store = store

    def on_recv_rsp(self, rsp_pb):
        ret_code, content = super().on_recv_rsp(rsp_pb)
        if ret_code == RET_OK:
            self.store.update_ticker(content)
        return ret_code, content


class TradingRTDataHandler(RTDataHandlerBase):
    """Handles real-time intraday data."""

    def __init__(self, store):
        self.store = store

    def on_recv_rsp(self, rsp_pb):
        ret_code, content = super().on_recv_rsp(rsp_pb)
        if ret_code == RET_OK:
            self.store.update_rt_data(content)
        return ret_code, content
