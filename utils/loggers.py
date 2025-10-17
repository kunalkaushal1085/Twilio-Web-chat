import logging
import os

# Ensure the logs directory exists
LOGS_DIR = "app_data/logs"
os.makedirs(LOGS_DIR, exist_ok=True)

# Configure logging
LOG_FILE_PATH = os.path.join(LOGS_DIR, "app.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Create logger instance
logger = logging.getLogger(__name__)

def log_message(message: str, level: str = "info"):
    """
    Log messages to console and file.
    Args:
        message (str): The message to log.
        level (str): The log level ("info", "warning", "error").
    """
    if level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    else:
        logger.info(message)
