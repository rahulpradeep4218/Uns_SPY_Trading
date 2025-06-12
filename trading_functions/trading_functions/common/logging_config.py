# logging_config.py

import logging
import os
from logging.handlers import RotatingFileHandler

# 1) toggle via env‐var or a config file
ENABLE_LOGGING = os.getenv("ENABLE_LOGGING", "false").lower() in ("true", "1", "yes")

# 2) where to write the file
LOG_FILE = os.getenv("LOG_FILE", "app.log")

# 3) root logger
logger = logging.getLogger()                      
logger.setLevel(logging.DEBUG if ENABLE_LOGGING else logging.INFO)

# 4) formatter
fmt = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
formatter = logging.Formatter(fmt)

# 5) console handler (always on)
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# 6) file handler (only if logging enabled)
if ENABLE_LOGGING:
    fh = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
