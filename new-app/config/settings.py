"""Paths and runtime limits. Override output with MOA_OUTPUT_DIR (use K: drive in production)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _asset_root() -> Path:
    """Read-only app assets (config, templates, bundled xlsx)."""
    if _is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _data_root() -> Path:
    """Writable runtime data (output PDFs, logs)."""
    override = os.environ.get("MOA_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if _is_frozen():
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local:
            return Path(local) / "MOA Valuation"
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent.parent


ROOT = _asset_root()
DATA_ROOT = _data_root()
CONFIG_DIR = ROOT / "config"
TEMPLATES_DIR = ROOT / "templates"
OUTPUT_DIR = Path(os.environ.get("MOA_OUTPUT_DIR", DATA_ROOT / "output")).expanduser()
LOG_DIR = DATA_ROOT / "logs"

MAX_FILES = 80
MAX_FILE_BYTES = 50 * 1024 * 1024
HOST = os.environ.get("MOA_HOST", "127.0.0.1")
PORT = int(os.environ.get("MOA_PORT", "8002"))
FROZEN = _is_frozen()
