import tempfile
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.database import Base
from app.schemas.knowledge import DocumentMetadata, VerificationStatus
from app.services.vector_store import VectorStoreService


@pytest.fixture
def temp_vector_store(tmp_path):
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    test_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    store = VectorStoreService(
        persist_dir=tmp_path / "chroma_db",
        session_factory=test_session_factory,
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.vector_store.CATALOG_FILE", tmp_path / "catalog.json")
        yield store


def test_indexing_and_idempotency(temp_vector_store):
    meta = DocumentMetadata(
        doc_id="doc_123",
        source_url="https://www.astu.edu.et/calendar",
        source_title="ASTU Academic Calendar",
        source_type="webpage",
        document_name="calendar.html",
        content_hash="hash_v1",
        academic_year="2024/2025",
        verification_status=VerificationStatus.VERIFIED.value,
        chunk_count=2,
    )
    chunks = ["Semester 1 starts in October.", "Final exams are held in January."]
    # Mock dummy 2D embeddings for testing vector store
    embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    # 1. Initial Indexing
    res1 = temp_vector_store.index_document(meta, chunks, embeddings)
    assert res1["status"] == "indexed"
    assert res1["chunk_count"] == 2
    assert temp_vector_store.collection.count() == 2

    # 2. Repeated ingestion of UNCHANGED document
    res2 = temp_vector_store.index_document(meta, chunks, embeddings)
    assert res2["status"] == "unchanged"
    assert "content is unchanged" in res2["message"]
    # Chunk count in vector store must NOT duplicate
    assert temp_vector_store.collection.count() == 2

    # 3. Ingestion of CHANGED document (new hash and updated content)
    meta_changed = DocumentMetadata(
        doc_id="doc_123",
        source_url="https://www.astu.edu.et/calendar",
        source_title="ASTU Academic Calendar Updated",
        source_type="webpage",
        document_name="calendar.html",
        content_hash="hash_v2",  # changed hash
        academic_year="2024/2025",
        verification_status=VerificationStatus.VERIFIED.value,
        chunk_count=3,
    )
    chunks_new = ["Updated: Semester 1 starts in November.", "Midterms in December.", "Finals in February."]
    embeddings_new = [[0.2, 0.3, 0.4], [0.5, 0.6, 0.7], [0.8, 0.9, 1.0]]

    res3 = temp_vector_store.index_document(meta_changed, chunks_new, embeddings_new)
    assert res3["status"] == "indexed"
    assert res3["chunk_count"] == 3
    # Total chunks in vector store should be exactly 3 (the old 2 were purged, no stale chunks)
    assert temp_vector_store.collection.count() == 3


def test_similarity_search_and_threshold(temp_vector_store):
    meta = DocumentMetadata(
        doc_id="doc_search",
        source_title="Dean of Students",
        source_type="webpage",
        document_name="students.html",
        content_hash="hash_search",
        chunk_count=2,
    )
    chunks = [
        "Dormitory registration takes place at the student services office.",
        "The university cafeteria serves three meals daily.",
    ]
    embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

    temp_vector_store.index_document(meta, chunks, embeddings)

    # Query close to chunk 0
    results = temp_vector_store.similarity_search(
        query_embedding=[0.99, 0.01, 0.0],
        top_k=2,
        relevance_threshold=0.55,
    )
    assert len(results) >= 1
    assert "Dormitory" in results[0]["text"]
    assert results[0]["metadata"]["source_title"] == "Dean of Students"
    assert results[0]["relevance_score"] > 0.5


def test_document_deletion(temp_vector_store):
    meta = DocumentMetadata(
        doc_id="doc_to_delete",
        source_title="Temporary Notice",
        source_type="txt",
        document_name="notice.txt",
        content_hash="hash_temp",
        chunk_count=1,
    )
    temp_vector_store.index_document(meta, ["Temporary notice text."], [[0.1, 0.2, 0.3]])
    assert temp_vector_store.collection.count() == 1

    deleted = temp_vector_store.delete_document("doc_to_delete")
    assert deleted == 1
    assert temp_vector_store.collection.count() == 0
    assert temp_vector_store.get_document("doc_to_delete") is None
