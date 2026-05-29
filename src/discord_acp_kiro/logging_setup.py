"""Logging configuration: stdout + rotating file."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler


def setup_logging(log_file: str = "bot.log", level: int = logging.INFO) -> None:
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logging.getLogger("discord").setLevel(logging.INFO)
