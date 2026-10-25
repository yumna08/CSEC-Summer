# MCP server

The repository includes a read-only MCP server using the official pinned
`mcp==2.3.0` SDK. It exposes no ingestion, deletion, reindex, admin, or write
operations.

## Exposed interfaces

- Tool `search_campus_knowledge(query, max_results)`: searches the existing
  RAG index, caps `max_results` at 5, and returns chunk text, source title, URL,
  and academic year. Empty retrieval returns the explicit status `no indexed
  evidence`.
- Resource `astu://sources/catalog`: returns the indexed document catalog as
  JSON.

The tool calls the existing `RAGService.retrieve_chunks` path, so its distance
threshold, lexical filtering, and embedding behavior are not duplicated or
changed.

## Run over stdio

From the repository root:

```bash
backend/.venv/bin/python backend/app/mcp_server.py
```

The process communicates over stdin/stdout. Do not add print statements to the
server because they would corrupt the MCP protocol stream.

## Claude Desktop configuration

Edit Claude Desktop's MCP configuration and replace the path with the absolute
repository path:

```json
{
  "mcpServers": {
    "astu-campusguide": {
      "command": "/absolute/path/to/CSEC summer/backend/.venv/bin/python",
      "args": [
        "/absolute/path/to/CSEC summer/backend/app/mcp_server.py"
      ],
      "env": {
        "GEMINI_API_KEY": "your-gemini-key",
        "CHROMA_PERSIST_DIR": "/absolute/path/to/CSEC summer/backend/data/chroma_db"
      }
    }
  }
}
```

The server needs the same read-only retrieval configuration as the backend. API
keys belong in the local client configuration or environment, never in the
repository or image.
