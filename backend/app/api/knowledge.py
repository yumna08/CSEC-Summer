import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from app.core.config import MAX_UPLOAD_SIZE_BYTES
from app.core.security import verify_admin_authorization
from app.schemas.knowledge import (
    DeleteDocumentResponse,
    DocumentListResponse,
    IngestResult,
    IngestUrlRequest,
    IngestWebsitesRequest,
    IngestWebsitesResponse,
    ReindexResponse,
    VerificationStatus,
)
from app.services.ingestion import ingestion_service
from app.services.registry import source_registry
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".text", ".md"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/octet-stream",  # Often sent for general binary uploads
}


@router.post(
    "/ingest-url",
    response_model=IngestResult,
    dependencies=[Depends(verify_admin_authorization)],
    summary="Ingest a single approved ASTU webpage",
)
def ingest_url(request: IngestUrlRequest):
    """Ingest a single approved webpage URL after SSRF and domain checks."""
    try:
        result = ingestion_service.ingest_url(
            url=request.url,
            custom_title=request.source_title,
            verification_status=request.verification_status or VerificationStatus.CANDIDATE.value,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to ingest URL %s: %s", request.url, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest URL. Check server logs.",
        ) from None


@router.post(
    "/ingest-websites",
    response_model=IngestWebsitesResponse,
    dependencies=[Depends(verify_admin_authorization)],
    summary="Crawl and ingest configured approved sources and discovered PDFs",
)
def ingest_websites(request: Optional[IngestWebsitesRequest] = None):
    """Ingest candidate/registered ASTU websites and valid discovered PDFs."""
    urls = request.urls if request else None
    discover_pdfs = request.discover_pdfs if request else True
    max_pages = request.max_pages if request and request.max_pages else 15

    try:
        return ingestion_service.ingest_websites(
            urls=urls,
            discover_pdfs=discover_pdfs,
            max_pages=max_pages,
        )
    except Exception as e:
        logger.error("Failed to ingest websites: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process website ingestion batch.",
        ) from None


@router.post(
    "/upload",
    response_model=IngestResult,
    dependencies=[Depends(verify_admin_authorization)],
    summary="Upload and ingest a PDF, DOCX, or TXT document",
)
async def upload_document(
    file: UploadFile = File(...),
    verification_status: str = VerificationStatus.VERIFIED.value,
):
    """
    Upload and ingest a document.
    Validates file extension, MIME type, file size, extracts text,
    detects scanned PDFs (marking as requiring OCR), and indexes chunks.
    """
    filename = file.filename or "uploaded_document"
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Validate MIME type if available
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type '{content_type}'.",
        )

    # Read bytes with file size guard
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB.",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        result = ingestion_service.ingest_file(
            filename=filename,
            file_bytes=content,
            source_url=None,
            verification_status=verification_status,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to ingest uploaded file %s: %s", filename, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process uploaded file.",
        ) from None


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List indexed knowledge sources and their ingestion status",
)
def list_documents():
    """List all indexed documents, chunk counts, hashes, and ingestion statuses."""
    docs = vector_store.list_documents()
    return DocumentListResponse(total=len(docs), documents=docs)


@router.delete(
    "/documents/{document_id}",
    response_model=DeleteDocumentResponse,
    dependencies=[Depends(verify_admin_authorization)],
    summary="Remove a document and its indexed chunks",
)
def delete_document(document_id: str):
    """Delete a document and purge all its indexed vector chunks."""
    deleted_chunks = vector_store.delete_document(document_id)
    return DeleteDocumentResponse(
        doc_id=document_id,
        deleted_chunks=deleted_chunks,
        message=f"Document '{document_id}' and {deleted_chunks} indexed chunks removed successfully.",
    )


@router.post(
    "/reindex",
    response_model=ReindexResponse,
    dependencies=[Depends(verify_admin_authorization)],
    summary="Refresh and reindex all registered sources",
)
def reindex_sources():
    """Refresh and re-ingest all registered sources."""
    try:
        return ingestion_service.reindex_all()
    except Exception as e:
        logger.error("Failed to reindex sources: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reindexing failed. Check backend logs.",
        ) from None


@router.get(
    "/sources",
    summary="List configured source registry URLs",
)
def list_sources():
    """Return list of candidate and approved sources from the source registry."""
    return {"sources": source_registry.get_sources()}
