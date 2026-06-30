import logging
import sys
from app.config import settings


def setup_logging() -> logging.Logger:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)-24s %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    root = logging.getLogger("moderator")
    root.setLevel(level)
    root.addHandler(handler)
    return root


logger = setup_logging()
