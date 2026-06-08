"""Order executor: places/cancels orders via Futu SecTradeContext."""

import os
import time
import logging
import threading
from collections import deque

from futu import (
    OpenSecTradeContext,
    TrdEnv,
    TrdSide,
    TrdMarket,
    OrderType,
    ModifyOrderOp,
    RET_OK,
)

from src.core.events import SignalType

logger = logging.getLogger(__name__)


class OrderExecutor:
    def __init__(self, config, store):
        self.config = config
        self.store = store
        # One context per market (HK and US use different filter_trdmarket)
        self.hk_trade_ctx = None
        self.us_trade_ctx = None
        self.order_history = deque(maxlen=1000)
        self._history_lock = threading.Lock()

    def start(self):
        host = self.config.get("opend.host", "127.0.0.1")
        port = self.config.get("opend.port", 11111)
        password = os.environ.get("FUTU_TRADE_PASSWORD", "")

        if self.config.get("trading.markets.HK.enabled", True):
            self.hk_trade_ctx = OpenSecTradeContext(
                filter_trdmarket=TrdMarket.HK, host=host, port=port
            )
            if password:
                ret, data = self.hk_trade_ctx.unlock_trade(password)
                if ret != RET_OK:
                    logger.warning(f"HK trade unlock failed: {data}")
            logger.info("HK trade context connected")

        if self.config.get("trading.markets.US.enabled", True):
            self.us_trade_ctx = OpenSecTradeContext(
                filter_trdmarket=TrdMarket.US, host=host, port=port
            )
            if password:
                ret, data = self.us_trade_ctx.unlock_trade(password)
                if ret != RET_OK:
                    logger.warning(f"US trade unlock failed: {data}")
            logger.info("US trade context connected")

    def execute(self, signal):
        trade_ctx = self._get_trade_context(signal.code)
        if not trade_ctx:
            logger.error(f"No trade context for {signal.code}")
            return

        current_price = self._get_current_price(signal.code)
        if current_price <= 0:
            logger.error(f"No valid price for {signal.code}")
            return

        # Slippage check
        if signal.price > 0:
            slippage = abs(current_price - signal.price) / signal.price * 100
            max_slip = self.config.get("execution.max_slippage_pct", 0.5)
            if slippage > max_slip:
                logger.warning(
                    f"Slippage {slippage:.2f}% > {max_slip}%, skip {signal.code}"
                )
                return

        trd_side = (
            TrdSide.BUY if signal.signal_type == SignalType.BUY else TrdSide.SELL
        )
        trd_env = (
            TrdEnv.REAL
            if self.config.get("trading.env") == "REAL"
            else TrdEnv.SIMULATE
        )

        qty = signal.suggested_qty if signal.suggested_qty > 0 else 100

        # Round price to valid tick size (US stocks: $0.01 for >= $1)
        current_price = round(current_price, 2)

        max_retries = self.config.get("execution.order_retry.max_retries", 2)
        retry_delay = self.config.get("execution.order_retry.retry_delay_sec", 3)

        for attempt in range(max_retries + 1):
            ret, data = trade_ctx.place_order(
                price=current_price,
                qty=qty,
                code=signal.code,
                trd_side=trd_side,
                order_type=OrderType.NORMAL,
                trd_env=trd_env,
            )
            if ret == RET_OK:
                order_id = data["order_id"][0]
                logger.info(
                    f"Order placed: {trd_side.value} {qty} {signal.code} "
                    f"@ {current_price}, id={order_id}"
                )
                with self._history_lock:
                    self.order_history.append({
                        "order_id": order_id,
                        "signal": signal,
                        "timestamp": signal.timestamp,
                    })
                return
            else:
                logger.error(
                    f"Order failed (attempt {attempt + 1}/{max_retries + 1}): {data}"
                )
                if attempt < max_retries:
                    time.sleep(retry_delay)

    def cancel_order(self, order_id, code):
        trade_ctx = self._get_trade_context(code)
        if not trade_ctx:
            return
        ret, data = trade_ctx.modify_order(
            modify_order_op=ModifyOrderOp.CANCEL,
            order_id=order_id,
            price=0,
            qty=0,
        )
        if ret == RET_OK:
            logger.info(f"Order cancelled: {order_id}")
        else:
            logger.error(f"Cancel failed: {data}")

    def _get_trade_context(self, code):
        if code.startswith("HK."):
            return self.hk_trade_ctx
        elif code.startswith("US."):
            return self.us_trade_ctx
        return None

    def _get_current_price(self, code):
        return self.store.get_latest_price(code)

    def close(self):
        if self.hk_trade_ctx:
            self.hk_trade_ctx.close()
            self.hk_trade_ctx = None
        if self.us_trade_ctx:
            self.us_trade_ctx.close()
            self.us_trade_ctx = None
        logger.info("Order executor closed")
