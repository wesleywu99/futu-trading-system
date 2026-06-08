"""YAML configuration loader with dot-notation access."""

import os
import yaml


class Config:
    def __init__(self, config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f)
        self._validate()

    def _validate(self):
        required_keys = ["opend", "trading", "watchlist"]
        for key in required_keys:
            if key not in self._data:
                raise ValueError(f"Missing required config key: {key}")

    def get(self, key_path: str, default=None):
        """Access nested values via dot notation. e.g. 'opend.host'"""
        keys = key_path.split(".")
        value = self._data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    @classmethod
    def load_from_env(cls):
        default_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.yaml")
        )
        config_path = os.environ.get("FUTU_CONFIG_PATH", default_path)
        return cls(config_path)
