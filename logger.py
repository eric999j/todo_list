"""集中化日誌設定。

預設輸出至 stderr 與 `app.log`（與本模組同層）。可透過環境變數調整：

* ``TODO_LOG_LEVEL``：DEBUG / INFO / WARNING / ERROR（預設 INFO）
* ``TODO_LOG_FILE``：覆寫日誌檔路徑；設為空字串可停用檔案輸出
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_LOGGER_NAME = "todo_app"
_initialized = False


def _resolve_log_file() -> Optional[str]:
    env_value = os.environ.get("TODO_LOG_FILE")
    if env_value is not None:
        return env_value or None
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "app.log")


def _configure() -> logging.Logger:
    global _initialized
    logger = logging.getLogger(_LOGGER_NAME)
    if _initialized:
        return logger

    level_name = os.environ.get("TODO_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(_DEFAULT_FORMAT)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_file = _resolve_log_file()
    if log_file:
        try:
            file_handler = RotatingFileHandler(
                log_file, maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            logger.warning("無法開啟日誌檔 %s，僅輸出至 stderr", log_file)

    _initialized = True
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """取得專案共用的 logger。傳入 ``name`` 會回傳子 logger。"""
    base = _configure()
    if name:
        return base.getChild(name)
    return base
