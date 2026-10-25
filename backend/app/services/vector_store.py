import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
import chromadb
from chromadb.config import Settings
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import (
    CHROMA_PERSIST_DIR,
    DATA_DIR,
    RAG_MAX_COSINE_DISTANCE,
    RAG_SCORE_MARGIN,
    RAG_TOP_K,
)
from app.db.database import SessionLocal
from app.db.models import KnowledgeDocument
from app.schemas.knowledge import DocumentMetadata, VerificationStatus

logger = logging.getLogger(__name__)

COLLECTION_NAME = "astu_campus_knowledge"
# Preserved for backward-compatibility references
CATALOG_FILE = DATA_DIR / "documents_catalog.json"


class VectorStoreService:
    def __init__(
        self,
        persist_dir: Path = CHROMA_PERSIST_DIR,
        session_factory: Optional[Callable[[], Session]] = None,
    ):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client: chromadb.PersistentClient | None = None
        self._collection = None
        self._session_factory = session_factory

    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _get_session(self) -> Session:
        if self._session_factory is not None:
            return self._session_factory()
        return SessionLocal()

    # -------------------------------------------------------------------------
    # PostgreSQL Document Metadata Management
    # -------------------------------------------------------------------------
    def get_document(self, doc_id: str) -> Optional[DocumentMetadata]:
        """Fetch document metadata by doc_id from PostgreSQL."""
        try:
            with self._get_session() as session:
                doc = session.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.doc_id == doc_id)
                ).scalar_one_or_none()

                if not doc:
                    return None
                return doc.to_metadata()
        except Exception as e:
            logger.error("Failed to fetch document %s from database: %s", doc_id, str(e))
            return None

    def list_documents(self) -> List[DocumentMetadata]:
        """List all document metadata records from PostgreSQL."""
        try:
            with self._get_session() as session:
                docs = session.execute(
                    select(KnowledgeDocument).order_by(KnowledgeDocument.id.desc())
                ).scalars().all()
                return [d.to_metadata() for d in docs]
        except Exception as e:
            logger.error("Failed to list documents from database: %s", str(e))
            return []

    def record_document_status(self, metadata: DocumentMetadata):
        """Save or update structured document metadata in PostgreSQL."""
        try:
            with self._get_session() as session:
                try:
                    doc = session.execute(
                        select(KnowledgeDocument).where(KnowledgeDocument.doc_id == metadata.doc_id)
                    ).scalar_one_or_none()

                    fetched_at = None
                    if metadata.fetched_at:
                        try:
                            fetched_at = datetime.fromisoformat(metadata.fetched_at)
                            if fetched_at.tzinfo is None:
                                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                        except Exception:
                            fetched_at = datetime.now(timezone.utc)
                    else:
                        fetched_at = datetime.now(timezone.utc)

                    if doc:
                        doc.source_url = metadata.source_url
                        doc.source_title = metadata.source_title
                        doc.source_type = metadata.source_type
                        doc.document_name = metadata.document_name
                        doc.content_hash = metadata.content_hash or ""
                        doc.fetched_at = fetched_at
                        doc.academic_year = metadata.academic_year
                        doc.publication_date = metadata.publication_date
                        doc.verification_status = metadata.verification_status
                        doc.chunk_count = metadata.chunk_count
                        doc.requires_ocr = metadata.requires_ocr
                        doc.error_message = metadata.error_message
                    else:
                        doc = KnowledgeDocument(
                            doc_id=metadata.doc_id,
                            source_url=metadata.source_url,
                            source_title=metadata.source_title,
                            source_type=metadata.source_type,
                            document_name=metadata.document_name,
                            content_hash=metadata.content_hash or "",
                            fetched_at=fetched_at,
                            academic_year=metadata.academic_year,
                            publication_date=metadata.publication_date,
                            verification_status=metadata.verification_status,
                            chunk_count=metadata.chunk_count,
                            requires_ocr=metadata.requires_ocr,
                            error_message=metadata.error_message,
                        )
                        session.add(doc)

                    session.commit()
                except Exception as e:
                    session.rollback()
                    logger.warning("Failed to record document metadata for %s: %s", metadata.doc_id, str(e))
        except Exception as e:
            logger.warning("Database unavailable in record_document_status for %s: %s", metadata.doc_id, str(e))

    # -------------------------------------------------------------------------
    # Vector Indexing & Idempotency
    # -------------------------------------------------------------------------
    def index_document(
        self,
        metadata: DocumentMetadata,
        chunks: List[str],
        embeddings: List[List[float]],
    ) -> Dict[str, Any]:
        """
        Index chunks for a document idempotently.
        - If content_hash is unchanged, skips indexing.
        - If content_hash changed, deletes previous chunks and indexes new ones.
        - Synchronizes Chroma vector store and PostgreSQL document metadata atomically.
        """
        existing = self.get_document(metadata.doc_id)

        # Check for unchanged document
        if existing and existing.content_hash == metadata.content_hash:
            logger.info("Document %s (%s) unchanged. Skipping index.", metadata.doc_id, metadata.document_name)
            return {
                "status": "unchanged",
                "doc_id": metadata.doc_id,
                "chunk_count": existing.chunk_count,
                "message": "Document content is unchanged. Skipping re-indexing.",
            }

        # If document already existed with different hash, remove old chunks first
        if existing:
            logger.info("Document %s changed. Purging old chunks before re-indexing.", metadata.doc_id)
            self._purge_chunks(metadata.doc_id)

        if not chunks:
            # Document has no text (e.g. empty or scanned)
            metadata.chunk_count = 0
            self.record_document_status(metadata)
            return {
                "status": "scanned_requires_ocr" if metadata.requires_ocr else "empty",
                "doc_id": metadata.doc_id,
                "chunk_count": 0,
                "message": "Document contains no extractable text (OCR required)." if metadata.requires_ocr else "Document is empty.",
            }

        # Build IDs and sanitized metadata for Chroma
        ids: List[str] = []
        sanitized_metadatas: List[Dict[str, Any]] = []

        for idx, _ in enumerate(chunks):
            chunk_id = f"{metadata.doc_id}_chunk_{idx}"
            ids.append(chunk_id)
            sanitized_metadatas.append({
                "doc_id": str(metadata.doc_id),
                "chunk_index": int(idx),
                "source_url": str(metadata.source_url or ""),
                "source_title": str(metadata.source_title or ""),
                "source_type": str(metadata.source_type or ""),
                "document_name": str(metadata.document_name or ""),
                "content_hash": str(metadata.content_hash or ""),
                "fetched_at": str(metadata.fetched_at or ""),
                "academic_year": str(metadata.academic_year or ""),
                "publication_date": str(metadata.publication_date or ""),
                "verification_status": str(metadata.verification_status or VerificationStatus.CANDIDATE.value),
            })

        # Add to Chroma collection
        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=sanitized_metadatas,
        )

        metadata.chunk_count = len(chunks)
        try:
            self.record_document_status(metadata)
        except Exception as e:
            # Purge newly added chunks to avoid inconsistent state
            logger.error(
                "Failed to save metadata to PostgreSQL after Chroma indexing for %s: %s. Rolling back Chroma chunks.",
                metadata.doc_id,
                str(e),
            )
            self._purge_chunks(metadata.doc_id)
            raise

        return {
            "status": "indexed",
            "doc_id": metadata.doc_id,
            "chunk_count": len(chunks),
            "message": f"Successfully indexed {len(chunks)} chunks.",
        }

    def _purge_chunks(self, doc_id: str):
        """Delete all chunks belonging to doc_id from Chroma."""
        try:
            self.collection.delete(where={"doc_id": doc_id})
        except Exception as e:
            logger.warning("Error deleting chunks for %s from Chroma: %s", doc_id, str(e))

    def delete_document(self, doc_id: str) -> int:
        """Delete document from PostgreSQL and purge chunks from Chroma."""
        deleted_count = 0
        with self._get_session() as session:
            try:
                doc = session.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.doc_id == doc_id)
                ).scalar_one_or_none()

                if doc:
                    deleted_count = doc.chunk_count
                    session.delete(doc)
                    session.commit()
            except Exception as e:
                session.rollback()
                logger.error("Failed to delete document %s from database: %s", doc_id, str(e))
                raise

        self._purge_chunks(doc_id)
        return deleted_count

    # -------------------------------------------------------------------------
    # Retrieval
    # -------------------------------------------------------------------------
    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = RAG_TOP_K,
        max_distance: float = RAG_MAX_COSINE_DISTANCE,
        score_margin: float = RAG_SCORE_MARGIN,
        relevance_threshold: Optional[float] = None,
        query_tokens: Optional[Set[str]] = None,
        is_navigational: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search for top-K chunks by cosine distance in Chroma with optional
        hybrid lexical re-ranking and noise filtering.
        Cosine distance in Chroma: 0 = identical, 1 = orthogonal, 2 = opposite.
        Cosine similarity = 1.0 - distance.
        """
        if self.collection.count() == 0:
            return []

        effective_max_dist = max_distance
        if relevance_threshold is not None:
            logger.warning(
                "relevance_threshold is deprecated. Standardize on max_distance (RAG_MAX_COSINE_DISTANCE=0.38)."
            )
            effective_max_dist = (1.0 - relevance_threshold) if relevance_threshold > 0.5 else relevance_threshold

        query_pool_size = min(max(top_k * 2, 8), self.collection.count())
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=query_pool_size,
            include=["documents", "metadatas", "distances"],
        )

        matched_chunks: List[Dict[str, Any]] = []

        if not results or not results["documents"] or not results["documents"][0]:
            return []

        ids = results["ids"][0] if results.get("ids") else []
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results.get("metadatas") else []
        dists = results["distances"][0] if results.get("distances") else []

        if not dists:
            return []

        top_dist = float(dists[0])
        if top_dist > effective_max_dist:
            logger.debug(
                "Top chunk distance %.4f exceeds max distance threshold %.4f. Rejecting all.",
                top_dist,
                effective_max_dist,
            )
            return []

        cutoff_dist = min(effective_max_dist, top_dist + score_margin)

        for idx, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
            if dist is not None:
                d = float(dist)
                if d <= cutoff_dist:
                    chunk_id = ids[idx] if idx < len(ids) else f"chunk_{idx}"
                    token_overlap = 0
                    overlap_tokens: Set[str] = set()

                    if query_tokens:
                        doc_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", doc.lower()))
                        title_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", (meta.get("source_title") or "").lower()))
                        overlap_tokens = query_tokens & (doc_words | title_words)
                        token_overlap = len(overlap_tokens)

                        # Noise filtering: for factual non-navigational queries, if distance is borderline (>= 0.28)
                        # and there is zero substantive overlap with query terms, skip noise chunk.
                        if not is_navigational and d >= 0.28 and token_overlap == 0:
                            continue

                    hybrid_score = max(0.0, 1.0 - d) + (0.04 * min(6, token_overlap))

                    matched_chunks.append({
                        "id": chunk_id,
                        "text": doc,
                        "metadata": meta,
                        "distance": d,
                        "relevance_score": hybrid_score,
                        "token_overlap": token_overlap,
                        "overlap_tokens": list(overlap_tokens),
                    })

        matched_chunks.sort(key=lambda x: x["relevance_score"], reverse=True)
        return matched_chunks[:top_k]


# Global singleton instance
vector_store = VectorStoreService()
