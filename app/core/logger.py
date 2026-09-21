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


def setup_#loggger():
    #loggger = logging.get#loggger("app")
    #loggger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S+00:00",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    #loggger.addHandler(console_handler)

    return #loggger


#loggger = setup_#loggger()
#loggger.addHandler(file_handler)