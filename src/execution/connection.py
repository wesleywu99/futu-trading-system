"""Connection manager: monitors OpenD connectivity and handles reconnection."""

import threading
import time
import logging

from futu import RET_OK

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self, config, collector, executor=None):
        self.config = config
        self.collector = collector
        self.executor = executor
        self.connected = False
        self._thread = None

    def start_monitoring(self):
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Connection monitor started")

    def _monitor_loop(self):
        while True:
            try:
                if self.collector.quote_ctx:
                    ret, _ = self.collector.quote_ctx.query_subscription()
                    if ret == RET_OK:
                        if not self.connected:
                            logger.info("Connection to OpenD established")
                        self.connected = True
                    else:
                        self.on_disconnect()
            except Exception:
                self.on_disconnect()
            time.sleep(30)

    def on_disconnect(self):
        if not self.connected:
            return
        logger.warning("Disconnected from OpenD!")
        self.connected = False
        self._attempt_reconnect()

    def _attempt_reconnect(self):
        max_retries = self.config.get("opend.reconnect.max_retries", 5)
        interval = self.config.get("opend.reconnect.retry_interval_sec", 10)

        for attempt in range(max_retries):
            logger.info(f"Reconnect attempt {attempt + 1}/{max_retries}...")
            time.sleep(interval)
            try:
                self.collector.reconnect()
                if self.executor:
                    self.executor.start()
                self.connected = True
                logger.info("Reconnected successfully!")
                return
            except Exception as e:
                logger.error(f"Reconnect failed: {e}")
                interval = min(interval * 2, 60)

        logger.critical("All reconnection attempts failed!")
