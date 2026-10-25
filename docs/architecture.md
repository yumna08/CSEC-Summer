# ASTU CampusGuide AI architecture

The default chat path remains the existing RAG pipeline. Set
`USE_GRAPH_PIPELINE=true` to use the optional LangGraph orchestration; both
paths return the same chat response shape and share retrieval, generation,
citation verification, abstention, and conversation memory services.

```mermaid
flowchart TD
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
```

The graph caps tool calls at two per request and falls back to the normal
retrieval function when a function call is malformed or unavailable. Retrieved
text and conversation history remain untrusted data; the existing Gemini
grounding instruction and independent citation verifier remain authoritative.
