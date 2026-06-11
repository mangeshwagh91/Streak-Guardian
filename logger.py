"""
logger.py — Structured logging setup for Streak Guardian.

Features:
  • Rotating file handler (logs/streak_guardian.log, 5 MB × 5 backups)
  • Coloured console output via colorlog
  • JSON-structured file output for easy parsing
  • Single call: get_logger(__name__)
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


_LOGS_DIR = Path(__file__).parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

_LOG_FILE = _LOGS_DIR / "streak_guardian.log"
_LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_STR, logging.INFO)

_initialised = False


# ── JSON formatter ────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


# ── coloured console formatter ────────────────────────────────────────────────

try:
    import colorlog  # type: ignore

    _console_fmt = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s %(levelname)-8s%(reset)s "
        "%(cyan)s%(name)s%(reset)s — %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG": "white",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
except ImportError:
    _console_fmt = logging.Formatter(  # type: ignore[assignment]
        "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


# ── initialiser ───────────────────────────────────────────────────────────────

def _setup_root_logger() -> None:
    global _initialised
    if _initialised:
        return
    _initialised = True

    root = logging.getLogger()
    root.setLevel(_LOG_LEVEL)

    # Console handler — use UTF-8 to handle emoji on Windows
    import io
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    ch = logging.StreamHandler(utf8_stdout)
    ch.setLevel(_LOG_LEVEL)
    ch.setFormatter(_console_fmt)
    root.addHandler(ch)

    # Rotating JSON file handler
    fh = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)      # always capture DEBUG to file
    fh.setFormatter(JSONFormatter())
    root.addHandler(fh)

    # Silence overly chatty third-party loggers
    for noisy in ("httpx", "httpcore", "asyncio", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a named logger, initialising the root logger on first call."""
    _setup_root_logger()
    return logging.getLogger(name)
