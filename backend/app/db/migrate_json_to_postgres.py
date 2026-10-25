import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import DATA_DIR, REGISTRY_FILE
from app.db.database import get_db_context, get_engine
from app.db.init_db import init_db
from app.db.models import KnowledgeDocument, KnowledgeSource

logger = logging.getLogger(__name__)

DEFAULT_SOURCES_PATH = Path(REGISTRY_FILE)
DEFAULT_CATALOG_PATH = Path(DATA_DIR / "documents_catalog.json")


def parse_iso_datetime(val: Optional[str]) -> Optional[datetime]:
    """Safely parse an ISO 8601 string to a timezone-aware UTC datetime."""
    if not val or not isinstance(val, str):
        return None
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logger.warning("Could not parse datetime string '%s': %s", val, str(e))
        return None


def migrate_sources(
    session: Session,
    sources_data: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Migrate sources from JSON data to knowledge_sources table."""
    inserted = 0
    updated = 0

    for item in sources_data:
        url = (item.get("url") or "").strip()
        if not url:
            continue

        title = item.get("title") or "ASTU Source"
        description = item.get("description") or ""
        verification_status = item.get("verification_status") or "candidate"
        added_at = parse_iso_datetime(item.get("added_at")) or datetime.now(timezone.utc)
        last_checked = parse_iso_datetime(item.get("last_checked"))
        last_status = item.get("last_status") or "pending"
        error_message = item.get("error_message")

        existing = session.execute(
            select(KnowledgeSource).where(KnowledgeSource.url == url)
        ).scalar_one_or_none()

        if existing:
            existing.title = title
            existing.description = description
            existing.verification_status = verification_status
            existing.added_at = added_at
            existing.last_checked = last_checked
            existing.last_status = last_status
            existing.error_message = error_message
            updated += 1
        else:
            new_source = KnowledgeSource(
                url=url,
                title=title,
                description=description,
                verification_status=verification_status,
                added_at=added_at,
                last_checked=last_checked,
                last_status=last_status,
                error_message=error_message,
            )
            session.add(new_source)
            inserted += 1

    return {"read": len(sources_data), "inserted": inserted, "updated": updated}


def migrate_documents(
    session: Session,
    documents_data: Dict[str, Dict[str, Any]],
) -> Dict[str, int]:
    """Migrate documents from JSON catalog data to knowledge_documents table."""
    inserted = 0
    updated = 0

    for doc_id, item in documents_data.items():
        clean_doc_id = str(item.get("doc_id") or doc_id).strip()
        if not clean_doc_id:
            continue

        source_url = item.get("source_url")
        source_title = item.get("source_title") or "Untitled Document"
        source_type = item.get("source_type") or "webpage"
        document_name = item.get("document_name") or clean_doc_id
        content_hash = item.get("content_hash") or ""
        fetched_at = parse_iso_datetime(item.get("fetched_at")) or datetime.now(timezone.utc)
        academic_year = item.get("academic_year")
        publication_date = item.get("publication_date")
        verification_status = item.get("verification_status") or "candidate"
        chunk_count = int(item.get("chunk_count") or 0)
        requires_ocr = bool(item.get("requires_ocr", False))
        error_message = item.get("error_message")

        existing = session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.doc_id == clean_doc_id)
        ).scalar_one_or_none()

        if existing:
            existing.source_url = source_url
            existing.source_title = source_title
            existing.source_type = source_type
            existing.document_name = document_name
            existing.content_hash = content_hash
            existing.fetched_at = fetched_at
            existing.academic_year = academic_year
            existing.publication_date = publication_date
            existing.verification_status = verification_status
            existing.chunk_count = chunk_count
            existing.requires_ocr = requires_ocr
            existing.error_message = error_message
            updated += 1
        else:
            new_doc = KnowledgeDocument(
                doc_id=clean_doc_id,
                source_url=source_url,
                source_title=source_title,
                source_type=source_type,
                document_name=document_name,
                content_hash=content_hash,
                fetched_at=fetched_at,
                academic_year=academic_year,
                publication_date=publication_date,
                verification_status=verification_status,
                chunk_count=chunk_count,
                requires_ocr=requires_ocr,
                error_message=error_message,
            )
            session.add(new_doc)
            inserted += 1

    return {"read": len(documents_data), "inserted": inserted, "updated": updated}


def validate_migration(
    session: Session,
    raw_sources: List[Dict[str, Any]],
    raw_documents: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate that migrated database records accurately match the original JSON data."""
    validation_results = {
        "sources_valid": True,
        "documents_valid": True,
        "sources_checked": 0,
        "documents_checked": 0,
        "mismatches": [],
    }

    # Validate sources
    for s in raw_sources:
        url = (s.get("url") or "").strip()
        if not url:
            continue
        db_source = session.execute(
            select(KnowledgeSource).where(KnowledgeSource.url == url)
        ).scalar_one_or_none()

        if not db_source:
            validation_results["sources_valid"] = False
            validation_results["mismatches"].append(f"Source missing from DB: {url}")
            continue

        validation_results["sources_checked"] += 1
        expected_status = s.get("verification_status") or "candidate"
        if db_source.verification_status != expected_status:
            validation_results["sources_valid"] = False
            validation_results["mismatches"].append(
                f"Source {url} verification_status mismatch: DB={db_source.verification_status}, JSON={expected_status}"
            )

    # Validate documents
    for doc_id, doc in raw_documents.items():
        clean_doc_id = str(doc.get("doc_id") or doc_id).strip()
        if not clean_doc_id:
            continue
        db_doc = session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.doc_id == clean_doc_id)
        ).scalar_one_or_none()

        if not db_doc:
            validation_results["documents_valid"] = False
            validation_results["mismatches"].append(f"Document missing from DB: {clean_doc_id}")
            continue

        validation_results["documents_checked"] += 1
        expected_chunks = int(doc.get("chunk_count") or 0)
        if db_doc.chunk_count != expected_chunks:
            validation_results["documents_valid"] = False
            validation_results["mismatches"].append(
                f"Document {clean_doc_id} chunk_count mismatch: DB={db_doc.chunk_count}, JSON={expected_chunks}"
            )

        expected_hash = doc.get("content_hash") or ""
        if db_doc.content_hash != expected_hash:
            validation_results["documents_valid"] = False
            validation_results["mismatches"].append(
                f"Document {clean_doc_id} content_hash mismatch"
            )

    return validation_results


def migrate_json_to_postgres(
    sources_path: Path = DEFAULT_SOURCES_PATH,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
) -> Dict[str, Any]:
    """
    Main migration entrypoint.
    Executes in a safe transaction with rollback on failure.
    Validates after migration without modifying or deleting local JSON files.
    """
    # 1. Ensure DB schema is initialized
    init_db()

    # 2. Read JSON files
    raw_sources: List[Dict[str, Any]] = []
    if sources_path.exists():
        with open(sources_path, "r", encoding="utf-8") as f:
            raw_sources = json.load(f)
    else:
        logger.warning("Sources file not found at %s. Skipping sources migration.", sources_path)

    raw_documents: Dict[str, Dict[str, Any]] = {}
    if catalog_path.exists():
        with open(catalog_path, "r", encoding="utf-8") as f:
            raw_documents = json.load(f)
    else:
        logger.warning("Catalog file not found at %s. Skipping documents migration.", catalog_path)

    # 3. Execute in atomic transaction
    with get_db_context() as session:
        try:
            with session.begin():
                source_stats = migrate_sources(session, raw_sources)
                doc_stats = migrate_documents(session, raw_documents)

            # 4. Validate after commit
            validation = validate_migration(session, raw_sources, raw_documents)
            if not validation["sources_valid"] or not validation["documents_valid"]:
                raise RuntimeError(
                    f"Migration validation failed: {validation['mismatches']}"
                )

            summary = {
                "status": "success",
                "sources": source_stats,
                "documents": doc_stats,
                "validation": {
                    "sources_checked": validation["sources_checked"],
                    "documents_checked": validation["documents_checked"],
                    "mismatches_count": len(validation["mismatches"]),
                },
            }
            logger.info("JSON-to-PostgreSQL migration completed successfully: %s", summary)
            return summary

        except Exception as e:
            logger.error("Migration failed, changes rolled back: %s", str(e))
            raise


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("=" * 60)
    print("Starting JSON to Neon PostgreSQL migration...")
    print("=" * 60)

    try:
        summary = migrate_json_to_postgres()
        print("\nMigration Results:")
        print(f"  Knowledge Sources:   {summary['sources']['read']} read, "
              f"{summary['sources']['inserted']} inserted, "
              f"{summary['sources']['updated']} updated")
        print(f"  Knowledge Documents: {summary['documents']['read']} read, "
              f"{summary['documents']['inserted']} inserted, "
              f"{summary['documents']['updated']} updated")
        print(f"  Validation:          {summary['validation']['sources_checked']} sources verified, "
              f"{summary['validation']['documents_checked']} documents verified, "
              f"{summary['validation']['mismatches_count']} mismatches")
        print("\nAll records migrated and verified successfully!")
    except Exception as e:
        print(f"\nMigration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
