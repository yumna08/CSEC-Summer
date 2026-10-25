import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import validate_production_security


def test_production_security_requires_admin_key():
    with pytest.raises(RuntimeError, match="ADMIN_API_KEY must be configured"):
        validate_production_security("production", "")


def test_non_production_can_run_without_admin_key():
    validate_production_security("development", "")
    validate_production_security("testing", "")


def test_production_import_refuses_empty_admin_key():
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "production",
            "ADMIN_API_KEY": "",
            "DATABASE_URL": "sqlite:///:memory:",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "Production startup refused" in result.stderr
