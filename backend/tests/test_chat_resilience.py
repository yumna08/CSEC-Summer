from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.genai.errors import APIError

from app.main import app
from app.services.rag import RAGService


def make_api_error(code: int, message: str, status: str = "") -> APIError:
    return APIError(
        code,
        {"error": {"code": code, "message": message, "status": status or str(code)}},
    )


def test_consecutive_questions_exam_prep_then_dean_of_student_services():
    """
    Test consecutive questions in the exact reported scenario:
    1. 'How can I prepare for exams?' (general advice, empty sources)
    2. 'What services does the Dean of Student Services provide?' (factual, citations returned)
    Verify both succeed consecutively without breaking state.
    """
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash", fallback_model="gemini-flash-latest")
    mock_client = MagicMock()
    rag._client = mock_client

    # Request 1: General study advice
    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[]):
            mock_res1 = MagicMock()
            mock_res1.text = (
                "Here are general exam preparation tips: Start early, plan a schedule, "
                "and practice past questions.\n\nSOURCES_USED: NONE"
            )
            mock_client.models.generate_content.return_value = mock_res1

            ans1, sources1 = rag.answer_question("How can I prepare for exams?")
            assert "general exam preparation tips" in ans1
            assert sources1 == []

    # Request 2: Factual question about Dean of Student Services
    ss_chunk = {
        "text": (
            "The Office of the Dean of Student Services provides Cafeteria Services, "
            "Dormitory Services, and Student Health Clinic Services."
        ),
        "metadata": {
            "source_title": "Dean of Student Services",
            "source_url": "https://www.astu.edu.et/student-services",
            "document_name": "dean-student-services.html",
            "verification_status": "candidate",
        },
        "distance": 0.21,
    }
    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[ss_chunk]):
            mock_res2 = MagicMock()
            mock_res2.text = (
                "The Dean of Student Services provides Cafeteria and Dormitory accommodations.\n\n"
                "SOURCES_USED: [1]"
            )
            mock_client.models.generate_content.return_value = mock_res2

            ans2, sources2 = rag.answer_question("What services does the Dean of Student Services provide?")
            assert "Cafeteria and Dormitory accommodations" in ans2
            assert len(sources2) == 1
            assert sources2[0].title == "Dean of Student Services"
            assert sources2[0].url == "https://www.astu.edu.et/student-services"


def test_gemini_transient_503_triggers_retry_and_succeeds():
    """Verify that a transient 503 UNAVAILABLE on attempt 1 retries and succeeds on attempt 2."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash", max_retries=2)
    mock_client = MagicMock()
    rag._client = mock_client

    error_503 = make_api_error(
        503,
        "This model is currently experiencing high demand. Spikes are temporary.",
        "UNAVAILABLE",
    )
    success_response = MagicMock()
    success_response.text = "Here is the verified information.\n\nSOURCES_USED: NONE"

    mock_client.models.generate_content.side_effect = [error_503, success_response]

    with patch("app.services.rag.time.sleep") as mock_sleep:
        with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
            with patch("app.services.rag.vector_store.similarity_search", return_value=[]):
                ans, sources = rag.answer_question("What is the ASTU mission?")
                assert "verified information" in ans
                assert mock_sleep.called
                assert mock_client.models.generate_content.call_count == 2


def test_gemini_quota_exhaustion_triggers_fallback_and_succeeds():
    """Verify that a 429 quota exhaustion on primary model immediately falls back to fallback model and succeeds."""
    rag = RAGService(
        api_key="fake_key",
        model="gemini-2.5-flash",
        fallback_model="gemini-flash-latest",
        max_retries=1,
    )
    mock_client = MagicMock()
    rag._client = mock_client

    # Primary model throws 429 quota exhaustion (limit 20 reached)
    quota_error = make_api_error(
        429,
        "You exceeded your current quota. Quota exceeded for metric ... limit: 20, model: gemini-2.5-flash",
        "RESOURCE_EXHAUSTED",
    )
    fallback_response = MagicMock()
    fallback_response.text = "Answer generated via high-availability fallback.\n\nSOURCES_USED: NONE"

    def side_effect(model, contents, config):
        if model == "gemini-2.5-flash":
            raise quota_error
        elif model == "gemini-flash-latest":
            return fallback_response
        raise ValueError(f"Unexpected model: {model}")

    mock_client.models.generate_content.side_effect = side_effect

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[]):
            ans, sources = rag.answer_question("Where can I find student services?")
            assert "via high-availability fallback" in ans
            assert sources == []


def test_all_models_quota_exhausted_raises_429():
    """Verify that if all models exhaust quota, an HTTP 429 is raised with safe user message."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash", fallback_model="gemini-flash-latest", max_retries=0)
    mock_client = MagicMock()
    rag._client = mock_client

    quota_error = make_api_error(429, "Quota exceeded. RESOURCE_EXHAUSTED", "RESOURCE_EXHAUSTED")
    mock_client.models.generate_content.side_effect = quota_error

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[]):
            with pytest.raises(HTTPException) as exc_info:
                rag.answer_question("Test query")
            assert exc_info.value.status_code == 429
            assert "high traffic or temporary rate limits" in exc_info.value.detail


def test_gemini_timeout_raises_504():
    """Verify that a timeout error raises HTTP 504 Gateway Timeout."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash", max_retries=0)
    mock_client = MagicMock()
    rag._client = mock_client

    mock_client.models.generate_content.side_effect = TimeoutError("Connection to AI provider timed out")

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[]):
            with pytest.raises(HTTPException) as exc_info:
                rag.answer_question("Test query")
            assert exc_info.value.status_code == 504
            assert "timed out" in exc_info.value.detail


def test_gemini_auth_failure_raises_503():
    """Verify that authentication / permission errors raise HTTP 503."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash", max_retries=0)
    mock_client = MagicMock()
    rag._client = mock_client

    auth_error = make_api_error(403, "PERMISSION_DENIED: API_KEY_INVALID", "PERMISSION_DENIED")
    mock_client.models.generate_content.side_effect = auth_error

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[]):
            with pytest.raises(HTTPException) as exc_info:
                rag.answer_question("Test query")
            assert exc_info.value.status_code == 503
            assert "authentication failed" in exc_info.value.detail


def test_subsequent_request_succeeds_after_failed_request():
    """Verify that one failed request does not corrupt or break subsequent chat requests."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash", max_retries=0)
    mock_client = MagicMock()
    rag._client = mock_client

    error_response = make_api_error(503, "UNAVAILABLE: Temporary spike", "UNAVAILABLE")
    success_response = MagicMock()
    success_response.text = "Subsequent request succeeded without issues.\n\nSOURCES_USED: NONE"

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[]):
            # Request 1: Fails
            mock_client.models.generate_content.side_effect = error_response
            with pytest.raises(HTTPException) as exc:
                rag.answer_question("Question 1")
            assert exc.value.status_code == 503

            # Request 2: Succeeds immediately
            mock_client.models.generate_content.side_effect = None
            mock_client.models.generate_content.return_value = success_response
            ans, sources = rag.answer_question("Question 2")
            assert "Subsequent request succeeded" in ans
            assert sources == []
