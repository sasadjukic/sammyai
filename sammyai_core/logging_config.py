"""Central logging configuration for SammyAI."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from types import TracebackType
from typing import Callable


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_FILE_NAME = "sammyai.log"


def configure_logging(
    log_dir: Path,
    *,
    level: int = logging.INFO,
    console: bool = True,
) -> Path:
    """Configure SammyAI's root logger once and return the active log file."""

    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / LOG_FILE_NAME

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not any(getattr(handler, "_sammyai_file_handler", False) for handler in root_logger.handlers):
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        file_handler._sammyai_file_handler = True  # type: ignore[attr-defined]
        root_logger.addHandler(file_handler)

    if console and not any(
        getattr(handler, "_sammyai_console_handler", False)
        for handler in root_logger.handlers
    ):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        console_handler._sammyai_console_handler = True  # type: ignore[attr-defined]
        root_logger.addHandler(console_handler)

    return log_file


def install_exception_hook() -> Callable[
    [type[BaseException], BaseException, TracebackType | None],
    None,
]:
    """Log otherwise-unhandled exceptions while preserving Python's default hook."""

    previous_hook = sys.excepthook

    def log_unhandled_exception(
        exception_type: type[BaseException],
        exception: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        if issubclass(exception_type, KeyboardInterrupt):
            previous_hook(exception_type, exception, traceback)
            return
        logging.getLogger("sammyai").critical(
            "Unhandled exception",
            exc_info=(exception_type, exception, traceback),
        )
        previous_hook(exception_type, exception, traceback)

    sys.excepthook = log_unhandled_exception
    return previous_hook
