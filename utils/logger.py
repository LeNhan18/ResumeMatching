import logging
import sys
from pathlib import Path

log_dir = "logs"


def setup_logger(name: str, log_file: str = "app.log", log_level: int = logging.INFO) -> logging.Logger:
    """Tạo một logger với cấu hình cơ bản, ghi log vào file và console."""

    # Tạo logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Tránh tạo nhiều handler nếu logger đã có handler
    if logger.handlers:
        return logger

    # Format log
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    log_file_path = Path(log_dir) / log_file
    log_file_path.parent.mkdir(exist_ok=True)

    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
