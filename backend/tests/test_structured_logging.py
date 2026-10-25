import json
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.structured_logging import JsonFormatter
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_request_logs_are_structured_and_include_request_metadata(client, caplog):
    with caplog.at_level(logging.INFO):
        response = client.get("/", headers={"X-Request-ID": "test-request-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"

    records = [record for record in caplog.records if record.getMessage() == "request_completed"]
    assert records
    record = records[-1]
    assert record.request_id == "test-request-123"
    assert record.method == "GET"
    assert record.path == "/"
    assert record.status_code == 200
    assert isinstance(record.latency_ms, float)


def test_json_formatter_redacts_secret_values():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="admin_key=super-secret api_key=gemini-secret",
        args=(),
        exc_info=None,
    )
    formatted = json.loads(JsonFormatter().format(record))

    assert formatted["message"] == "admin_key=[REDACTED] api_key=[REDACTED]"
    assert "super-secret" not in json.dumps(formatted)
    assert "gemini-secret" not in json.dumps(formatted)


def test_request_logging_does_not_log_message_or_admin_key(client, caplog):
    with patch("app.main.GEMINI_API_KEY", "test-key"), patch(
        "app.main.rag_service.answer_question", return_value=("ok", [])
    ), caplog.at_level(logging.INFO):
        response = client.post(
            "/api/chat",
            json={"message": "private-user-message"},
            headers={"X-Admin-Key": "private-admin-key"},
        )

    assert response.status_code == 200
    assert "private-user-message" not in caplog.text
    assert "private-admin-key" not in caplog.text
