from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_chat_rate_limit_returns_429_and_retry_after(client):
    with patch("app.main.GEMINI_API_KEY", "test-key"), patch(
        "app.main.rag_service.answer_question", return_value=("ok", [])
    ):
        responses = [
            client.post("/api/chat", json={"message": f"Question {index}"})
            for index in range(61)
        ]

    assert all(response.status_code == 200 for response in responses[:60])
    assert responses[-1].status_code == 429
    assert responses[-1].headers.get("Retry-After")


def test_admin_rate_limit_is_stricter_and_returns_429(client):
    with patch("app.api.knowledge.vector_store.delete_document", return_value=0):
        responses = [
            client.delete("/api/knowledge/documents/rate-test")
            for _ in range(11)
        ]

    assert all(response.status_code == 200 for response in responses[:10])
    assert responses[-1].status_code == 429
    assert responses[-1].headers.get("Retry-After")
