# ASTU CampusGuide AI

ASTU CampusGuide AI is a FastAPI + ChromaDB + Gemini backend with a Next.js
student chat interface. It answers ASTU questions from verified indexed
documents, cites the supporting sources, and abstains when the indexed evidence
cannot support a factual answer.

## Architecture

```mermaid
flowchart LR
    UI[Next.js chat UI] --> API[FastAPI]
    API --> RAG[RAG service]
    RAG --> Chroma[(ChromaDB)]
    RAG --> Gemini[Gemini API]
    RAG --> Verify[Citation verification]
    Verify --> API
    API --> Memory[(PostgreSQL)]
    API -. database unavailable .-> Local[In-memory session fallback]
    API --> UI
```

The default chat route uses the existing RAG pipeline. Set
`USE_GRAPH_PIPELINE=true` to select the optional LangGraph workflow; both
paths keep the same chat response contract and reuse the existing retrieval,
grounding, citation, and abstention logic. See [docs/architecture.md](docs/architecture.md)
for the detailed graph.

The saved six-question graph diagnosis is documented in
[docs/graph-diagnosis-c1.md](docs/graph-diagnosis-c1.md). A corrected
12-question real-model comparison was not produced because Gemini quota and
fallback availability were blocked; the default remains `USE_GRAPH_PIPELINE=false`.

The read-only MCP server is documented in [docs/mcp.md](docs/mcp.md). It
provides indexed knowledge search and the `astu://sources/catalog` resource;
it has no ingestion, deletion, or reindex operations.

## Setup without Docker

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GEMINI_API_KEY and ADMIN_API_KEY.
uvicorn app.main:app --reload --port 8000
```

Frontend, in a second terminal:

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

The API is available at `http://localhost:8000`; the UI is available at
`http://localhost:3000`. PostgreSQL is optional for local development because
chat memory falls back to process-local memory when `DATABASE_URL` is empty or
unavailable. Chroma data is stored under `backend/data/chroma_db` locally.

## Setup with Docker Compose

Docker Compose runs PostgreSQL, the backend, and the frontend. Secrets are
runtime environment values and are excluded from both image build contexts.

```bash
export POSTGRES_PASSWORD='use-a-local-password'
export GEMINI_API_KEY='your-real-gemini-key'
export ADMIN_API_KEY='use-a-long-random-admin-key'
docker compose up --build
```

The API health endpoint is `http://localhost:8000/api/health`. Chroma is stored
in the named `chroma_data` volume and PostgreSQL data is stored in
`postgres_data`.

## Environment variables

Backend variables are documented in `backend/.env.example`:

| Variable | Purpose | Example/default |
| --- | --- | --- |
| `DATA_DIR` | Local data root | `data` |
| `CHROMA_PERSIST_DIR` | Chroma persistence directory | `data/chroma_db` |
| `REGISTRY_FILE` | Source registry file | `data/source_registry.json` |
| `GEMINI_API_KEY` | Gemini credential | `replace-with-a-gemini-api-key` |
| `GEMINI_MODEL` | Primary Gemini model | `gemini-2.5-flash` |
| `GEMINI_FALLBACK_MODEL` | Comma-separated fallback models | `gemini-flash-latest,gemini-flash-lite-latest` |
| `GEMINI_EMBEDDING_MODEL` | Embedding model | `gemini-embedding-001` |
| `GEMINI_MAX_RETRIES` | Retry count per model | `2` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Ingestion chunking | `800` / `150` |
| `RAG_TOP_K` | Retrieved chunk count | `4` |
| `RAG_MAX_COSINE_DISTANCE` | Retrieval distance cutoff | `0.38` |
| `RAG_RELEVANCE_THRESHOLD` | Backward-compatible cutoff alias | `0.38` |
| `RAG_SCORE_MARGIN` | Relative retrieval margin | `0.10` |
| `CHAT_HISTORY_TURNS` | Recent turns in prompts | `6` |
| `CHAT_RETENTION_DAYS` | Session retention period | `30` |
| `USE_GRAPH_PIPELINE` | Select LangGraph path | `false` |
| `RESEARCH_MAX_MODEL_CALLS` | Research model-call cap | `8` |
| `APPROVED_DOMAINS` | Allowed ingestion domains | `astu.edu.et,portal.astu.edu.et` |
| `MAX_CRAWL_PAGES` | Website crawl limit | `15` |
| `CRAWL_TIMEOUT_SECONDS` | Crawler timeout | `10` |
| `MAX_UPLOAD_SIZE_BYTES` | Upload size limit | `10485760` |
| `RATE_LIMIT_ENABLED` | Enable request limits | `true` |
| `RATE_LIMIT_STORAGE_URI` | Rate-limit storage | `memory://` |
| `CHAT_RATE_LIMIT` | Chat limit | `60/minute` |
| `ADMIN_RATE_LIMIT` | Admin limit | `10/minute` |
| `LOG_LEVEL` | Structured log level | `INFO` |
| `APP_ENV` | Runtime environment | `development` |
| `ADMIN_API_KEY` | Admin endpoint credential | `replace-with-a-long-random-admin-key` |
| `REQUIRE_ADMIN_AUTH` | Require admin auth | `true` |
| `CORS_ORIGINS` | Comma-separated browser origins | `http://localhost:3000,http://127.0.0.1:3000` |
| `DATABASE_URL` | SQLAlchemy database URL | `postgresql+psycopg://user:password@localhost:5432/campusguide` |
| `DB_POOL_SIZE` | Database pool size | `5` |
| `DB_MAX_OVERFLOW` | Extra pool connections | `10` |
| `DB_POOL_PRE_PING` | Validate pooled connections | `true` |

Frontend uses `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.example`.
Compose additionally supports `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `BACKEND_PORT`, and `FRONTEND_PORT`.

In production, `ADMIN_API_KEY` must be non-empty and `CORS_ORIGINS` must contain
explicit origins; wildcard CORS is rejected.

## Ingesting documents

Admin-protected ingestion endpoints accept approved ASTU URLs, registered
websites, and PDF/DOCX/TXT/Markdown uploads. Example:

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest-url \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -d '{"url":"https://www.astu.edu.et/","verification_status":"verified"}'
```

Other endpoints are `POST /api/knowledge/ingest-websites`,
`POST /api/knowledge/upload`, and `POST /api/knowledge/reindex`. The source
registry and indexed document status are available through the read-only
knowledge endpoints.

## Research reports

`POST /api/research` accepts `{ "topic": "..." }` and returns a structured
report with a summary, sub-question steps, grounded citations, required
documents, contacts, and unsupported or missing items. The workflow plans at
most four sub-questions, uses the legacy retriever for each, and stops when
`RESEARCH_MAX_MODEL_CALLS` is reached. It explicitly says when the indexed
knowledge base does not cover part of the topic.

## Tests and evaluation

From the repository root:

```bash
backend/.venv/bin/pytest -q --timeout=60
cd backend && ./.venv/bin/pytest -q --timeout=60 && cd ..
cd frontend && npm run lint && npx tsc --noEmit && cd ..
POSTGRES_PASSWORD=dummy docker compose config
```

The deterministic evaluation never calls Gemini:

```bash
cd backend
./.venv/bin/python scripts/evaluate_rag.py --output ../docs/rag-mocked.json
```

The quota-safe real evaluator accepts `--real`, requires `1 <= --limit <= 20`,
adds a delay between model calls, and keeps legacy and graph artifacts separate:

```bash
./.venv/bin/python scripts/evaluate_rag.py --real --limit 6 \
  --delay-seconds 1.5 --output ../docs/rag-real-model-legacy-6q.json
USE_GRAPH_PIPELINE=true ./.venv/bin/python scripts/evaluate_rag.py --real --graph --limit 6 \
  --delay-seconds 1.5 --output ../docs/rag-real-model-graph-6q.json
```

### Stage A real-model results

These are the measured six-question artifacts committed under `docs/`. They
were captured before the general-advice scoring correction; the run could not
be honestly repeated afterward because the observed Gemini quota/high-demand
fallback errors exhausted the available evaluation capacity.

| Pipeline | Accuracy | Citation correctness | Abstention rate | Average latency | Model calls/question |
| --- | ---: | ---: | ---: | ---: | ---: |
| Legacy | 0.8333 | 0.8333 | 0.1667 | 8963.413 ms | 2.0 |
| Graph | 0.5 | 0.5 | 0.3333 | 18272.554 ms | 3.833 |

Failed questions recorded by the saved pre-correction artifacts were: legacy
`adv-01` (the scoring bug classified citation-free general advice as a
retrieval miss/bad citation); graph `cal-01` (bad citation), `reg-02` (wrong
abstention and bad citation), and `adv-01` (the same scoring bug plus the
corresponding retrieval label). The scorer now treats citation-free general
advice separately; a corrected real rerun remains required.

## Data storage and retention

The app stores opaque chat session UUIDs, user messages, assistant replies,
timestamps, and cited source identifiers for assistant turns. It does not
store student names, student IDs, grades, enrollment records, or other private
student-system data. Sessions are retained for `CHAT_RETENTION_DAYS` (default
30) and can also be deleted with `DELETE /api/chat/sessions/{id}`. When the
database is offline, the fallback store lasts only for the backend process
lifetime and is clearly logged. Indexed source text and metadata are stored in
Chroma; ingestion metadata is stored in the configured SQL database.

## What the assistant refuses to answer and why

It refuses or abstains on ASTU-specific claims when no indexed, verified chunk
supports the claim, when citation verification fails, or when the request is
outside the supported campus-information scope. This prevents invented fees,
deadlines, locations, officials, and policies. It may still provide general
study guidance without ASTU citations when the question is clearly general.

## Known limitations

- The captured real comparison is not yet a corrected apples-to-apples graph
  benchmark because quota prevented rerunning after the scoring fix; the graph
  result was lower on that observed run.
- Rate limiting defaults to in-memory storage and is not shared across workers.
- PostgreSQL table initialization is additive at startup; a production schema
  migration process should be added before frequent schema evolution.
- The current repository does not yet include the research-agent endpoint or
  optional tracing backend.
- Retrieval quality depends on the freshness and coverage of the approved
  indexed sources; unsupported university facts remain unavailable.
