import io
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.chat import SourceCitation


@pytest.fixture
def client():
    return TestClient(app)


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ASTU CampusGuide AI"
    assert data["status"] == "running"


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "campusguide-api"}


def test_cors_allows_configured_frontend_origin_and_rejects_unknown_origin(client):
    allowed = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

    rejected = client.options(
        "/api/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_ai_test_missing_key(client):
    with patch("app.main.GEMINI_API_KEY", ""):
        response = client.post("/api/ai/test")
        assert response.status_code == 503
        assert "Gemini API key is not configured" in response.json()["detail"]


@patch("app.main.genai.Client")
def test_ai_test_success(mock_genai_cls, client):
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Welcome to ASTU CampusGuide AI!"
    mock_instance.models.generate_content.return_value = mock_response
    mock_genai_cls.return_value = mock_instance

    with patch("app.main.GEMINI_API_KEY", "fake_key"):
        response = client.post("/api/ai/test")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Gemini connection successful."
        assert data["reply"] == "Welcome to ASTU CampusGuide AI!"


def test_chat_empty_message(client):
    with patch("app.main.GEMINI_API_KEY", "fake_key"):
        response = client.post("/api/chat", json={"message": "   "})
        assert response.status_code == 422


@patch("app.main.rag_service.answer_question")
def test_chat_success_with_sources_frontend_compatible(mock_answer, client):
    mock_answer.return_value = (
        "Semester 1 registration starts on October 20.",
        [
            SourceCitation(
                title="ASTU Academic Calendar",
                url="https://www.astu.edu.et/calendar",
                document_name="calendar.html",
                academic_year="2024/2025",
                snippet="Registration starts October 20.",
            )
        ],
    )

    with patch("app.main.GEMINI_API_KEY", "fake_key"):
        response = client.post("/api/chat", json={"message": "When is registration?"})
        assert response.status_code == 200
        data = response.json()

        # Frontend expects data.reply (and optionally data.sources)
        assert "reply" in data
        assert "October 20" in data["reply"]
        assert "sources" in data
        assert len(data["sources"]) == 1
        assert data["sources"][0]["title"] == "ASTU Academic Calendar"
        assert data["sources"][0]["url"] == "https://www.astu.edu.et/calendar"


def test_knowledge_sources_list(client):
    response = client.get("/api/knowledge/sources")
    assert response.status_code == 200
    data = response.json()
    assert "sources" in data
    assert len(data["sources"]) >= 5
    urls = [s["url"] for s in data["sources"]]
    assert "https://www.astu.edu.et/" in urls
    assert "https://portal.astu.edu.et/pages/active_calendars" in urls


def test_knowledge_documents_list(client):
    response = client.get("/api/knowledge/documents")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "documents" in data


def test_upload_invalid_file_extension(client):
    response = client.post(
        "/api/knowledge/upload",
        files={"file": ("malicious.exe", b"malicious binary content", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_empty_file(client):
    response = client.post(
        "/api/knowledge/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 400
    assert "Uploaded file is empty" in response.json()["detail"]


@patch("app.api.knowledge.ingestion_service.ingest_file")
def test_upload_valid_txt_file(mock_ingest, client):
    from app.schemas.knowledge import IngestResult

    mock_ingest.return_value = IngestResult(
        doc_id="file_123",
        document_name="guide.txt",
        status="indexed",
        chunk_count=2,
        message="Successfully indexed 2 chunks.",
    )

    response = client.post(
        "/api/knowledge/upload",
        files={"file": ("guide.txt", b"ASTU guide text content", "text/plain")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "indexed"
    assert data["chunk_count"] == 2


@patch("app.api.knowledge.vector_store.delete_document")
def test_delete_document_endpoint(mock_delete, client):
    mock_delete.return_value = 3
    response = client.delete("/api/knowledge/documents/test_doc_id")
    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == "test_doc_id"
    assert data["deleted_chunks"] == 3


def test_admin_authorization_enforced_when_configured(client):
    with patch("app.core.security.REQUIRE_ADMIN_AUTH", True):
        with patch("app.core.security.ADMIN_API_KEY", "super_secret_admin_key"):
            # Request without key
            response = client.delete("/api/knowledge/documents/doc1")
            assert response.status_code == 401

            # Request with wrong key
            response = client.delete(
                "/api/knowledge/documents/doc1",
                headers={"X-Admin-Key": "wrong_key"},
            )
            assert response.status_code == 401

            # Request with correct key
            with patch("app.api.knowledge.vector_store.delete_document", return_value=1):
                response = client.delete(
                    "/api/knowledge/documents/doc1",
                    headers={"X-Admin-Key": "super_secret_admin_key"},
                )
                assert response.status_code == 200
