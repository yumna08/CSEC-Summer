import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
_raw_data_dir = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR = _raw_data_dir if _raw_data_dir.is_absolute() else (BASE_DIR / _raw_data_dir).resolve()
CHROMA_PERSIST_DIR = Path(os.getenv("CHROMA_PERSIST_DIR", str(DATA_DIR / "chroma_db")))
REGISTRY_FILE = Path(os.getenv("REGISTRY_FILE", str(DATA_DIR / "source_registry.json")))

# Ensure storage directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)

# Gemini API and Models
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-flash-latest,gemini-flash-lite-latest")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

# RAG & Chunking Settings
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
# Standardized maximum cosine distance for ChromaDB vector search (0.0 = identical, 1.0 = orthogonal).
# For gemini-embedding-001:
# - Highly relevant: distance 0.15 - 0.36 (similarity 0.64 - 0.85)
# - Weak / unrelated noise: distance >= 0.41 (similarity <= 0.59)
# Standardized setting: RAG_MAX_COSINE_DISTANCE (default: 0.38)
RAG_MAX_COSINE_DISTANCE = float(
    os.getenv("RAG_MAX_COSINE_DISTANCE", os.getenv("RAG_RELEVANCE_THRESHOLD", "0.38"))
)
# Backward-compatibility alias
RAG_RELEVANCE_THRESHOLD = RAG_MAX_COSINE_DISTANCE
# Relative distance margin from top-ranked chunk to avoid trailing noise chunks
RAG_SCORE_MARGIN = float(os.getenv("RAG_SCORE_MARGIN", "0.10"))

# Conversation memory
CHAT_HISTORY_TURNS = max(0, int(os.getenv("CHAT_HISTORY_TURNS", "6")))
CHAT_RETENTION_DAYS = max(0, int(os.getenv("CHAT_RETENTION_DAYS", "30")))
USE_GRAPH_PIPELINE = os.getenv("USE_GRAPH_PIPELINE", "false").lower() in ("true", "1", "yes")
RESEARCH_MAX_MODEL_CALLS = max(1, int(os.getenv("RESEARCH_MAX_MODEL_CALLS", "8")))

# Crawler & Security Settings
APPROVED_DOMAINS = [
    d.strip().lower()
    for d in os.getenv("APPROVED_DOMAINS", "astu.edu.et,portal.astu.edu.et").split(",")
    if d.strip()
]
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", "15"))
CRAWL_TIMEOUT_SECONDS = int(os.getenv("CRAWL_TIMEOUT_SECONDS", "10"))
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(10 * 1024 * 1024)))  # 10 MB

# Request rate limiting
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")
RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")
CHAT_RATE_LIMIT = os.getenv("CHAT_RATE_LIMIT", "60/minute")
ADMIN_RATE_LIMIT = os.getenv("ADMIN_RATE_LIMIT", "10/minute")

# Runtime and admin security
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
REQUIRE_ADMIN_AUTH = os.getenv("REQUIRE_ADMIN_AUTH", "true").lower() in ("true", "1", "yes")


def validate_production_security(app_env: str = APP_ENV, admin_api_key: str = ADMIN_API_KEY) -> None:
    """Refuse production startup when administrative authentication is unusable."""
    if app_env in {"production", "prod"} and not admin_api_key.strip():
        raise RuntimeError(
            "Production startup refused: ADMIN_API_KEY must be configured."
        )


validate_production_security()


def validate_cors_origins(
    app_env: str = APP_ENV,
    origins: list[str] = CORS_ORIGINS,
) -> None:
    """Require explicit, non-wildcard browser origins in production."""
    normalized = {origin.strip() for origin in origins if origin.strip()}
    if app_env in {"production", "prod"} and (not normalized or "*" in normalized):
        raise RuntimeError(
            "Production startup refused: CORS_ORIGINS must contain explicit origins."
        )


validate_cors_origins()

# Database (PostgreSQL / Neon)
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_PRE_PING = os.getenv("DB_POOL_PRE_PING", "true").lower() in ("true", "1", "yes")
