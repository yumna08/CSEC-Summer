# ASTU CampusGuide AI architecture

The browser talks to a FastAPI backend. The backend keeps the established
retrieval, citation-verification, and abstention behavior, with optional
LangGraph orchestration selected by `USE_GRAPH_PIPELINE=true`. Conversation
turns use PostgreSQL when available and an explicit process-local fallback when
the database is offline; Chroma remains the document retrieval store.

```mermaid
flowchart LR
    Browser[Next.js frontend] --> API[FastAPI API]
    API --> Memory[(PostgreSQL chat memory)]
    API --> Fallback[In-memory fallback]
    API --> Pipeline{Legacy or LangGraph}
    Pipeline --> Chroma[(ChromaDB indexed chunks)]
    Pipeline --> Gemini[Gemini generation and embeddings]
    Pipeline --> Verify[Citation verifier and abstention]
    Verify --> API

    subgraph Graph[Optional LangGraph workflow]
        START([chat request]) --> classify
        classify -->|greeting| answer_or_abstain
        classify -->|factual, general, or out of scope| rewrite
        rewrite --> retrieve
        retrieve --> generate
        generate --> verify_citations
        verify_citations --> answer_or_abstain
        answer_or_abstain --> END([response])
        retrieve -. factual tool call .-> search_astu_documents
        retrieve -. calendar tool call .-> get_academic_calendar
        search_astu_documents -. indexed chunks .-> generate
        get_academic_calendar -. indexed calendar chunks .-> generate
    end
```

The graph caps tool calls at two per request and falls back to the normal
retrieval function when a function call is malformed or unavailable. Retrieved
text and conversation history remain untrusted data; the existing Gemini
grounding instruction and independent citation verifier remain authoritative.
