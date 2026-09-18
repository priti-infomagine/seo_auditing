import logging
import os
import sys
from datetime import datetime, timezone


# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

file_handler = logging.FileHandler(
    "logs/app.log"
)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S+00:00",
)

file_handler.setFormatter(formatter)


def setup_logger():
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S+00:00",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


logger = setup_logger()
logger.addHandler(file_handler)