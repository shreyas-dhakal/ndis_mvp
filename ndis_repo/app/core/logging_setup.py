from __future__ import annotations

import logging
import os
from datetime import datetime


def setup_logging(*, log_dir: str, activity_name: str | None, log_level: str) -> str:
    """Configure application + uvicorn logging to a single file per activity.

    Returns the full path to the created log file.
    """

    os.makedirs(log_dir, exist_ok=True)
    activity = activity_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{activity}.log")

    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers (can happen with reload).
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(console_handler)

    logging.captureWarnings(True)

    # Make uvicorn logs use the root handlers.
    for uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ulogger = logging.getLogger(uv_name)
        ulogger.handlers = []
        ulogger.propagate = True

    root.info("Logging initialized", extra={"log_path": log_path})
    return log_path
