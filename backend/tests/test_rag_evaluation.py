import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from app.core.config import DATA_DIR, RAG_MAX_COSINE_DISTANCE, RAG_SCORE_MARGIN
from app.schemas.chat import SourceCitation
from app.services.rag import (
    RAGService,
    extract_substantive_tokens,
    is_source_location_query,
    verify_citation_grounding,
)
from app.services.vector_store import VectorStoreService


@pytest.fixture
def eval_dataset():
    dataset_file = DATA_DIR / "evaluation_dataset.json"
    assert dataset_file.exists(), f"Evaluation dataset not found at {dataset_file}"
    with open(dataset_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@pytest.fixture
def isolated_vector_store(tmp_path):
    """Isolated Chroma store with representative ASTU chunks across categories."""
    store = VectorStoreService(persist_dir=tmp_path / "chroma_eval_store")

    documents = [
        # Student Services
        "The Office of the Dean of Student Services specifically provides: Cafeteria Services, Dormitory Services, and Health Services Clinic.",
        # Registrar General
        "Registrar and Alumni Executive directives and guidelines on students: admission, registration, and graduation guidelines.",
        # Registrar Contact (Exact Person)
        "Registrar and Alumni Executive Contact: Dr. Abebe Girma Regassa, Assistant Professor of Applied Mathematics.",
        # Active Calendar 2026/2027
        "Available Calendars: Grade submission 2026/2027 First Semester begins October 15, 2026. Final exams January 11, 2027.",
        # Active Calendar Readmission/Withdrawal
        "Readmission 2026/2027 First Semester: deadline October 17, 2026. Course Withdrawal deadline October 30, 2026.",
        # Historical Calendar (2023/2024)
        "Historical Academic Calendar 2023/2024 (2016 E.C.): archived reference schedules.",
        # Generic Institutional Homepage
        "Former Students of ASTU visit their University. ASTU conducts orientation sessions and collaborates on technological innovation.",
    ]

    metadatas = [
        {"doc_id": "doc_ss", "source_title": "Dean of Student Services", "source_url": "https://www.astu.edu.et/student-services", "academic_year": ""},
        {"doc_id": "doc_reg_gen", "source_title": "ASTU Registrar and Alumni Executive", "source_url": "https://www.astu.edu.et/registrar", "academic_year": ""},
        {"doc_id": "doc_reg_contact", "source_title": "ASTU Registrar and Alumni Executive", "source_url": "https://www.astu.edu.et/registrar", "academic_year": ""},
        {"doc_id": "doc_cal_active", "source_title": "ASTU Active Calendars Portal", "source_url": "https://portal.astu.edu.et/pages/active_calendars", "academic_year": "2026/2027"},
        {"doc_id": "doc_cal_dates", "source_title": "ASTU Active Calendars Portal", "source_url": "https://portal.astu.edu.et/pages/active_calendars", "academic_year": "2026/2027"},
        {"doc_id": "doc_cal_old", "source_title": "ASTU Academic Calendar", "source_url": "https://www.astu.edu.et/calendar-archive", "academic_year": "2023/2024"},
        {"doc_id": "doc_home", "source_title": "ASTU Homepage", "source_url": "https://www.astu.edu.et/", "academic_year": ""},
    ]

    ids = [f"eval_chunk_{i}" for i in range(len(documents))]

    # Mock embeddings: 7 vectors with known similarity spaces
    embeddings = [
        [0.9, 0.1, 0.0, 0.0],  # doc_ss
        [0.1, 0.9, 0.0, 0.0],  # doc_reg_gen
        [0.15, 0.85, 0.1, 0.0], # doc_reg_contact
        [0.0, 0.2, 0.9, 0.0],  # doc_cal_active
        [0.05, 0.25, 0.85, 0.0],# doc_cal_dates
        [0.0, 0.3, 0.8, 0.0],  # doc_cal_old
        [0.5, 0.5, 0.5, 0.0],  # doc_home
    ]

    store.collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    return store


# ---------------------------------------------------------------------------
# 1. Evaluation Dataset Structure & Category Coverage
# ---------------------------------------------------------------------------

def test_evaluation_dataset_structure_and_completeness(eval_dataset):
    """Ensure evaluation dataset covers all required ASTU domains and schemas."""
    assert len(eval_dataset) >= 15, "Evaluation dataset must contain at least 15 representative cases."

    required_categories = {
        "student_services",
        "admissions_and_registration",
        "official_contacts",
        "academic_procedures",
        "campus_facilities",
        "departments_and_programs",
        "general_student_advice",
        "unindexed_missing_info",
    }
    present_categories = {item["category"] for item in eval_dataset}
    assert required_categories.issubset(present_categories), f"Missing categories: {required_categories - present_categories}"

    for item in eval_dataset:
        assert "id" in item
        assert "query" in item and len(item["query"]) > 5
        assert item["expected_behavior"] in ("answer", "qualify", "abstain")
        assert "expected_sources" in item
        assert "manual_verification_status" in item


# ---------------------------------------------------------------------------
# 2. Hybrid Retrieval: Precision and Noise Filtering
# ---------------------------------------------------------------------------

def test_hybrid_retrieval_filters_borderline_noise_for_unindexed_query(isolated_vector_store):
    """
    When an unindexed question (e.g. bookstore) has borderline distance (>=0.28)
    and zero substantive keyword overlap with chunks, noise chunks are filtered out.
    """
    query = "Where is the campus bookstore located at ASTU?"
    query_tokens = extract_substantive_tokens(query)
    # Mock embedding with borderline distance (~0.306) to doc_home
    mock_emb = [0.40, 0.40, 0.40, 0.72]

    results = isolated_vector_store.similarity_search(
        query_embedding=mock_emb,
        top_k=4,
        max_distance=0.38,
        query_tokens=query_tokens,
        is_navigational=False,
    )

    # Chunks with 0 overlap with {'bookstore', 'located'} must be rejected as noise
    assert len(results) == 0, f"Expected 0 chunks for unindexed query, got: {results}"


def test_hybrid_retrieval_retains_chunks_with_substantive_overlap(isolated_vector_store):
    """
    Queries matching legitimate knowledge (e.g. withdrawal deadline) retain their chunks
    due to substantive keyword overlap ('withdrawal').
    """
    query = "What is the official deadline for student withdrawal?"
    query_tokens = extract_substantive_tokens(query)
    mock_emb = [0.05, 0.25, 0.85, 0.0]  # Matches doc_cal_dates closely

    results = isolated_vector_store.similarity_search(
        query_embedding=mock_emb,
        top_k=4,
        max_distance=0.38,
        query_tokens=query_tokens,
        is_navigational=False,
    )

    assert len(results) >= 1
    top_meta = results[0]["metadata"]
    assert "Active Calendars" in top_meta["source_title"]
    assert results[0]["token_overlap"] >= 1


def test_hybrid_scoring_ranks_exact_contact_above_generic_prose(isolated_vector_store):
    """
    Exact keyword overlap on Dr. Abebe Girma Regassa elevates the contact chunk
    above generic institutional text.
    """
    query = "Who is the Registrar and Alumni Executive at ASTU? Dr. Abebe Girma"
    query_tokens = extract_substantive_tokens(query)
    # Embedding is equidistant between general registrar chunk and contact chunk
    mock_emb = [0.125, 0.875, 0.05, 0.0]

    results = isolated_vector_store.similarity_search(
        query_embedding=mock_emb,
        top_k=4,
        max_distance=0.38,
        query_tokens=query_tokens,
        is_navigational=False,
    )

    assert len(results) >= 1
    # Top chunk must be the one with Dr. Abebe Girma Regassa
    assert "Dr. Abebe Girma Regassa" in results[0]["text"]
    assert results[0]["token_overlap"] >= 2


# ---------------------------------------------------------------------------
# 3. Grounding Verification & Unsupported Claims
# ---------------------------------------------------------------------------

def test_unsupported_factual_claim_drops_citation():
    """
    If the model claims a fact not in the chunk (e.g. invented swimming pool),
    verify_citation_grounding rejects the citation.
    """
    chunk_text = "The Dean of Student Services provides Cafeteria, Dormitory, and Health Services."
    hallucinated_reply = "ASTU provides an Olympic swimming pool and equestrian club.\n\nSOURCES_USED: [1]"

    grounded = verify_citation_grounding(
        chunk_text=chunk_text,
        reply_text=hallucinated_reply,
        source_title="Dean of Student Services",
        source_url="https://www.astu.edu.et/student-services",
        question="Does ASTU have a swimming pool?",
    )
    assert grounded is False


def test_supported_factual_claim_validates_citation():
    """Valid factual claims supported by chunk pass independent verification."""
    chunk_text = "The Dean of Student Services provides Cafeteria, Dormitory, and Health Services."
    factual_reply = "The Dean of Student Services provides Cafeteria Services, Dormitory accommodations, and Health Services."

    grounded = verify_citation_grounding(
        chunk_text=chunk_text,
        reply_text=factual_reply,
        source_title="Dean of Student Services",
        source_url="https://www.astu.edu.et/student-services",
        question="What services does the Dean of Student Services provide?",
    )
    assert grounded is True


# ---------------------------------------------------------------------------
# 4. Outdated / Conflicting Documents Handling
# ---------------------------------------------------------------------------

def test_outdated_calendar_chunk_rejected_when_active_calendar_requested():
    """
    When asking about 2026/2027 calendar, an old 2023/2024 chunk must not be attributed
    if the reply specifically references 2026/2027 dates.
    """
    old_chunk = "Historical Academic Calendar 2023/2024 (2016 E.C.): archived reference schedules."
    active_chunk = "Available Calendars: Grade submission 2026/2027 First Semester begins October 15, 2026."
    reply = "For the 2026/2027 first semester, grade submission begins October 15, 2026."

    assert verify_citation_grounding(old_chunk, reply, "ASTU Academic Calendar") is False
    assert verify_citation_grounding(active_chunk, reply, "ASTU Active Calendars Portal") is True


# ---------------------------------------------------------------------------
# 5. Abstention on Missing Information
# ---------------------------------------------------------------------------

def test_unindexed_query_acknowledges_missing_info_and_returns_no_sources():
    """
    When asking about an unindexed ASTU topic (e.g. international tuition fees),
    RAG service safely returns an abstention message without fake citations.
    """
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[]):
            mock_response = MagicMock()
            mock_response.text = (
                "Verified information regarding international student tuition fees is not available in the indexed sources. "
                "Please check the official ASTU portal at https://www.astu.edu.et for official fee schedules.\n\n"
                "SOURCES_USED: NONE"
            )
            mock_client.models.generate_content.return_value = mock_response

            answer, sources, diag = rag.answer_question_with_diagnostics(
                "What is the tuition fee for international students at ASTU?"
            )

            assert "not available in the indexed sources" in answer
            assert sources == []
            assert diag["grounding_status"] == "abstained"
            assert diag["retrieved_count"] == 0


# ---------------------------------------------------------------------------
# 6. Observability Diagnostics Verification
# ---------------------------------------------------------------------------

def test_rag_diagnostics_metadata_structure_and_safety():
    """Verify that diagnostics contains safe metadata without secrets."""
    rag = RAGService(api_key="fake_key", model="gemini-2.5-flash")
    mock_client = MagicMock()
    rag._client = mock_client

    chunk = {
        "id": "chunk_ss_1",
        "text": "The Dean of Student Services provides Cafeteria and Dormitory services.",
        "metadata": {
            "doc_id": "doc_ss",
            "source_title": "Dean of Student Services",
            "source_url": "https://www.astu.edu.et/student-services",
            "verification_status": "candidate",
        },
        "distance": 0.22,
        "relevance_score": 0.88,
        "token_overlap": 2,
    }

    with patch("app.services.rag.embedding_service.embed_query", return_value=[0.1, 0.2]):
        with patch("app.services.rag.vector_store.similarity_search", return_value=[chunk]):
            mock_response = MagicMock()
            mock_response.text = (
                "The Dean of Student Services manages Cafeteria and Dormitory services.\n\n"
                "SOURCES_USED: [1]"
            )
            mock_client.models.generate_content.return_value = mock_response

            _, sources, diag = rag.answer_question_with_diagnostics(
                "What services are provided by the Dean of Student Services?"
            )

            assert diag["grounding_status"] == "grounded"
            assert diag["retrieved_count"] == 1
            assert diag["citations_count"] == 1
            assert len(diag["chunks"]) == 1
            c_meta = diag["chunks"][0]
            assert c_meta["doc_id"] == "doc_ss"
            assert c_meta["distance"] == 0.22
            assert c_meta["relevance_score"] == 0.88
            assert c_meta["verification_status"] == "candidate"

            # Ensure no API keys or internal secrets are present in diagnostics
            diag_str = str(diag)
            assert "fake_key" not in diag_str
            assert "api_key" not in diag_str


# ---------------------------------------------------------------------------
# 7. Multi-Model Fallback Chain Verification
# ---------------------------------------------------------------------------

def test_multi_model_fallback_chain_executes_in_sequence():
    """Verify that comma-separated fallback models in config are parsed and attempted in sequence."""
    rag = RAGService(
        api_key="fake_key",
        model="gemini-2.5-flash",
        fallback_model="gemini-flash-latest,gemini-flash-lite-latest",
        max_retries=1,
    )
    mock_client = MagicMock()
    rag._client = mock_client

    attempted_models = []

    def mock_generate(model, contents, config=None):
        attempted_models.append(model)
        if model in ("gemini-2.5-flash", "gemini-flash-latest"):
            from google.genai.errors import APIError
            raise APIError(503, {"error": {"code": 503, "message": "High demand spike", "status": "UNAVAILABLE"}})
        resp = MagicMock()
        resp.text = "Success from lite fallback\n\nSOURCES_USED: NONE"
        return resp

    mock_client.models.generate_content.side_effect = mock_generate

    resp = rag._generate_with_retry_and_fallback("Hello")
    assert resp.text == "Success from lite fallback\n\nSOURCES_USED: NONE"
    assert "gemini-2.5-flash" in attempted_models
    assert "gemini-flash-latest" in attempted_models
    assert "gemini-flash-lite-latest" in attempted_models
