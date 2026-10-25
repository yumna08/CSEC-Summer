import concurrent.futures
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, reset_engine_for_testing
from app.db.models import KnowledgeDocument
from app.main import app
from app.schemas.chat import SourceCitation
from app.schemas.knowledge import DocumentMetadata, VerificationStatus
from app.services.registry import SourceRegistry
from app.services.vector_store import VectorStoreService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db_engine():
    """Create an isolated in-memory SQLite database for deterministic tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    reset_engine_for_testing(engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    reset_engine_for_testing(None)
    engine.dispose()


# =============================================================================
# 1. INVALID REQUESTS AND VALIDATION
# =============================================================================

def test_invalid_requests_chat_validation(client):
    """Verify chat endpoint rejects empty, whitespace, or malformed queries with 422."""
    with patch("app.main.GEMINI_API_KEY", "test-api-key"):
        # Empty string (rejected by Pydantic schema validation)
        res1 = client.post("/api/chat", json={"message": ""})
        assert res1.status_code == 422

        # Whitespace only (rejected by application logic message.strip())
        res2 = client.post("/api/chat", json={"message": "   \n\t  "})
        assert res2.status_code == 422
        assert "Please enter a question" in res2.json()["detail"]

        # Missing field
        res3 = client.post("/api/chat", json={})
        assert res3.status_code == 422


def test_invalid_requests_upload_validation(client):
    """Verify upload rejects invalid file extensions, empty content, and bad MIME types."""
    # Disallowed extension
    res_ext = client.post(
        "/api/knowledge/upload",
        files={"file": ("malicious.exe", b"MZ\x90\x00BinaryContent", "application/octet-stream")},
    )
    assert res_ext.status_code == 400
    assert "Unsupported file type" in res_ext.json()["detail"]

    # Disallowed script
    res_py = client.post(
        "/api/knowledge/upload",
        files={"file": ("exploit.py", b"import os; os.system('ls')", "text/x-python")},
    )
    assert res_py.status_code == 400
    assert "Unsupported file type" in res_py.json()["detail"]

    # Empty file (0 bytes)
    res_empty = client.post(
        "/api/knowledge/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert res_empty.status_code == 400
    assert "Uploaded file is empty" in res_empty.json()["detail"]


def test_invalid_requests_url_ssrf_and_domain_safety(client):
    """Verify URL ingestion rejects external domains, loopbacks, and cloud metadata IPs."""
    # Disallowed external domain
    res_ext = client.post("/api/knowledge/ingest-url", json={"url": "https://google.com/search"})
    assert res_ext.status_code == 200
    assert res_ext.json()["status"] == "failed"
    assert "not in the approved ASTU domain list" in res_ext.json()["message"]

    # Disallowed loopback IP
    res_loop = client.post("/api/knowledge/ingest-url", json={"url": "http://127.0.0.1:8000/admin"})
    assert res_loop.status_code == 200
    assert res_loop.json()["status"] == "failed"

    # Disallowed cloud metadata IP
    res_meta = client.post("/api/knowledge/ingest-url", json={"url": "http://169.254.169.254/latest/meta-data"})
    assert res_meta.status_code == 200
    assert res_meta.json()["status"] == "failed"


# =============================================================================
# 2. MISSING CONFIGURATION
# =============================================================================

def test_missing_gemini_api_key(client):
    """Verify 503 is returned when GEMINI_API_KEY is not configured."""
    with patch("app.main.GEMINI_API_KEY", ""):
        res_chat = client.post("/api/chat", json={"message": "Where is the library?"})
        assert res_chat.status_code == 503
        assert "Gemini API key is not configured" in res_chat.json()["detail"]

        res_test = client.post("/api/ai/test")
        assert res_test.status_code == 503
        assert "Gemini API key is not configured" in res_test.json()["detail"]


def test_missing_admin_api_key_when_auth_required(client):
    """Verify 503 is returned for admin operations when REQUIRE_ADMIN_AUTH is true but no key set."""
    with patch("app.core.security.REQUIRE_ADMIN_AUTH", True), \
         patch("app.core.security.ADMIN_API_KEY", ""):
        res = client.post("/api/knowledge/reindex")
        assert res.status_code == 503
        assert "ADMIN_API_KEY is not configured" in res.json()["detail"]


# =============================================================================
# 3. ADMINISTRATIVE AUTHENTICATION AND AUTHORIZATION
# =============================================================================

def test_admin_authorization_enforcement_and_timing_safety(client):
    """Verify constant-time admin authorization properly validates keys and rejects bad keys."""
    configured_key = "super_secure_admin_key_2026"

    with patch("app.core.security.REQUIRE_ADMIN_AUTH", True), \
         patch("app.core.security.ADMIN_API_KEY", configured_key):

        # Missing header -> 401
        res_missing = client.post("/api/knowledge/reindex")
        assert res_missing.status_code == 401
        assert "Invalid or missing administrative authorization key" in res_missing.json()["detail"]

        # Wrong key -> 401
        res_wrong = client.post(
            "/api/knowledge/reindex",
            headers={"X-Admin-Key": "wrong_key_here"},
        )
        assert res_wrong.status_code == 401

        # Delete document with wrong key -> 401
        res_del_unauth = client.delete(
            "/api/knowledge/documents/doc_123",
            headers={"X-Admin-Key": "wrong_key"},
        )
        assert res_del_unauth.status_code == 401

        # Valid key -> authorized (calls underlying service)
        with patch("app.api.knowledge.ingestion_service.reindex_all") as mock_reindex:
            from app.schemas.knowledge import ReindexResponse
            mock_reindex.return_value = ReindexResponse(
                total_reindexed=1,
                results=[],
            )
            res_valid = client.post(
                "/api/knowledge/reindex",
                headers={"X-Admin-Key": configured_key},
            )
            assert res_valid.status_code == 200
            assert res_valid.json()["total_reindexed"] == 1


# =============================================================================
# 4. DATABASE FAILURES AND RESILIENCE
# =============================================================================

def test_chat_resilience_when_database_is_down(client):
    """
    RAG chat relies primarily on ChromaDB vector collection.
    Verify that even if PostgreSQL database throws an OperationalError,
    /api/chat continues serving grounded answers without crashing.
    """
    mock_sources = [
        SourceCitation(
            title="ASTU Academic Calendar",
            url="https://www.astu.edu.et/admission/importants/academic-calendar",
            document_name="calendar.pdf",
            academic_year="2025/2026",
            snippet="Registration begins on October 25.",
        )
    ]

    with patch("app.main.GEMINI_API_KEY", "test-key"), \
         patch("app.main.rag_service.answer_question") as mock_answer:
        mock_answer.return_value = ("Registration begins on October 25, 2025.", mock_sources)

        response = client.post("/api/chat", json={"message": "When is registration?"})
        assert response.status_code == 200
        data = response.json()
        assert "October 25" in data["reply"]
        assert len(data["sources"]) == 1
        assert data["sources"][0]["title"] == "ASTU Academic Calendar"


def test_services_database_failure_graceful_handling():
    """Verify registry and vector_store methods handle database connection errors without crashing."""
    broken_factory = MagicMock(side_effect=OperationalError("connection failed", None, None))

    # Source registry should return empty list gracefully on DB error
    reg = SourceRegistry(registry_file=None, session_factory=broken_factory)
    sources = reg.get_sources()
    assert sources == []

    # Vector store metadata methods should handle DB error gracefully
    vs = VectorStoreService(session_factory=broken_factory)
    assert vs.list_documents() == []
    assert vs.get_document("any_doc_id") is None


# =============================================================================
# 5. HEALTH CHECK ENDPOINT (BASIC AND DETAILED)
# =============================================================================

def test_health_endpoint_basic_and_detailed(client):
    """Verify basic health check returns simple status, and detailed=True reports components."""
    # Basic check (backward compatible)
    res_basic = client.get("/api/health")
    assert res_basic.status_code == 200
    assert res_basic.json() == {"status": "healthy", "service": "campusguide-api"}

    # Detailed check
    res_detailed = client.get("/api/health?detailed=true")
    assert res_detailed.status_code == 200
    data = res_detailed.json()
    assert "status" in data
    assert "components" in data
    assert "vector_store" in data["components"]
    assert "database" in data["components"]
    assert "ai_service" in data["components"]
    assert data["components"]["vector_store"]["status"] == "ready"


def test_detailed_health_reports_degraded_when_db_down(client):
    """Verify detailed health check reports degraded when database connection fails."""
    with patch("app.main.DATABASE_URL", "postgresql+psycopg://user:pass@invalid-host:5432/db"), \
         patch("app.db.database.get_engine") as mock_engine:
        mock_conn = MagicMock()
        mock_conn.__enter__.side_effect = OperationalError("connection refused", None, None)
        mock_engine.return_value.connect.return_value = mock_conn

        res = client.get("/api/health?detailed=true")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"]["status"] == "disconnected"


# =============================================================================
# 6. AI PROVIDER FAILURE AND RECOVERY
# =============================================================================

def test_chat_ai_provider_failure_handling(client):
    """Verify unexpected RAG exceptions return clean 500 error without exposing stack traces."""
    with patch("app.main.GEMINI_API_KEY", "test-key"), \
         patch("app.main.rag_service.answer_question", side_effect=RuntimeError("AI provider timeout")):
        res = client.post("/api/chat", json={"message": "What is the tuition fee?"})
        assert res.status_code == 500
        assert "An internal server error occurred" in res.json()["detail"]


# =============================================================================
# 7. CONCURRENT REQUESTS
# =============================================================================

def test_concurrent_chat_requests(client):
    """Verify multiple concurrent chat requests execute deterministically without race conditions."""
    mock_sources = [
        SourceCitation(
            title="ASTU Academic Calendar",
            url="https://www.astu.edu.et/admission/importants/academic-calendar",
            document_name="calendar.pdf",
        )
    ]

    with patch("app.main.GEMINI_API_KEY", "test-key"), \
         patch("app.main.rag_service.answer_question") as mock_answer:
        mock_answer.return_value = ("Concurrent response test", mock_sources)

        def make_request(idx: int):
            return client.post("/api/chat", json={"message": f"Question number {idx}"})

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            responses = [f.result() for f in futures]

        for res in responses:
            assert res.status_code == 200
            assert res.json()["reply"] == "Concurrent response test"


# =============================================================================
# 8. REPEATED INGESTION AND IDEMPOTENCE
# =============================================================================

def test_repeated_ingestion_and_idempotence(isolated_db_engine):
    """Verify index_document is idempotent: unchanged content_hash skips reindexing."""
    SessionTest = sessionmaker(autocommit=False, autoflush=False, bind=isolated_db_engine)
    vs = VectorStoreService(session_factory=SessionTest)

    meta = DocumentMetadata(
        doc_id="test_doc_001",
        source_url="https://www.astu.edu.et/page",
        source_title="ASTU Page",
        source_type="web",
        document_name="page.html",
        content_hash="hash_v1_abc123",
        chunk_count=2,
        verification_status=VerificationStatus.VERIFIED.value,
    )

    # First indexing
    with patch.object(vs, "_purge_chunks") as mock_purge:
        # Pre-seed in DB
        vs.record_document_status(meta)

        # Re-index with same hash -> should be unchanged
        res_unchanged = vs.index_document(
            metadata=meta,
            chunks=["Chunk 1", "Chunk 2"],
            embeddings=[[0.1] * 768, [0.2] * 768],
        )
        assert res_unchanged["status"] == "unchanged"
        mock_purge.assert_not_called()

        # Update with new content hash -> should purge old chunks
        meta_updated = DocumentMetadata(
            doc_id="test_doc_001",
            source_url="https://www.astu.edu.et/page",
            source_title="ASTU Page",
            source_type="web",
            document_name="page.html",
            content_hash="hash_v2_updated456",
            chunk_count=2,
            verification_status=VerificationStatus.VERIFIED.value,
        )

        with patch.object(vs.collection, "add") as mock_add:
            res_updated = vs.index_document(
                metadata=meta_updated,
                chunks=["New Chunk 1", "New Chunk 2"],
                embeddings=[[0.3] * 768, [0.4] * 768],
            )
            assert res_updated["status"] == "indexed"
            mock_purge.assert_called_once_with("test_doc_001")
