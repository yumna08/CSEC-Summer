
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import (
    RAG_MAX_COSINE_DISTANCE,
    RAG_RELEVANCE_THRESHOLD,
    RAG_SCORE_MARGIN,
)
from app.schemas.chat import SourceCitation
from app.services.rag import (
    RAGService,
    extract_citations_and_clean_reply,
    is_source_location_query,
    parse_source_indices,
    verify_citation_grounding,
    verify_factual_grounding,
    verify_navigational_grounding,
)
from app.services.vector_store import VectorStoreService
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def test_vector_store(tmp_path):
    """Create an isolated Chroma store with representative test documents."""
    store = VectorStoreService(persist_dir=tmp_path / "chroma_test_quality")

    store.collection.add(
        ids=[
            "chunk_student_services",
            "chunk_calendar",
            "chunk_symposium_noise",
        ],
        documents=[
            (
                "The Office of the Dean of Student Services provides "
                "Cafeteria Services, Dormitory Services, and Health Services."
            ),
            (
                "Active Calendars 2026/2027 First Semester: Grade submission "
                "begins October 15, Final Exams from January 11 to January 22."
            ),
            (
                "Abstract Template 5th International Research Symposium ASTU: "
                "Manuscripts must be submitted in MS Word format (.doc or .docx)."
            ),
        ],
        metadatas=[
            {
                "source_title": "Dean of Student Services",
                "source_url": "https://www.astu.edu.et/student-services",
                "doc_id": "doc_ss",
            },
            {
                "source_title": "ASTU Active Calendars Portal",
                "source_url": "https://portal.astu.edu.et/pages/active_calendars",
                "doc_id": "doc_cal",
            },
            {
                "source_title": "Abstract Template 5th International Research Symposium",
                "source_url": "https://www.astu.edu.et/symposium.pdf",
                "doc_id": "doc_symp",
            },
        ],
        embeddings=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.5, 0.5, 0.7],
        ],
    )

    return store


# ---------------------------------------------------------------------------
# Part A: Retrieval threshold configuration
# ---------------------------------------------------------------------------

def test_rag_threshold_configuration_is_valid():
    """Ensure retrieval settings use sensible ranges."""
    assert 0 < RAG_MAX_COSINE_DISTANCE <= 2
    assert RAG_SCORE_MARGIN >= 0
    assert RAG_RELEVANCE_THRESHOLD >= 0


def test_vector_store_fixture_contains_representative_chunks(test_vector_store):
    """Verify that the isolated vector store was populated."""
    assert test_vector_store.collection.count() == 3


# ---------------------------------------------------------------------------
# Part B: Citation index parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw_tag", "max_valid_index", "expected"),
    [
        ("1, 2", 3, [1, 2]),
        ("[1, 2]", 3, [1, 2]),
        ("1, 1, 2", 3, [1, 2]),
        ("bad_token, -1, 0, 999, 1, 1", 3, [1]),
        ("NONE", 3, []),
        ("EMPTY", 3, []),
        ("N/A", 3, []),
        ("[]", 3, []),
        ("", 3, []),
        ("3, 2, 1", 3, [3, 2, 1]),
        ("4, 5", 3, []),
    ],
)
def test_parse_source_indices(raw_tag, max_valid_index, expected):
    """Validate, deduplicate, and preserve the order of valid citation indices."""
    assert parse_source_indices(raw_tag, max_valid_index) == expected


# ---------------------------------------------------------------------------
# Part C: Independent citation grounding
# ---------------------------------------------------------------------------

def test_independent_citation_grounding_verification():
    """Verify that citations support factual claims in the answer."""
    chunk_text = (
        "The Office of the Dean of Student Services provides Cafeteria "
        "Services, Dormitory Services, and Health Services."
    )
    valid_reply = (
        "The Dean of Student Services at ASTU oversees Cafeteria, "
        "Dormitory, and Health Services for students."
    )

    assert (
        verify_citation_grounding(
            chunk_text, valid_reply, "Dean of Student Services"
        )
        is True
    )

    hallucinated_reply = (
        "To prepare for exams, create a timetable, get enough sleep, "
        "and practice previous questions."
    )
    assert (
        verify_citation_grounding(
            chunk_text, hallucinated_reply, "Dean of Student Services"
        )
        is False
    )

    cal_chunk = (
        "Final Exams are scheduled from January 11 to January 22, 2027 "
        "on the active academic calendar."
    )
    cal_reply = (
        "According to official records, Final Exams run from "
        "January 11 to January 22, 2027."
    )

    assert (
        verify_citation_grounding(
            cal_chunk, cal_reply, "ASTU Active Calendars Portal"
        )
        is True
    )

    assert verify_citation_grounding("", "Some reply") is False
    assert verify_citation_grounding(chunk_text, "") is False


def test_homepage_url_is_not_enough_to_validate_unrelated_claims():
    """A homepage URL or title alone must not validate unrelated factual advice."""
    homepage_chunk = (
        "ASTU conducts orientation sessions and publishes university news."
    )
    unrelated_reply = (
        "To prepare for exams, create a timetable, get enough sleep, "
        "and practice previous questions."
    )

    assert (
        verify_citation_grounding(
            homepage_chunk,
            unrelated_reply,
            "ASTU Homepage",
        )
        is False
    )


def test_rag_rejects_hallucinated_model_citation_when_unsupported_by_chunk():
    """Reject a model citation when the retrieved chunk does not support the answer."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    symposium_chunk = {
        "text": (
            "Abstract Template 5th International Research Symposium ASTU: "
            "Manuscripts must be submitted in MS Word format (.doc or .docx)."
        ),
        "metadata": {
            "source_title": "Abstract Template 5th International Research Symposium",
            "source_url": "https://www.astu.edu.et/symposium.pdf",
            "document_name": "symposium.pdf",
            "academic_year": None,
            "publication_date": None,
        },
        "distance": 0.36,
        "relevance_score": 0.64,
    }

    with patch(
        "app.services.rag.embedding_service.embed_query",
        return_value=[0.1, 0.2],
    ):
        with patch(
            "app.services.rag.vector_store.similarity_search",
            return_value=[symposium_chunk],
        ):
            mock_response = MagicMock()
            mock_response.text = (
                "To prepare for exams effectively, start early, create a study "
                "schedule, review lecture slides, and practice with past exam papers.\n\n"
                "SOURCES_USED: [1]"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question(
                "How can I prepare for exams?"
            )

            assert "prepare for exams effectively" in answer
            assert "SOURCES_USED" not in answer
            assert sources == []


def test_rag_handles_malformed_duplicated_and_out_of_range_source_tags():
    """Verify that malformed, negative, out-of-range, and duplicate indices are handled."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    mock_chunk = {
        "text": (
            "The Office of the Dean of Student Services provides Cafeteria "
            "Services, Dormitory Services, and Health Services."
        ),
        "metadata": {
            "source_title": "Dean of Student Services",
            "source_url": "https://www.astu.edu.et/student-services",
            "document_name": "dean-of-student-services.html",
        },
        "distance": 0.22,
        "relevance_score": 0.78,
    }

    with patch(
        "app.services.rag.embedding_service.embed_query",
        return_value=[0.1, 0.2],
    ):
        with patch(
            "app.services.rag.vector_store.similarity_search",
            return_value=[mock_chunk],
        ):
            mock_response = MagicMock()
            mock_response.text = (
                "The Dean of Student Services provides Cafeteria and Health Services.\n\n"
                "SOURCES_USED: [bad_token, -1, 0, 999, 1, 1]"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question(
                "What services are provided?"
            )

            assert "Cafeteria and Health Services" in answer
            assert len(sources) == 1
            assert sources[0].title == "Dean of Student Services"


def test_rag_fallback_when_tag_omitted_verifies_grounding():
    """When the model omits its citation tag, only grounded sources are included."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    grounded_chunk = {
        "text": (
            "The Office of the Dean of Student Services provides "
            "Cafeteria Services and Dormitory Services."
        ),
        "metadata": {
            "source_title": "Dean of Student Services",
            "source_url": "https://www.astu.edu.et/ss",
        },
        "distance": 0.20,
    }
    ungrounded_chunk = {
        "text": "Research Symposium Abstract Template formatting guidelines for MS Word.",
        "metadata": {
            "source_title": "Symposium Template",
            "source_url": "https://www.astu.edu.et/symp",
        },
        "distance": 0.25,
    }

    with patch(
        "app.services.rag.embedding_service.embed_query",
        return_value=[0.1, 0.2],
    ):
        with patch(
            "app.services.rag.vector_store.similarity_search",
            return_value=[grounded_chunk, ungrounded_chunk],
        ):
            mock_response = MagicMock()
            mock_response.text = (
                "The Dean of Student Services manages Cafeteria and "
                "Dormitory accommodations for students."
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question(
                "Where can I find dormitory services?"
            )

            assert len(sources) == 1
            assert sources[0].title == "Dean of Student Services"


def test_regression_general_study_tips_no_spurious_sources():
    """General study advice must not cite unrelated ASTU documents."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    with patch(
        "app.services.rag.embedding_service.embed_query",
        return_value=[0.1, 0.2],
    ):
        with patch(
            "app.services.rag.vector_store.similarity_search",
            return_value=[],
        ):
            mock_response = MagicMock()
            mock_response.text = (
                "Here are general exam preparation tips: Start early, plan a "
                "schedule, practice with past problems, and maintain a healthy "
                "sleep cycle.\n\nSOURCES_USED: NONE"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question(
                "How can I prepare for exams?"
            )

            assert "general exam preparation tips" in answer
            assert "SOURCES_USED" not in answer
            assert sources == []


# ---------------------------------------------------------------------------
# Part D: Task 6 Regression Tests
# ---------------------------------------------------------------------------

def test_factual_answer_supported_by_retrieved_astu_document_returns_citation():
    """1. A factual answer supported by a retrieved ASTU document returns the correct citation."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    ss_chunk = {
        "text": (
            "The Office of the Dean of Student Services provides Cafeteria "
            "Services, Dormitory Services, and Student Health Clinic Services."
        ),
        "metadata": {
            "source_title": "Dean of Student Services",
            "source_url": "https://www.astu.edu.et/student-services",
            "document_name": "dean-student-services.html",
            "academic_year": None,
            "publication_date": None,
            "verification_status": "approved",
        },
        "distance": 0.21,
        "relevance_score": 0.79,
    }

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[ss_chunk]):
            mock_response = MagicMock()
            mock_response.text = (
                "The Dean of Student Services at ASTU provides Cafeteria, "
                "Dormitory, and Student Health Clinic services.\n\n"
                "SOURCES_USED: [1]"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question("What services does Dean of Student Services provide?")

            assert "Cafeteria, Dormitory, and Student Health Clinic" in answer
            assert "SOURCES_USED" not in answer
            assert len(sources) == 1
            assert sources[0].title == "Dean of Student Services"
            assert sources[0].url == "https://www.astu.edu.et/student-services"
            assert sources[0].verification_status == "approved"


def test_unsupported_factual_claim_does_not_receive_citation():
    """2. An unsupported factual claim does not receive a citation."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    chunk = {
        "text": "ASTU offers engineering and technology degree programs with accreditation.",
        "metadata": {
            "source_title": "Academic Programs Overview",
            "source_url": "https://www.astu.edu.et/programs",
            "document_name": "programs.html",
        },
        "distance": 0.28,
        "relevance_score": 0.72,
    }

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[chunk]):
            mock_response = MagicMock()
            # Model hallucinates a specific date/tuition not in the chunk
            mock_response.text = (
                "Undergraduate tuition fees are exactly 5,000 ETB per semester starting next month.\n\n"
                "SOURCES_USED: [1]"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question("How much is undergraduate tuition?")

            assert "tuition fees" in answer
            assert "SOURCES_USED" not in answer
            assert sources == []


def test_source_location_question_returns_official_navigation_link():
    """3. A source-location question returns an appropriate official navigation link without false claims."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    homepage_chunk = {
        "text": "ASTU conducts student orientation and disseminates university announcements.",
        "metadata": {
            "source_title": "ASTU Homepage",
            "source_url": "https://www.astu.edu.et/",
            "document_name": "https://www.astu.edu.et/",
            "verification_status": "candidate",
        },
        "distance": 0.31,
        "relevance_score": 0.69,
    }
    symposium_chunk = {
        "text": "Abstract Template 5th International Research Symposium ASTU formatting guidelines.",
        "metadata": {
            "source_title": "Research Symposium Template",
            "source_url": "https://www.astu.edu.et/symposium.pdf",
            "document_name": "symposium.pdf",
            "verification_status": "candidate",
        },
        "distance": 0.34,
        "relevance_score": 0.66,
    }

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[homepage_chunk, symposium_chunk]):
            mock_response = MagicMock()
            mock_response.text = (
                "You can find official ASTU information on the university's official website at https://www.astu.edu.et/.\n\n"
                "SOURCES_USED: [1, 2]"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question("Where can I find official ASTU information?")

            assert "https://www.astu.edu.et/" in answer
            assert "SOURCES_USED" not in answer
            # Only the official homepage is accepted; the symposium document is rejected
            assert len(sources) == 1
            assert sources[0].title == "ASTU Homepage"
            assert sources[0].url == "https://www.astu.edu.et/"


def test_general_study_advice_does_not_cite_unrelated_retrieved_documents():
    """4. General study advice does not cite unrelated ASTU documents even if retrieved."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    homepage_chunk = {
        "text": "ASTU conducts student orientation and disseminates university announcements.",
        "metadata": {
            "source_title": "ASTU Homepage",
            "source_url": "https://www.astu.edu.et/",
        },
        "distance": 0.32,
    }

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[homepage_chunk]):
            mock_response = MagicMock()
            mock_response.text = (
                "Here are proven study techniques: Use the Pomodoro technique, summarize lecture "
                "notes in your own words, and practice past exam problems.\n\n"
                "SOURCES_USED: [1]"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question("How can I study effectively for university exams?")

            assert "Pomodoro technique" in answer
            assert "SOURCES_USED" not in answer
            assert sources == []


def test_extract_and_parse_citation_tags_with_markdown_punctuation_and_prose():
    """5. Missing, malformed, duplicated, negative, and out-of-range citation indices are handled safely."""
    # Bold with period
    clean1, tag1 = extract_citations_and_clean_reply("Here is your answer.\n\n**SOURCES_USED:** [1, 2].")
    assert clean1 == "Here is your answer."
    assert parse_source_indices(tag1, 3) == [1, 2]

    # Bold brackets
    clean2, tag2 = extract_citations_and_clean_reply("Here is your answer.\n\n**SOURCES_USED: [1, 2]**")
    assert clean2 == "Here is your answer."
    assert parse_source_indices(tag2, 3) == [1, 2]

    # Trailing polite prose after marker
    clean3, tag3 = extract_citations_and_clean_reply("Here is your answer.\n\nSOURCES_USED: [1]\nI hope this was helpful!")
    assert clean3 == "Here is your answer."
    assert parse_source_indices(tag3, 3) == [1]

    # Malformed indices
    assert parse_source_indices("[-1, 0, 999, bad, 2, 2]", 3) == [2]
    assert parse_source_indices("NONE", 3) == []
    assert parse_source_indices("", 3) == []


def test_gemini_omitting_citation_marker_follows_safe_fallback_path():
    """6. Gemini omitting the citation marker follows a safe fallback path."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    grounded_chunk = {
        "text": "The Dean of Student Services provides Cafeteria Services and Dormitory accommodations.",
        "metadata": {
            "source_title": "Dean of Student Services",
            "source_url": "https://www.astu.edu.et/student-services",
        },
        "distance": 0.20,
    }
    ungrounded_chunk = {
        "text": "Research Symposium submission details and manuscript formatting guidelines.",
        "metadata": {
            "source_title": "Symposium Guidelines",
            "source_url": "https://www.astu.edu.et/symposium.pdf",
        },
        "distance": 0.25,
    }

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[grounded_chunk, ungrounded_chunk]):
            mock_response = MagicMock()
            # Model completely omits the SOURCES_USED marker
            mock_response.text = (
                "The Dean of Student Services manages Cafeteria Services and Dormitory accommodations."
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question("Where can I get dormitory accommodations?")

            assert len(sources) == 1
            assert sources[0].title == "Dean of Student Services"


def test_candidate_sources_not_incorrectly_presented_as_verified():
    """7. Candidate sources are not incorrectly presented as verified sources."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    candidate_chunk = {
        "text": "ASTU student portal allows checking grades and registered courses.",
        "metadata": {
            "source_title": "Student Portal Guide",
            "source_url": "https://portal.astu.edu.et/",
            "verification_status": "candidate",
        },
        "distance": 0.22,
    }

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[candidate_chunk]):
            mock_response = MagicMock()
            mock_response.text = (
                "You can check grades and registered courses on the student portal.\n\n"
                "SOURCES_USED: [1]"
            )
            mock_client.models.generate_content.return_value = mock_response

            _, sources = rag.answer_question("How do I check my grades?")

            assert len(sources) == 1
            # Must remain marked candidate, never falsely converted to verified/approved
            assert sources[0].verification_status == "candidate"


def test_empty_retrieval_results_produce_valid_answer_and_empty_sources():
    """8. Empty retrieval results produce a valid answer and an empty source list."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[]):
            mock_response = MagicMock()
            mock_response.text = (
                "I do not have verified records on this specific inquiry in the indexed campus knowledge base. "
                "Please consult the relevant department office.\n\n"
                "SOURCES_USED: NONE"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question("What is the syllabus for Course CS-9999?")

            assert "do not have verified records" in answer
            assert "SOURCES_USED" not in answer
            assert sources == []


def test_multiple_valid_citations_deduplicated_correctly():
    """9. Multiple valid citations from the same document are deduplicated correctly."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    # 3 chunks from the same document
    chunks = [
        {
            "text": "The Dean of Student Services provides Cafeteria Services.",
            "metadata": {
                "source_title": "Dean of Student Services",
                "source_url": "https://www.astu.edu.et/student-services",
                "document_name": "student-services.html",
            },
            "distance": 0.20,
        },
        {
            "text": "The Dean of Student Services also oversees Dormitory Services.",
            "metadata": {
                "source_title": "Dean of Student Services",
                "source_url": "https://www.astu.edu.et/student-services",
                "document_name": "student-services.html",
            },
            "distance": 0.22,
        },
        {
            "text": "The Dean of Student Services operates Health Services Clinic.",
            "metadata": {
                "source_title": "Dean of Student Services",
                "source_url": "https://www.astu.edu.et/student-services",
                "document_name": "student-services.html",
            },
            "distance": 0.24,
        },
    ]

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=chunks):
            mock_response = MagicMock()
            mock_response.text = (
                "The Dean of Student Services provides Cafeteria, Dormitory, and Health Services.\n\n"
                "SOURCES_USED: [1, 2, 3]"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources = rag.answer_question("What student services are available?")

            assert "Cafeteria, Dormitory, and Health Services" in answer
            assert "SOURCES_USED" not in answer
            # Cleanly deduplicated to 1 citation
            assert len(sources) == 1
            assert sources[0].title == "Dean of Student Services"
            assert sources[0].url == "https://www.astu.edu.et/student-services"


def test_existing_api_response_and_frontend_compatibility():
    """10. Existing API response and frontend source-display compatibility are preserved."""
    client = TestClient(app)

    with patch("app.main.GEMINI_API_KEY", "fake_key"):
        with patch("app.main.rag_service.answer_question") as mock_rag:
            mock_rag.return_value = (
                "You can find official ASTU information on their official website at https://www.astu.edu.et/.",
                [
                    SourceCitation(
                        title="ASTU Homepage",
                        url="https://www.astu.edu.et/",
                        document_name="https://www.astu.edu.et/",
                        snippet="Adama Science and Technology University...",
                        verification_status="candidate",
                    )
                ],
            )

            response = client.post("/api/chat", json={"message": "Where can I find official ASTU information?"})
            assert response.status_code == 200

            data = response.json()
            # Frontend relies on: data.reply and data.sources
            assert "reply" in data
            assert "https://www.astu.edu.et/" in data["reply"]
            assert "sources" in data
            assert len(data["sources"]) == 1

            source = data["sources"][0]
            # Verify frontend field requirements (title, url, snippet, verification_status)
            assert source["title"] == "ASTU Homepage"
            assert source["url"] == "https://www.astu.edu.et/"
            assert "snippet" in source
            assert source["verification_status"] == "candidate"