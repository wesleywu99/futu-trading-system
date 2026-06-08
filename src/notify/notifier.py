"""Notification dispatcher: console, file log, and optional Telegram."""

import logging

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config):
        self.config = config
        self.enabled = config.get("notification.enabled", True)
        self.telegram_enabled = config.get("notification.telegram.enabled", False)

        if self.telegram_enabled:
            try:
                import requests
                self._requests = requests
                self._bot_token = config.get("notification.telegram.bot_token", "")
                self._chat_id = config.get("notification.telegram.chat_id", "")
            except ImportError:
                logger.warning("requests not installed, Telegram notifications disabled")
                self.telegram_enabled = False

    def send(self, event_type, message):
        if not self.enabled:
            return

        # Always log
        logger.info(f"[ALERT:{event_type}] {message}")

        # Telegram
        if self.telegram_enabled and self._bot_token and self._chat_id:
            self._send_telegram(f"[{event_type}] {message}")

    def _send_telegram(self, text):
        try:
            url = (
                f"https://api.telegram.org/bot{self._bot_token}"
                f"/sendMessage"
            )
            self._requests.post(url, json={
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "HTML",
            }, timeout=10)
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
