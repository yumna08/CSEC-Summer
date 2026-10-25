import pytest

from app.core.config import validate_cors_origins


def test_production_cors_rejects_wildcard():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        validate_cors_origins("production", ["*"])


def test_production_cors_rejects_empty_origins():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        validate_cors_origins("production", [])


def test_development_cors_accepts_configured_origins():
    validate_cors_origins("development", ["http://localhost:3000"])
