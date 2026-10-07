"""Structured logging for the API (stdlib-based, JSON-friendly fields)."""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Return a logger with a structured single-line format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


logger = get_logger("turnos")
