import importlib
import sys
from unittest.mock import patch

import pytest

# The global test harness aliases httpx2 to httpx for Starlette's local
# TestClient workaround. MCP 2.x needs its real httpx2 package instead.
sys.modules.pop("httpx2", None)
importlib.import_module("httpx2")

from app.mcp_server import search_campus_knowledge, sources_catalog


def chunk(chunk_id="chunk-1"):
    return {
        "id": chunk_id,
        "text": "ASTU Registrar handles registration.",
        "metadata": {
            "source_title": "ASTU Registrar and Alumni Executive",
            "source_url": "https://www.astu.edu.et/registrar",
            "academic_year": "2026/2027",
        },
    }


def test_search_returns_indexed_chunk_fields():
    with patch(
        "app.mcp_server.rag_service.retrieve_chunks",
        return_value=([chunk()], False),
    ) as retrieve:
        result = search_campus_knowledge("registration", 3)

    retrieve.assert_called_once_with("registration", top_k=3)
    assert result == {
        "status": "ok",
        "results": [
            {
                "chunk_id": "chunk-1",
                "text": "ASTU Registrar handles registration.",
                "source_title": "ASTU Registrar and Alumni Executive",
                "url": "https://www.astu.edu.et/registrar",
                "academic_year": "2026/2027",
            }
        ],
    }


def test_search_returns_explicit_empty_result():
    with patch("app.mcp_server.rag_service.retrieve_chunks", return_value=([], False)):
        assert search_campus_knowledge("bookstore", 5) == {
            "status": "no indexed evidence",
            "results": [],
        }


def test_search_caps_results_to_requested_maximum():
    chunks = [chunk(f"chunk-{index}") for index in range(5)]
    with patch("app.mcp_server.rag_service.retrieve_chunks", return_value=(chunks, False)) as retrieve:
        result = search_campus_knowledge("registration", 2)

    retrieve.assert_called_once_with("registration", top_k=2)
    assert len(result["results"]) == 2


@pytest.mark.parametrize(
    ("query", "max_results"),
    [("", 2), ("registration", 0), ("registration", 6), ("registration", True)],
)
def test_search_rejects_invalid_input(query, max_results):
    with pytest.raises(ValueError):
        search_campus_knowledge(query, max_results)


def test_sources_catalog_reads_indexed_documents_only():
    source = {"doc_id": "doc-1", "source_title": "ASTU Registrar"}
    with patch("app.mcp_server.vector_store.list_documents", return_value=[source]):
        assert sources_catalog() == {"sources": [source]}
