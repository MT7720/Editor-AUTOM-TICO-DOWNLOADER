"""Utility helpers for the GUI package."""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
from typing import Optional

LOGGER_NAME = "video_editor_app"
logger = logging.getLogger(LOGGER_NAME)


def resource_path(relative_path: str) -> str:
    """Return the absolute path to a bundled resource."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_app_data_path() -> str:
    """Create (if needed) and return the application data directory."""
    app_data_folder_name = "EditorDownloaderUniversal"
    if platform.system() == "Windows":
        base_dir: Optional[str] = os.getenv("APPDATA")
    else:
        base_dir = os.path.expanduser("~/.config")
    app_data_dir = os.path.join(base_dir or os.path.expanduser("~"), app_data_folder_name)
    os.makedirs(app_data_dir, exist_ok=True)
    return app_data_dir


def configure_file_logging(log_filename: str = "app_main.log") -> Optional[str]:
    """Configure the rotating file handler used by the GUI application."""
    logger.setLevel(logging.DEBUG)
    log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s")

    try:
        base_dir = (
            os.path.dirname(os.path.abspath(sys.argv[0]))
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__))
        )
        log_file_path = os.path.join(base_dir, log_filename)

        handler = logging.handlers.RotatingFileHandler(
            log_file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(log_formatter)

        existing = [h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        for h in existing:
            logger.removeHandler(h)
        logger.addHandler(handler)
        logger.info("Log configurado. Ficheiro de log: %s", os.path.abspath(log_file_path))
        return log_file_path
    except Exception as exc:  # pragma: no cover - defensive logging configuration
        print(f"Erro ao configurar o log em ficheiro: {exc}")
        return None
