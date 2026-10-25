import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.config import REGISTRY_FILE
from app.db.database import SessionLocal
from app.db.models import KnowledgeSource

logger = logging.getLogger(__name__)

INITIAL_ASTU_SOURCES = [
    {
        "url": "https://www.astu.edu.et/",
        "title": "ASTU Homepage",
        "description": "Adama Science and Technology University official portal homepage.",
        "verification_status": "candidate",
    },
    {
        "url": "https://www.astu.edu.et/10-academics/212-registrar-and-alumni-executive",
        "title": "ASTU Registrar and Alumni Executive",
        "description": "Registrar announcements, admission guidelines, and alumni information.",
        "verification_status": "candidate",
    },
    {
        "url": "https://www.astu.edu.et/offices/administration-development/dean-of-student-services",
        "title": "Dean of Student Services",
        "description": "Student services, cafeteria, clinic, dormitories, and student support.",
        "verification_status": "candidate",
    },
    {
        "url": "https://www.astu.edu.et/admission/importants/academic-calendar",
        "title": "ASTU Academic Calendar",
        "description": "Important dates, semesters, exams, and academic milestones.",
        "verification_status": "candidate",
    },
    {
        "url": "https://portal.astu.edu.et/pages/active_calendars",
        "title": "ASTU Student Portal Active Calendars",
        "description": "Live active academic calendars on the student portal.",
        "verification_status": "candidate",
    },
]


class SourceRegistry:
    def __init__(
        self,
        registry_file: Optional[Path] = REGISTRY_FILE,
        session_factory: Optional[Callable[[], Session]] = None,
    ):
        self.registry_file = Path(registry_file) if registry_file else None
        self._session_factory = session_factory
        self._ensure_initialized()

    def _get_session(self) -> Session:
        if self._session_factory is not None:
            return self._session_factory()
        return SessionLocal()

    def _ensure_initialized(self):
        """Seed initial candidate sources if the database table is empty."""
        try:
            with self._get_session() as session:
                count = session.execute(
                    select(func.count(KnowledgeSource.id))
                ).scalar() or 0

                if count == 0:
                    logger.info("Initializing knowledge_sources with default ASTU sources.")
                    now = datetime.now(timezone.utc)
                    for item in INITIAL_ASTU_SOURCES:
                        source = KnowledgeSource(
                            url=item["url"],
                            title=item["title"],
                            description=item.get("description", ""),
                            verification_status=item.get("verification_status", "candidate"),
                            added_at=now,
                            last_status="pending",
                        )
                        session.add(source)
                    session.commit()
        except Exception as e:
            logger.error("Failed to verify/initialize source registry in database: %s", str(e))

    def get_sources(self) -> List[Dict[str, Any]]:
        """Return list of candidate and approved sources from PostgreSQL."""
        try:
            with self._get_session() as session:
                sources = session.execute(
                    select(KnowledgeSource).order_by(KnowledgeSource.id)
                ).scalars().all()

                if not sources:
                    self._ensure_initialized()
                    sources = session.execute(
                        select(KnowledgeSource).order_by(KnowledgeSource.id)
                    ).scalars().all()

                return [s.to_dict() for s in sources]
        except Exception as e:
            logger.error("Failed to retrieve sources from database: %s", str(e))
            return []

    def add_source(
        self,
        url: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        verification_status: str = "candidate",
    ) -> Dict[str, Any]:
        """Add or update an approved URL in the PostgreSQL knowledge_sources registry."""
        clean_url = url.strip()

        with self._get_session() as session:
            try:
                source = session.execute(
                    select(KnowledgeSource).where(
                        func.lower(KnowledgeSource.url) == clean_url.lower()
                    )
                ).scalar_one_or_none()

                if source:
                    if title:
                        source.title = title
                    if description is not None:
                        source.description = description
                    source.verification_status = verification_status
                else:
                    source = KnowledgeSource(
                        url=clean_url,
                        title=title or "ASTU Source",
                        description=description or "",
                        verification_status=verification_status,
                        added_at=datetime.now(timezone.utc),
                        last_status="pending",
                    )
                    session.add(source)

                session.commit()
                session.refresh(source)
                return source.to_dict()
            except Exception as e:
                session.rollback()
                logger.error("Failed to add or update source %s: %s", clean_url, str(e))
                raise

    def update_source_status(
        self,
        url: str,
        status: str,
        error_message: Optional[str] = None,
        title: Optional[str] = None,
    ):
        """Update inspection/ingestion status for a source in PostgreSQL."""
        clean_url = url.strip().lower()

        try:
            with self._get_session() as session:
                try:
                    source = session.execute(
                        select(KnowledgeSource).where(
                            func.lower(KnowledgeSource.url) == clean_url
                        )
                    ).scalar_one_or_none()

                    if source:
                        source.last_status = status
                        source.last_checked = datetime.now(timezone.utc)
                        source.error_message = error_message
                        if title:
                            source.title = title
                        session.commit()
                    else:
                        logger.debug("Attempted to update status for non-registered URL: %s", url)
                except Exception as e:
                    session.rollback()
                    logger.warning("Failed to update status for source %s in database: %s", url, str(e))
        except Exception as e:
            logger.warning("Database unavailable in update_source_status for %s: %s", url, str(e))


# Global singleton instance
source_registry = SourceRegistry()
