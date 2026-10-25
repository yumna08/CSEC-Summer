import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional
from sqlalchemy import select
from app.core.config import MAX_CRAWL_PAGES
from app.db.database import SessionLocal
from app.db.models import IngestionJob
from app.schemas.knowledge import (
    DocumentMetadata,
    IngestResult,
    IngestWebsitesResponse,
    ReindexResponse,
    SourceType,
    VerificationStatus,
)
from app.services.chunker import chunk_document
from app.services.crawler import crawler
from app.services.embeddings import embedding_service
from app.services.extractors import (
    extract_docx_content,
    extract_html_content,
    extract_pdf_content,
    extract_txt_content,
)
from app.services.registry import source_registry
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)


def generate_doc_id(source_identifier: str) -> str:
    """Generate a stable document ID from a URL or file identifier."""
    return hashlib.md5(source_identifier.strip().lower().encode("utf-8")).hexdigest()[:16]


class IngestionService:
    def _create_job(self, job_type: str) -> Optional[int]:
        try:
            with SessionLocal() as session:
                job = IngestionJob(
                    job_type=job_type,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                session.add(job)
                session.commit()
                return job.id
        except Exception as e:
            logger.debug("Ingestion job recording skipped or unavailable: %s", str(e))
            return None

    def _complete_job(
        self,
        job_id: Optional[int],
        status: str,
        total_attempted: int = 0,
        successful: int = 0,
        unchanged: int = 0,
        failed: int = 0,
        requires_ocr: int = 0,
        error_message: Optional[str] = None,
        details: Optional[Any] = None,
    ):
        if not job_id:
            return
        try:
            with SessionLocal() as session:
                job = session.execute(
                    select(IngestionJob).where(IngestionJob.id == job_id)
                ).scalar_one_or_none()
                if job:
                    job.status = status
                    job.total_attempted = total_attempted
                    job.successful = successful
                    job.unchanged = unchanged
                    job.failed = failed
                    job.requires_ocr = requires_ocr
                    job.error_message = error_message
                    job.details = details
                    job.completed_at = datetime.now(timezone.utc)
                    session.commit()
        except Exception as e:
            logger.debug("Ingestion job completion update skipped: %s", str(e))

    def ingest_url(
        self,
        url: str,
        custom_title: Optional[str] = None,
        verification_status: str = VerificationStatus.CANDIDATE.value,
    ) -> IngestResult:
        """
        Ingest a single approved webpage URL.
        Validates status, robots.txt, extracts content, embeds, and indexes idempotently.
        """
        doc_id = f"web_{generate_doc_id(url)}"

        # 1. Fetch safely
        success, response, err_msg = crawler.fetch_url_safely(
            url,
            expected_content_types=("text/html", "application/xhtml+xml"),
        )
        if not success or response is None:
            source_registry.update_source_status(url, "failed", error_message=err_msg)
            # Record failed status in catalog for visibility
            meta = DocumentMetadata(
                doc_id=doc_id,
                source_url=url,
                source_title=custom_title or "ASTU Webpage",
                source_type=SourceType.WEBPAGE.value,
                document_name=url,
                content_hash="",
                verification_status=VerificationStatus.FAILED.value,
                chunk_count=0,
                error_message=err_msg,
            )
            vector_store.record_document_status(meta)
            return IngestResult(
                doc_id=doc_id,
                source_url=url,
                document_name=url,
                status="failed",
                chunk_count=0,
                message=f"Inaccessible webpage: {err_msg}",
            )

        # 2. Extract content
        extracted = extract_html_content(response.text, base_url=url)
        title = custom_title or extracted["title"]
        clean_text = extracted["text"]
        content_hash = extracted["content_hash"]

        if not clean_text or extracted["requires_ocr"]:
            source_registry.update_source_status(url, "empty", error_message="Empty page content")
            meta = DocumentMetadata(
                doc_id=doc_id,
                source_url=url,
                source_title=title,
                source_type=SourceType.WEBPAGE.value,
                document_name=url,
                content_hash=content_hash,
                verification_status=verification_status,
                chunk_count=0,
                error_message="Page contained no readable main text.",
            )
            vector_store.record_document_status(meta)
            return IngestResult(
                doc_id=doc_id,
                source_url=url,
                document_name=title,
                status="empty",
                chunk_count=0,
                message="Page contained no readable main text.",
            )

        # 3. Check for existing identical document
        existing = vector_store.get_document(doc_id)
        if existing and existing.content_hash == content_hash:
            source_registry.update_source_status(url, "unchanged", title=title)
            return IngestResult(
                doc_id=doc_id,
                source_url=url,
                document_name=title,
                status="unchanged",
                chunk_count=existing.chunk_count,
                message="Webpage content has not changed. Existing index preserved.",
            )

        # 4. Chunk text
        chunks = chunk_document(clean_text)

        # 5. Generate embeddings
        try:
            embeddings = embedding_service.embed_documents(chunks)
        except Exception as e:
            logger.error("Embedding generation failed for %s: %s", url, str(e))
            source_registry.update_source_status(url, "embedding_failed", error_message=str(e))
            return IngestResult(
                doc_id=doc_id,
                source_url=url,
                document_name=title,
                status="failed",
                chunk_count=0,
                message=f"Embedding generation failed: {str(e)}",
            )

        # 6. Index into Chroma
        metadata = DocumentMetadata(
            doc_id=doc_id,
            source_url=url,
            source_title=title,
            source_type=SourceType.WEBPAGE.value,
            document_name=url,
            content_hash=content_hash,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            academic_year=extracted.get("academic_year"),
            publication_date=extracted.get("publication_date"),
            verification_status=verification_status,
            chunk_count=len(chunks),
        )

        index_res = vector_store.index_document(metadata, chunks, embeddings)
        source_registry.update_source_status(url, "indexed", title=title)

        return IngestResult(
            doc_id=doc_id,
            source_url=url,
            document_name=title,
            status=index_res["status"],
            chunk_count=index_res["chunk_count"],
            message=index_res["message"],
        )

    def ingest_file(
        self,
        filename: str,
        file_bytes: bytes,
        source_url: Optional[str] = None,
        verification_status: str = VerificationStatus.CANDIDATE.value,
    ) -> IngestResult:
        """
        Ingest a file (PDF, DOCX, TXT) from upload or web crawler.
        Detects scanned PDFs and marks as requiring OCR.
        """
        ext = Path(filename).suffix.lower()
        doc_id = f"file_{generate_doc_id(source_url or filename)}"

        if ext == ".pdf":
            extracted = extract_pdf_content(file_bytes, filename=filename)
            source_type = SourceType.PDF.value
        elif ext == ".docx":
            extracted = extract_docx_content(file_bytes, filename=filename)
            source_type = SourceType.DOCX.value
        elif ext in (".txt", ".text", ".md"):
            extracted = extract_txt_content(file_bytes, filename=filename)
            source_type = SourceType.TXT.value
        else:
            return IngestResult(
                doc_id=doc_id,
                source_url=source_url,
                document_name=filename,
                status="failed",
                chunk_count=0,
                message=f"Unsupported file format '{ext}'. Supported formats: PDF, DOCX, TXT.",
            )

        title = extracted.get("title") or filename
        content_hash = extracted.get("content_hash") or ""
        clean_text = extracted.get("text") or ""
        requires_ocr = extracted.get("requires_ocr", False)

        # Handle scanned or empty documents
        if requires_ocr or not clean_text:
            meta = DocumentMetadata(
                doc_id=doc_id,
                source_url=source_url,
                source_title=title,
                source_type=source_type,
                document_name=filename,
                content_hash=content_hash,
                verification_status=verification_status,
                chunk_count=0,
                requires_ocr=True,
                error_message="Document appears to be a scanned image or contains no extractable text. Requires OCR.",
            )
            vector_store.record_document_status(meta)
            return IngestResult(
                doc_id=doc_id,
                source_url=source_url,
                document_name=filename,
                status="scanned_requires_ocr",
                chunk_count=0,
                message="Document appears to be a scanned image or contains no extractable text. Marked as requiring OCR.",
            )

        # Check for unchanged document
        existing = vector_store.get_document(doc_id)
        if existing and existing.content_hash == content_hash:
            return IngestResult(
                doc_id=doc_id,
                source_url=source_url,
                document_name=filename,
                status="unchanged",
                chunk_count=existing.chunk_count,
                message="Document content is unchanged. Existing index preserved.",
            )

        # Chunk text
        chunks = chunk_document(clean_text)

        # Generate embeddings
        try:
            embeddings = embedding_service.embed_documents(chunks)
        except Exception as e:
            logger.error("Embedding generation failed for file %s: %s", filename, str(e))
            return IngestResult(
                doc_id=doc_id,
                source_url=source_url,
                document_name=filename,
                status="failed",
                chunk_count=0,
                message=f"Embedding generation failed: {str(e)}",
            )

        metadata = DocumentMetadata(
            doc_id=doc_id,
            source_url=source_url,
            source_title=title,
            source_type=source_type,
            document_name=filename,
            content_hash=content_hash,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            academic_year=extracted.get("academic_year"),
            publication_date=extracted.get("publication_date"),
            verification_status=verification_status,
            chunk_count=len(chunks),
            requires_ocr=False,
        )

        index_res = vector_store.index_document(metadata, chunks, embeddings)

        return IngestResult(
            doc_id=doc_id,
            source_url=source_url,
            document_name=filename,
            status=index_res["status"],
            chunk_count=index_res["chunk_count"],
            message=index_res["message"],
        )

    def ingest_websites(
        self,
        urls: Optional[List[str]] = None,
        discover_pdfs: bool = True,
        max_pages: int = MAX_CRAWL_PAGES,
    ) -> IngestWebsitesResponse:
        """
        Crawl and ingest configured approved sources.
        Discovers PDF links on approved pages, validates them, and ingests.
        """
        job_id = self._create_job(job_type="websites")
        if urls:
            targets = [{"url": u, "title": None, "verification_status": "candidate"} for u in urls]
        else:
            targets = source_registry.get_sources()

        results: List[IngestResult] = []
        discovered_pdf_urls: List[str] = []
        processed_pages = 0

        try:
            for target in targets:
                if processed_pages >= max_pages:
                    break

                url = target["url"]
                res = self.ingest_url(
                    url=url,
                    custom_title=target.get("title"),
                    verification_status=target.get("verification_status", "candidate"),
                )
                results.append(res)
                processed_pages += 1

                # Discover PDFs linked from this page if allowed
                if discover_pdfs and res.status in ("indexed", "unchanged"):
                    # Fetch page HTML again or inspect
                    success, resp, _ = crawler.fetch_url_safely(url)
                    if success and resp:
                        extracted = extract_html_content(resp.text, base_url=url)
                        pdf_hrefs = extracted.get("pdf_links", [])
                        valid_pdfs = crawler.discover_and_validate_pdf_links(url, pdf_hrefs)
                        for p_url in valid_pdfs:
                            if p_url not in discovered_pdf_urls:
                                discovered_pdf_urls.append(p_url)

            # Ingest discovered PDFs within limits
            for pdf_url in discovered_pdf_urls:
                if processed_pages >= max_pages:
                    break

                filename = Path(pdf_url).name or "document.pdf"
                success, resp, err_msg = crawler.fetch_url_safely(
                    pdf_url,
                    expected_content_types=("application/pdf", "application/octet-stream"),
                )
                processed_pages += 1

                if not success or resp is None:
                    results.append(IngestResult(
                        doc_id=f"file_{generate_doc_id(pdf_url)}",
                        source_url=pdf_url,
                        document_name=filename,
                        status="failed",
                        chunk_count=0,
                        message=f"Failed to download linked PDF: {err_msg}",
                    ))
                    continue

                file_res = self.ingest_file(
                    filename=filename,
                    file_bytes=resp.content,
                    source_url=pdf_url,
                    verification_status=VerificationStatus.CANDIDATE.value,
                )
                results.append(file_res)

            successful = sum(1 for r in results if r.status == "indexed")
            unchanged = sum(1 for r in results if r.status == "unchanged")
            failed = sum(1 for r in results if r.status == "failed")
            requires_ocr = sum(1 for r in results if r.status == "scanned_requires_ocr")

            response = IngestWebsitesResponse(
                total_attempted=len(results),
                successful=successful,
                unchanged=unchanged,
                failed=failed,
                requires_ocr=requires_ocr,
                results=results,
            )

            job_status = "completed" if failed == 0 else ("failed" if (successful + unchanged) == 0 else "completed_with_errors")
            self._complete_job(
                job_id=job_id,
                status=job_status,
                total_attempted=len(results),
                successful=successful,
                unchanged=unchanged,
                failed=failed,
                requires_ocr=requires_ocr,
            )
            return response
        except Exception as e:
            self._complete_job(job_id=job_id, status="failed", error_message=str(e))
            raise

    def reindex_all(self) -> ReindexResponse:
        """Refresh and reindex all registered sources."""
        job_id = self._create_job(job_type="reindex")
        try:
            ingest_res = self.ingest_websites(urls=None, discover_pdfs=True)
            self._complete_job(
                job_id=job_id,
                status="completed" if ingest_res.failed == 0 else "completed_with_errors",
                total_attempted=ingest_res.total_attempted,
                successful=ingest_res.successful,
                unchanged=ingest_res.unchanged,
                failed=ingest_res.failed,
                requires_ocr=ingest_res.requires_ocr,
            )
            return ReindexResponse(
                total_reindexed=ingest_res.successful + ingest_res.unchanged,
                results=ingest_res.results,
            )
        except Exception as e:
            self._complete_job(job_id=job_id, status="failed", error_message=str(e))
            raise



# Global singleton instance
ingestion_service = IngestionService()
