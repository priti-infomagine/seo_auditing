import logging
import os
import sys


# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

file_handler = logging.FileHandler(
    "logs/app.log"
)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)

file_handler.setFormatter(formatter)


def setup_logger():
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


logger = setup_logger()
logger.addHandler(file_handler)