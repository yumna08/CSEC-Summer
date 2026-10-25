from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    WEBPAGE = "webpage"
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    CANDIDATE = "candidate"
    UNVERIFIED = "unverified"
    FAILED = "failed"


class DocumentMetadata(BaseModel):
    doc_id: str
    source_url: Optional[str] = None
    source_title: str
    source_type: str
    document_name: str
    content_hash: str
    fetched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    academic_year: Optional[str] = None
    publication_date: Optional[str] = None
    verification_status: str = VerificationStatus.CANDIDATE.value
    chunk_count: int = 0
    requires_ocr: bool = False
    error_message: Optional[str] = None


class IngestUrlRequest(BaseModel):
    url: str = Field(..., description="Approved ASTU webpage URL to ingest")
    source_title: Optional[str] = None
    verification_status: Optional[str] = VerificationStatus.CANDIDATE.value


class IngestWebsitesRequest(BaseModel):
    urls: Optional[List[str]] = None
    discover_pdfs: bool = True
    max_pages: Optional[int] = None


class IngestResult(BaseModel):
    doc_id: Optional[str] = None
    source_url: Optional[str] = None
    document_name: str
    status: str  # "indexed", "unchanged", "scanned_requires_ocr", "failed"
    chunk_count: int = 0
    message: str


class IngestWebsitesResponse(BaseModel):
    total_attempted: int
    successful: int
    unchanged: int
    failed: int
    requires_ocr: int
    results: List[IngestResult]


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentMetadata]


class DeleteDocumentResponse(BaseModel):
    doc_id: str
    deleted_chunks: int
    message: str


class ReindexResponse(BaseModel):
    total_reindexed: int
    results: List[IngestResult]
