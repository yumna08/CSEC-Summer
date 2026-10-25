from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from app.db.database import Base
from app.schemas.knowledge import DocumentMetadata, VerificationStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(2048), unique=True, index=True, nullable=False)
    title = Column(String(512), nullable=False, default="ASTU Source")
    description = Column(Text, nullable=True, default="")
    verification_status = Column(String(50), nullable=False, default=VerificationStatus.CANDIDATE.value)
    added_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_checked = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(50), nullable=True, default="pending")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description or "",
            "verification_status": self.verification_status,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "last_status": self.last_status,
            "error_message": self.error_message,
        }


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(64), unique=True, index=True, nullable=False)
    source_url = Column(String(2048), nullable=True, index=True)
    source_title = Column(String(512), nullable=False)
    source_type = Column(String(50), nullable=False)
    document_name = Column(String(512), nullable=False)
    content_hash = Column(String(128), nullable=False, default="")
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    academic_year = Column(String(50), nullable=True)
    publication_date = Column(String(100), nullable=True)
    verification_status = Column(String(50), nullable=False, default=VerificationStatus.CANDIDATE.value)
    chunk_count = Column(Integer, nullable=False, default=0)
    requires_ocr = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def to_metadata(self) -> DocumentMetadata:
        return DocumentMetadata(
            doc_id=self.doc_id,
            source_url=self.source_url,
            source_title=self.source_title,
            source_type=self.source_type,
            document_name=self.document_name,
            content_hash=self.content_hash,
            fetched_at=self.fetched_at.isoformat() if self.fetched_at else utc_now().isoformat(),
            academic_year=self.academic_year,
            publication_date=self.publication_date,
            verification_status=self.verification_status,
            chunk_count=self.chunk_count,
            requires_ocr=self.requires_ocr,
            error_message=self.error_message,
        )

    def to_dict(self) -> Dict[str, Any]:
        return self.to_metadata().model_dump()


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String(50), nullable=False)  # "url", "websites", "file", "reindex"
    status = Column(String(50), nullable=False, default="pending")  # "pending", "running", "completed", "failed"
    total_attempted = Column(Integer, nullable=False, default=0)
    successful = Column(Integer, nullable=False, default=0)
    unchanged = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    requires_ocr = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "total_attempted": self.total_attempted,
            "successful": self.successful,
            "unchanged": self.unchanged,
            "failed": self.failed,
            "requires_ocr": self.requires_ocr,
            "error_message": self.error_message,
            "details": self.details,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
