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

# Crawler & Security Settings
APPROVED_DOMAINS = [
    d.strip().lower()
    for d in os.getenv("APPROVED_DOMAINS", "astu.edu.et,portal.astu.edu.et").split(",")
    if d.strip()
]
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", "15"))
CRAWL_TIMEOUT_SECONDS = int(os.getenv("CRAWL_TIMEOUT_SECONDS", "10"))
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(10 * 1024 * 1024)))  # 10 MB

# Admin Security Key (optional in dev, recommended in production)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
REQUIRE_ADMIN_AUTH = os.getenv("REQUIRE_ADMIN_AUTH", "false").lower() in ("true", "1", "yes")

# Database (PostgreSQL / Neon)
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_PRE_PING = os.getenv("DB_POOL_PRE_PING", "true").lower() in ("true", "1", "yes")
