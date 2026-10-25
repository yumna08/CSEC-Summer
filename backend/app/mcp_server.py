"""Read-only MCP server for indexed ASTU campus knowledge.

Run directly with the official MCP SDK's stdio transport:
``python backend/app/mcp_server.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Make direct execution work for Claude Desktop, whose working directory is
# not guaranteed to be the backend directory.
if __package__ in {None, ""}:  # pragma: no cover - exercised by process startup
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.mcpserver import MCPServer

from app.services.rag import rag_service
from app.services.vector_store import vector_store


MAX_RESULTS = 5
NO_INDEXED_EVIDENCE = "no indexed evidence"


def _validate_search_input(query: Any, max_results: Any) -> tuple[str, int]:
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > 2000:
        raise ValueError("query must be a non-empty string of at most 2000 characters")
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise ValueError("max_results must be an integer from 1 to 5")
    if not 1 <= max_results <= MAX_RESULTS:
        raise ValueError("max_results must be an integer from 1 to 5")
    return query.strip(), max_results


def _format_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    metadata = chunk.get("metadata") or {}
    return {
        "chunk_id": chunk.get("id"),
        "text": str(chunk.get("text", "")),
        "source_title": str(metadata.get("source_title", "")),
        "url": metadata.get("source_url") or None,
        "academic_year": metadata.get("academic_year") or None,
    }


def search_campus_knowledge(query: str, max_results: int = MAX_RESULTS) -> Dict[str, Any]:
    """Search only the existing indexed ASTU chunks; never synthesize results."""
    clean_query, clean_max_results = _validate_search_input(query, max_results)
    chunks, _ = rag_service.retrieve_chunks(clean_query, top_k=clean_max_results)
    results = [_format_chunk(chunk) for chunk in chunks[:clean_max_results]]
    if not results:
        return {"status": NO_INDEXED_EVIDENCE, "results": []}
    return {"status": "ok", "results": results}


def _source_dict(source: Any) -> Dict[str, Any]:
    if hasattr(source, "model_dump"):
        return source.model_dump()
    if hasattr(source, "to_dict"):
        return source.to_dict()
    if isinstance(source, dict):
        return dict(source)
    return {"source": str(source)}


def sources_catalog() -> Dict[str, Any]:
    """Return the indexed document catalog without exposing mutation operations."""
    return {"sources": [_source_dict(source) for source in vector_store.list_documents()]}


mcp_server = MCPServer(
    name="astu-campusguide",
    title="ASTU CampusGuide Knowledge",
    description="Read-only search over indexed ASTU campus documents.",
    version="0.1.0",
)


@mcp_server.tool(
    name="search_campus_knowledge",
    description="Search indexed ASTU documents. Returns no indexed evidence when nothing passes retrieval."
)
def search_campus_knowledge_tool(query: str, max_results: int = MAX_RESULTS) -> Dict[str, Any]:
    return search_campus_knowledge(query, max_results)


@mcp_server.resource(
    "astu://sources/catalog",
    name="astu_sources_catalog",
    description="Catalog of indexed ASTU sources.",
    mime_type="application/json",
)
def sources_catalog_resource() -> str:
    return json.dumps(sources_catalog(), ensure_ascii=False)


if __name__ == "__main__":  # pragma: no cover - transport loop
    mcp_server.run("stdio")
