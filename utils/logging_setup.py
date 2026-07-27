from __future__ import annotations

import logging
import logging.handlers
import traceback
from pathlib import Path

from .paths import APP_VERSION, logs_dir

_CONFIGURED = False


def setup_logging() -> Path:
    """Configure rotating file logging under the per-user data dir. Idempotent."""
    global _CONFIGURED
    log_file = logs_dir() / "app.log"
    if _CONFIGURED:
        return log_file
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logging.getLogger(__name__).info("logging ready, version=%s", APP_VERSION)
    _CONFIGURED = True
    return log_file


def log_exception(context: str) -> None:
    logging.getLogger("app").error("%s\n%s", context, traceback.format_exc())
