"""Logging setup with console and rotating file handler."""

import os
import logging
from logging.handlers import RotatingFileHandler


def setup_logging(config=None):
    level_name = "INFO"
    file_path = os.path.join("logs", "trading.log")
    max_bytes = 50 * 1024 * 1024  # 50MB
    backup_count = 5

    if config:
        level_name = config.get("logging.level", "INFO")
        file_enabled = config.get("notification.file.enabled", True)
        if file_enabled:
            file_path = config.get("notification.file.path", file_path)
            max_bytes = config.get("notification.file.max_size_mb", 50) * 1024 * 1024
            backup_count = config.get("notification.file.backup_count", 5)

    log_level = getattr(logging, level_name.upper(), logging.INFO)

    # Ensure log directory exists
    log_dir = os.path.dirname(file_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (rotating)
    file_handler = RotatingFileHandler(
        file_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return root_logger
