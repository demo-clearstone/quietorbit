"""Paths and runtime limits. Override output with MOA_OUTPUT_DIR (use K: drive in production)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    _default_data_dir = Path(
        os.environ.get(
            "LOCALAPPDATA",
            Path.home() / "AppData" / "Local",
        )
    ) / "MOA Valuation Package"
else:
    ROOT = Path(__file__).resolve().parent.parent
    _default_data_dir = ROOT

DATA_DIR = Path(os.environ.get("MOA_DATA_DIR", _default_data_dir)).expanduser()
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = Path(os.environ.get("MOA_OUTPUT_DIR", DATA_DIR / "output")).expanduser()
LOG_DIR = DATA_DIR / "logs"
TEMPLATES_DIR = ROOT / "templates"

MAX_FILES = 80
MAX_FILE_BYTES = 50 * 1024 * 1024
HOST = os.environ.get("MOA_HOST", "127.0.0.1")
PORT = int(os.environ.get("MOA_PORT", "8002"))
