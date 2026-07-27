# backend/app/core/logger.py

import logging
from datetime import datetime, timezone


class AppFormatter(logging.Formatter):
    """Custom formatter that prepends [HH:MM:SS.mmm][CATEGORY] to each log record."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        category = getattr(record, "category", "SYSTEM")
        return f"[{timestamp}][{category}] {record.getMessage()}"


_logger = logging.getLogger("lesmeilleurs")
_logger.setLevel(logging.INFO)
_logger.handlers.clear()

handler = logging.StreamHandler()
handler.setFormatter(AppFormatter())
_logger.addHandler(handler)


class Logger:
    """Structured logger for the Les Meilleurs backend."""

    @staticmethod
    def api(method: str, path: str, extra: str = "") -> None:
        """Log an API event (request received, response sent)."""
        msg = f"{method} {path}"
        if extra:
            msg += f" - {extra}"
        _logger.info(msg, extra={"category": "API"})

    @staticmethod
    def task(task_name: str, message: str) -> None:
        """Log a Celery task event."""
        _logger.info(f"{task_name}: {message}", extra={"category": "TASK"})

    @staticmethod
    def phase(phase_name: str) -> None:
        """Log a pipeline phase transition."""
        _logger.info(phase_name, extra={"category": "PHASE"})

    @staticmethod
    def error(context: str, detail: str = "") -> None:
        """Log an error with context."""
        msg = f"{context}"
        if detail:
            msg += f": {detail}"
        _logger.error(msg, extra={"category": "ERROR"})


logger = Logger()
