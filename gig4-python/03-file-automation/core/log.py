"""Logging setup: readable console output plus an optional log file.

Usage:
    from core.log import setup_logging
    log = setup_logging(verbose=args.verbose, log_file=args.log_file)
    log.info("Started")
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
DATEFMT = "%H:%M:%S"


def setup_logging(verbose: bool = False, log_file: str | Path | None = None, name: str = "app") -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    # Windows consoles (cp1252) can't print every character; replace instead of crashing.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(FORMAT, DATEFMT))
    root.addHandler(console)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(handler)

    # Third-party libraries are noisy at DEBUG; keep them at WARNING unless asked.
    # (core.http logs retries itself in one short line, so urllib3 stays at ERROR.)
    for noisy in ("urllib3", "charset_normalizer", "chardet"):
        logging.getLogger(noisy).setLevel(logging.DEBUG if verbose else logging.ERROR)
    return logging.getLogger(name)
