import json
import logging
import os
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_ -]?key|admin[_ -]?key|authorization|x-admin-key)(\s*[:=]\s*)\S+"
)


def redact_log_text(value: str) -> str:
    """Remove credential-like values from log messages."""
    return _SECRET_PATTERN.sub(r"\1\2[REDACTED]", value)


class JsonFormatter(logging.Formatter):
    """Format application logs as single-line JSON records."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_log_text(record.getMessage()),
            "request_id": getattr(record, "request_id", request_id_context.get()),
        }

        for field in ("method", "path", "status_code", "latency_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = redact_log_text(self.formatException(record.exc_info))

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    """Install one JSON stream handler for the application process."""
    root_logger = logging.getLogger()
    root_logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

    if any(getattr(handler, "_campusguide_json", False) for handler in root_logger.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler._campusguide_json = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)
