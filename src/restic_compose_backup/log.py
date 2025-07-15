import logging
import os
import sys

logger = logging.getLogger("restic_compose_backup")
HOSTNAME = os.environ["HOSTNAME"]

DEFAULT_LOG_LEVEL = logging.INFO
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def setup(level: str = "warning"):
    """Set up logging"""
    level = level or ""
    level = LOG_LEVELS.get(level.lower(), DEFAULT_LOG_LEVEL)
    logger.setLevel(level)

    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(level)
    # ch.setFormatter(logging.Formatter('%(asctime)s - {HOSTNAME} - %(name)s - %(levelname)s - %(message)s'))
    # ch.setFormatter(logging.Formatter('%(asctime)s - {HOSTNAME} - %(levelname)s - %(message)s'))
    ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s: %(message)s"))
    logger.addHandler(ch)
