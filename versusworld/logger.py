from __future__ import annotations

import logging
import sys

from versusworld.config import Settings


def get_logger(name: str = "versusworld") -> logging.Logger:
    settings = Settings()
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(settings.log_level)
    return logger
