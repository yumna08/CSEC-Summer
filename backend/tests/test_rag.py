from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from app.services.rag import RAGService


def test_rag_missing_api_key():
    rag = RAGService(api_key="", model="gemini-2.5-flash")
    with pytest.raises(HTTPException) as exc:
        rag.answer_question("What is ASTU?")
    assert exc.value.status_code == 503
    assert "Gemini API key is not configured" in exc.value.detail


def test_rag_empty_question():
    rag = RAGService(api_key="test_key", model="gemini-2.5-flash")
    with pytest.raises(HTTPException) as exc:
        rag.answer_question("   ")
    assert exc.value.status_code == 422


@patch("app.services.rag.embedding_service.embed_query")
@patch("app.services.rag.vector_store.similarity_search")
def test_rag_with_retrieved_evidence(mock_search, mock_embed):
    rag = RAGService(api_key="test_key", model="gemini-2.5-flash")
    mock_embed.return_value = [0.1, 0.2, 0.3]
    mock_search.return_value = [
        {
            "text": "Registration for the 2024/2025 academic year starts on October 20.",
            "metadata": {
                "source_title": "ASTU Academic Calendar",
                "source_url": "https://www.astu.edu.et/calendar",
                "document_name": "calendar.html",
                "academic_year": "2024/2025",
                "publication_date": "October 1, 2024",
            },
            "distance": 0.15,
            "relevance_score": 0.85,
        }
    ]

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "According to the ASTU Academic Calendar, registration starts on October 20 for 2024/2025."
    mock_client.models.generate_content.return_value = mock_response

    with patch.object(rag, "_client", mock_client):
        answer, sources = rag.answer_question("When does registration begin?")

        assert "October 20" in answer
        assert len(sources) == 1
        assert sources[0].title == "ASTU Academic Calendar"
        assert sources[0].url == "https://www.astu.edu.et/calendar"
        assert sources[0].academic_year == "2024/2025"

        # Check prompt grounding instructions in the mock call
        call_args = mock_client.models.generate_content.call_args
        assert "Retrieved Verified ASTU Reference Material" in call_args.kwargs["contents"]


@patch("app.services.rag.embedding_service.embed_query")
@patch("app.services.rag.vector_store.similarity_search")
def test_rag_no_relevant_evidence_fallback(mock_search, mock_embed):
    rag = RAGService(api_key="test_key", model="gemini-2.5-flash")
    mock_embed.return_value = [0.1, 0.2, 0.3]
    mock_search.return_value = []  # No chunks above threshold

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = (
        "Here are general exam preparation tips: 1. Create a schedule. "
        "For official ASTU exam schedules, please verify on the official portal."
    )
    mock_client.models.generate_content.return_value = mock_response

    with patch.object(rag, "_client", mock_client):
        answer, sources = rag.answer_question("How can I prepare for exams?")

        assert "general exam preparation tips" in answer
        assert len(sources) == 0  # No fabricated sources


@patch("app.services.rag.embedding_service.embed_query")
@patch("app.services.rag.vector_store.similarity_search")
def test_rag_gemini_api_failure_handled(mock_search, mock_embed):
    rag = RAGService(api_key="test_key", model="gemini-2.5-flash")
    mock_embed.return_value = [0.1, 0.2, 0.3]
    mock_search.return_value = []

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("Google Cloud Internal Error")

    with patch.object(rag, "_client", mock_client):
        with pytest.raises(HTTPException) as exc:
            rag.answer_question("What is ASTU?")
        assert exc.value.status_code == 502
        assert "temporarily unavailable" in exc.value.detail
