import logging
import sys
from typing import List, Optional
from sqlalchemy import Engine, inspect
from app.db.database import Base, get_engine
# Import models to ensure they are registered with Base.metadata
from app.db.models import ChatMessage, ChatSession, IngestionJob, KnowledgeDocument, KnowledgeSource

logger = logging.getLogger(__name__)

EXPECTED_TABLES = [
    KnowledgeSource.__tablename__,
    KnowledgeDocument.__tablename__,
    IngestionJob.__tablename__,
    ChatSession.__tablename__,
    ChatMessage.__tablename__,
]


def init_db(engine: Optional[Engine] = None) -> List[str]:
    """
    Safely initialize the database schema.
    Uses checkfirst=True to ensure existing tables are NEVER dropped or recreated.
    Validates that all expected tables exist.
    """
    eng = engine or get_engine()

    # Create tables safely without dropping existing ones
    Base.metadata.create_all(bind=eng, checkfirst=True)

    # Validate tables via inspector
    inspector = inspect(eng)
    existing_tables = inspector.get_table_names()

    missing = [t for t in EXPECTED_TABLES if t not in existing_tables]
    if missing:
        raise RuntimeError(f"Database initialization failed. Missing tables: {missing}")

    logger.info("Database schema initialized and verified. Active tables: %s", existing_tables)
    return existing_tables


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        tables = init_db()
        print("Database schema successfully initialized!")
        print(f"Verified tables: {', '.join(sorted(tables))}")
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
