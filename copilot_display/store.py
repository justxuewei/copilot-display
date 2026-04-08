"""Persistent storage for device cache and configuration."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEVICES_FILE = "devices.json"
_CONFIG_FILE = "config.json"

_DEFAULT_CONFIG: dict = {
    "scan_interval": 60,     # seconds between BLE device scans (0 = disabled)
    "refresh_interval": 300, # seconds between automatic display refreshes (0 = disabled)
    "work_days": [0, 1, 2, 3, 4],  # 0=Mon … 6=Sun; empty list = every day
    "work_start": "10:00",         # HH:MM — start of active window (empty = always active)
    "work_end": "20:00",           # HH:MM — end of active window (empty = always active)
}


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Data directory: %s", data_dir)

    # ── Devices ───────────────────────────────────────────────────────────────

    def load_devices(self) -> list[dict]:
        path = self.data_dir / _DEVICES_FILE
        if not path.exists():
            return []
        try:
            devices = json.loads(path.read_text())
            logger.info("Loaded %d cached device(s) from %s", len(devices), path)
            return devices
        except Exception:
            logger.warning("Failed to read %s, ignoring", path, exc_info=True)
            return []

    def save_devices(self, devices: list[dict]) -> None:
        path = self.data_dir / _DEVICES_FILE
        try:
            path.write_text(json.dumps(devices, indent=2))
        except Exception:
            logger.warning("Failed to save devices to %s", path, exc_info=True)

    # ── Config ────────────────────────────────────────────────────────────────

    def load_config(self) -> dict:
        path = self.data_dir / _CONFIG_FILE
        config = dict(_DEFAULT_CONFIG)
        if path.exists():
            try:
                config.update(json.loads(path.read_text()))
            except Exception:
                logger.warning("Failed to read %s, using defaults", path, exc_info=True)
        else:
            # Write defaults so users can discover and edit the file
            self.save_config(config)
        return config

    def save_config(self, config: dict) -> None:
        path = self.data_dir / _CONFIG_FILE
        try:
            path.write_text(json.dumps(config, indent=2))
        except Exception:
            logger.warning("Failed to save config to %s", path, exc_info=True)
