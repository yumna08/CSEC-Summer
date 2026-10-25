"""Keep the test suite isolated from developer services and local data."""

import os
import shutil
import tempfile
from pathlib import Path


_TEST_RUNTIME_DIR = Path(tempfile.mkdtemp(prefix="campusguide-tests-"))

# These values must be set before application modules are imported. In
# particular, SourceRegistry is created during app import and must never try
# to connect to a developer's PostgreSQL/Neon database during tests.
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_RUNTIME_DIR / 'test.db'}"
os.environ["DATA_DIR"] = str(_TEST_RUNTIME_DIR / "data")
os.environ["CHROMA_PERSIST_DIR"] = str(_TEST_RUNTIME_DIR / "chroma_db")
os.environ["REGISTRY_FILE"] = str(_TEST_RUNTIME_DIR / "source_registry.json")
os.environ.setdefault("GEMINI_API_KEY", "")

_TEST_DATA_DIR = _TEST_RUNTIME_DIR / "data"
_TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
shutil.copyfile(
    Path(__file__).parent / "data" / "evaluation_dataset.json",
    _TEST_DATA_DIR / "evaluation_dataset.json",
)

# Some transitive dependencies install the experimental ``httpx2`` package.
# Starlette prefers it when present, but the current TestClient integration in
# this environment blocks on a basic request. Force Starlette's test client to
# use the stable httpx package required by this project instead.
import httpx  # noqa: E402
import sys  # noqa: E402
import asyncio  # noqa: E402
from typing import Any  # noqa: E402

sys.modules["httpx2"] = httpx

from app.db.database import get_engine  # noqa: E402
from app.db.init_db import init_db  # noqa: E402


# Create the local schema before app.main imports the global source registry.
init_db(get_engine())


async def _run_sync_without_worker_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run sync endpoint functions inline in this restricted test environment."""
    return func(*args, **kwargs)


# The execution environment cannot wake an asyncio loop from another thread,
# which makes Starlette's standard synchronous TestClient block. Running sync
# endpoints inline and driving ASGI with an async client keeps tests isolated
# without changing production behavior.
import anyio.to_thread  # noqa: E402

anyio.to_thread.run_sync = _run_sync_without_worker_thread


class LocalTestClient:
    __test__ = False

    def __init__(self, app: Any, base_url: str = "http://testserver", **_: Any):
        self.app = app
        self.base_url = base_url

    async def _request_async(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url=self.base_url) as client:
            return await client.request(method, url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return asyncio.run(self._request_async(method, url, **kwargs))

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def __enter__(self) -> "LocalTestClient":
        return self

    def __exit__(self, *_: Any) -> None:
        return None


import fastapi.testclient  # noqa: E402
import starlette.testclient  # noqa: E402

fastapi.testclient.TestClient = LocalTestClient
starlette.testclient.TestClient = LocalTestClient
