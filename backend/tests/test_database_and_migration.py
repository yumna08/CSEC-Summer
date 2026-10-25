import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import (
    Base,
    get_engine,
    normalize_database_url,
    reset_engine_for_testing,
)
from app.db.init_db import init_db
from app.db.migrate_json_to_postgres import (
    migrate_documents,
    migrate_json_to_postgres,
    migrate_sources,
    parse_iso_datetime,
    validate_migration,
)
from app.db.models import IngestionJob, KnowledgeDocument, KnowledgeSource
from app.schemas.knowledge import DocumentMetadata, VerificationStatus
from app.services.registry import SourceRegistry
from app.services.vector_store import VectorStoreService


@pytest.fixture
def test_db_engine():
    """Create a completely isolated in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def test_session_factory(test_db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)


# -----------------------------------------------------------------------------
# Database Configuration & URL Tests
# -----------------------------------------------------------------------------
def test_normalize_database_url():
    # Empty
    assert normalize_database_url("") == ""
    assert normalize_database_url("   ") == ""

    # postgres:// to postgresql+psycopg://
    assert normalize_database_url("postgres://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"

    # postgresql:// to postgresql+psycopg://
    assert normalize_database_url("postgresql://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"

    # already postgresql+psycopg://
    assert normalize_database_url("postgresql+psycopg://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"

    # sqlite unchanged
    assert normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_missing_database_url():
    with patch.dict(os.environ, {"DATABASE_URL": ""}):
        reset_engine_for_testing(None)
        with pytest.raises(RuntimeError) as exc_info:
            get_engine()
        assert "DATABASE_URL is not configured" in str(exc_info.value)
    reset_engine_for_testing(None)


# -----------------------------------------------------------------------------
# Schema Initialization Tests
# -----------------------------------------------------------------------------
def test_init_db_creates_expected_tables(test_db_engine):
    tables = init_db(test_db_engine)
    assert "knowledge_sources" in tables
    assert "knowledge_documents" in tables
    assert "ingestion_jobs" in tables


# -----------------------------------------------------------------------------
# JSON to PostgreSQL Migration Tests
# -----------------------------------------------------------------------------
def test_json_to_postgres_migration(test_session_factory, tmp_path):
    sources_data = [
        {
            "url": "https://www.astu.edu.et/",
            "title": "ASTU Homepage",
            "description": "Adama Science and Technology University portal.",
            "verification_status": "candidate",
            "added_at": "2026-10-18T09:59:18.836145+00:00",
            "last_checked": "2026-10-18T10:38:35.697241+00:00",
            "last_status": "unchanged",
            "error_message": None,
        },
        {
            "url": "https://www.astu.edu.et/calendar",
            "title": "ASTU Calendar",
            "description": "Academic dates and deadlines.",
            "verification_status": "verified",
            "added_at": "2026-10-18T09:59:18.836145+00:00",
            "last_checked": None,
            "last_status": "pending",
            "error_message": None,
        },
    ]

    docs_data = {
        "web_001": {
            "doc_id": "web_001",
            "source_url": "https://www.astu.edu.et/",
            "source_title": "ASTU Homepage",
            "source_type": "webpage",
            "document_name": "homepage.html",
            "content_hash": "hash_12345",
            "fetched_at": "2026-10-18T10:14:10.014057+00:00",
            "academic_year": "2024/2025",
            "publication_date": "September 30, 2026",
            "verification_status": "candidate",
            "chunk_count": 4,
            "requires_ocr": False,
            "error_message": None,
        },
        "file_002": {
            "doc_id": "file_002",
            "source_url": "https://www.astu.edu.et/notice.pdf",
            "source_title": "notice.pdf",
            "source_type": "pdf",
            "document_name": "notice.pdf",
            "content_hash": "hash_67890",
            "fetched_at": "2026-10-18T10:39:29.191843+00:00",
            "academic_year": None,
            "publication_date": None,
            "verification_status": "candidate",
            "chunk_count": 0,
            "requires_ocr": True,
            "error_message": "Scanned PDF requiring OCR.",
        },
    }

    sources_file = tmp_path / "test_sources.json"
    catalog_file = tmp_path / "test_catalog.json"
    with open(sources_file, "w", encoding="utf-8") as f:
        json.dump(sources_data, f)
    with open(catalog_file, "w", encoding="utf-8") as f:
        json.dump(docs_data, f)

    # 1. First migration run
    with test_session_factory() as session:
        with session.begin():
            src_res = migrate_sources(session, sources_data)
            doc_res = migrate_documents(session, docs_data)

        assert src_res["read"] == 2
        assert src_res["inserted"] == 2
        assert src_res["updated"] == 0

        assert doc_res["read"] == 2
        assert doc_res["inserted"] == 2
        assert doc_res["updated"] == 0

        # Validate records in DB
        val = validate_migration(session, sources_data, docs_data)
        assert val["sources_valid"] is True
        assert val["documents_valid"] is True
        assert val["sources_checked"] == 2
        assert val["documents_checked"] == 2
        assert len(val["mismatches"]) == 0

        # Check total rows
        db_sources = session.execute(select(KnowledgeSource)).scalars().all()
        db_docs = session.execute(select(KnowledgeDocument)).scalars().all()
        assert len(db_sources) == 2
        assert len(db_docs) == 2

    # 2. Rerun migration to verify idempotency and duplicate prevention
    with test_session_factory() as session:
        with session.begin():
            src_res2 = migrate_sources(session, sources_data)
            doc_res2 = migrate_documents(session, docs_data)

        assert src_res2["inserted"] == 0
        assert src_res2["updated"] == 2

        assert doc_res2["inserted"] == 0
        assert doc_res2["updated"] == 2

        # Row counts must still be exactly 2
        db_sources2 = session.execute(select(KnowledgeSource)).scalars().all()
        db_docs2 = session.execute(select(KnowledgeDocument)).scalars().all()
        assert len(db_sources2) == 2
        assert len(db_docs2) == 2


# -----------------------------------------------------------------------------
# Source Registry CRUD Tests
# -----------------------------------------------------------------------------
def test_source_registry_crud(test_session_factory):
    registry = SourceRegistry(session_factory=test_session_factory)

    # 1. Initial seeds populated
    sources = registry.get_sources()
    assert len(sources) >= 5
    urls = [s["url"] for s in sources]
    assert "https://www.astu.edu.et/" in urls

    # 2. Add new source
    new_s = registry.add_source(
        url="https://www.astu.edu.et/library",
        title="ASTU Library",
        description="Main campus library portal.",
        verification_status="verified",
    )
    assert new_s["url"] == "https://www.astu.edu.et/library"
    assert new_s["verification_status"] == "verified"

    # 3. Update existing source (case-insensitive)
    updated_s = registry.add_source(
        url="HTTPS://WWW.ASTU.EDU.ET/LIBRARY",
        title="ASTU Main Library Updated",
    )
    assert updated_s["title"] == "ASTU Main Library Updated"

    # 4. Update status
    registry.update_source_status(
        url="https://www.astu.edu.et/library",
        status="success",
        title="ASTU Main Library Active",
    )
    with test_session_factory() as session:
        src = session.execute(
            select(KnowledgeSource).where(KnowledgeSource.url == "https://www.astu.edu.et/library")
        ).scalar_one()
        assert src.last_status == "success"
        assert src.title == "ASTU Main Library Active"
        assert src.last_checked is not None


# -----------------------------------------------------------------------------
# Vector Store Document Metadata CRUD Tests
# -----------------------------------------------------------------------------
def test_vector_store_metadata_crud(test_session_factory, tmp_path):
    store = VectorStoreService(
        persist_dir=tmp_path / "chroma_db",
        session_factory=test_session_factory,
    )

    meta = DocumentMetadata(
        doc_id="doc_test_01",
        source_url="https://www.astu.edu.et/info",
        source_title="Campus Info",
        source_type="webpage",
        document_name="info.html",
        content_hash="hash_alpha",
        academic_year="2025/2026",
        publication_date="October 2025",
        verification_status=VerificationStatus.CANDIDATE.value,
        chunk_count=2,
    )

    # 1. Record document status
    store.record_document_status(meta)

    # 2. Retrieve document
    retrieved = store.get_document("doc_test_01")
    assert retrieved is not None
    assert retrieved.doc_id == "doc_test_01"
    assert retrieved.source_title == "Campus Info"
    assert retrieved.academic_year == "2025/2026"
    assert retrieved.chunk_count == 2

    # 3. List documents
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0].doc_id == "doc_test_01"

    # 4. Update status
    meta.chunk_count = 5
    meta.verification_status = VerificationStatus.VERIFIED.value
    store.record_document_status(meta)
    updated = store.get_document("doc_test_01")
    assert updated.chunk_count == 5
    assert updated.verification_status == "verified"

    # 5. Delete document
    deleted_count = store.delete_document("doc_test_01")
    assert deleted_count == 5
    assert store.get_document("doc_test_01") is None
    assert len(store.list_documents()) == 0


# -----------------------------------------------------------------------------
# Ingestion Job Logging Tests
# -----------------------------------------------------------------------------
def test_ingestion_job_logging(test_session_factory):
    with test_session_factory() as session:
        job = IngestionJob(
            job_type="websites",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(job)
        session.commit()
        job_id = job.id
        assert job_id is not None

        # Complete job
        job.status = "completed"
        job.total_attempted = 5
        job.successful = 4
        job.failed = 1
        job.completed_at = datetime.now(timezone.utc)
        session.commit()

        # Query
        reloaded = session.execute(
            select(IngestionJob).where(IngestionJob.id == job_id)
        ).scalar_one()
        assert reloaded.status == "completed"
        assert reloaded.successful == 4
        assert reloaded.failed == 1
