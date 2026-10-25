"""Optional LangGraph orchestration around the existing RAG service."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, TypedDict

from google.genai import types
from langgraph.graph import END, StateGraph

from app.schemas.chat import SourceCitation
from app.services.rag import SYSTEM_INSTRUCTION, RAGService, rag_service


MAX_TOOL_CALLS = 2
MAX_TOOL_RESULTS = 8
_ABSTENTION_REPLY = (
    "I could not verify that answer against the indexed ASTU sources. "
    "Please check https://www.astu.edu.et or https://portal.astu.edu.et for official information."
)


class GraphState(TypedDict, total=False):
    message: str
    session_history: List[Dict[str, Any]]
    classification: Literal["greeting", "factual", "general", "out_of_scope"]
    rewritten_query: str
    retrieved_chunks: List[Dict[str, Any]]
    draft_answer: str
    sources: List[SourceCitation]
    diagnostics: Dict[str, Any]
    citation_check: Dict[str, Any]
    final_answer: str
    tool_calls: int
    tool_call_names: List[str]
    trace: List[Dict[str, Any]]


def _tool_declarations() -> List[types.Tool]:
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="search_astu_documents",
                    description="Search verified indexed ASTU documents for an answer.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "query": {"type": "STRING", "description": "The focused ASTU search query."},
                            "max_results": {
                                "type": "INTEGER",
                                "description": "Maximum number of indexed chunks to return, from 1 to 8.",
                            },
                        },
                        "required": ["query", "max_results"],
                    },
                ),
                types.FunctionDeclaration(
                    name="get_academic_calendar",
                    description="Search the indexed ASTU academic calendar chunks for an academic year.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "academic_year": {
                                "type": "STRING",
                                "description": "Academic year such as 2026/2027.",
                            }
                        },
                        "required": ["academic_year"],
                    },
                ),
            ]
        )
    ]


TOOL_DECLARATIONS = _tool_declarations()


def _validate_query(query: Any) -> str:
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > 2000:
        raise ValueError("query must be a non-empty string of at most 2000 characters")
    return query.strip()


def _validate_max_results(max_results: Any) -> int:
    if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= MAX_TOOL_RESULTS:
        raise ValueError("max_results must be an integer from 1 to 8")
    return max_results


def _safe_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": chunk.get("id"),
        "text": str(chunk.get("text", "")),
        "metadata": dict(chunk.get("metadata", {})),
        "distance": chunk.get("distance", 1.0),
        "relevance_score": chunk.get("relevance_score", 0.0),
        "token_overlap": chunk.get("token_overlap", 0),
    }


def search_astu_documents(query: str, max_results: int = 4) -> List[Dict[str, Any]]:
    """Search the existing verified retrieval index for tool callers."""
    clean_query = _validate_query(query)
    clean_max_results = _validate_max_results(max_results)
    chunks, _ = rag_service.retrieve_chunks(clean_query, top_k=clean_max_results)
    return [_safe_chunk(chunk) for chunk in chunks]


def get_academic_calendar(academic_year: str) -> List[Dict[str, Any]]:
    """Return only indexed calendar chunks matching the requested year."""
    if not isinstance(academic_year, str) or len(academic_year.strip()) > 32:
        raise ValueError("academic_year must be a string of at most 32 characters")
    year = academic_year.strip()
    query = f"academic calendar {year}" if year else "academic calendar"
    chunks, _ = rag_service.retrieve_chunks(query, top_k=MAX_TOOL_RESULTS)
    filtered = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        title = str(metadata.get("source_title", "")).lower()
        text = str(chunk.get("text", ""))
        searchable = f"{title} {text}".lower()
        if "calendar" not in searchable:
            continue
        if year and year.lower() not in searchable:
            continue
        filtered.append(_safe_chunk(chunk))
    return filtered


def _extract_function_calls(response: Any) -> List[Any]:
    direct = getattr(response, "function_calls", None)
    if direct:
        return list(direct)
    calls: List[Any] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                calls.append(function_call)
    return calls


def _call_name_and_args(call: Any) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    if isinstance(call, dict):
        name = call.get("name")
        args = call.get("args", call.get("arguments"))
    else:
        name = getattr(call, "name", None)
        args = getattr(call, "args", None)
    return name if isinstance(name, str) else None, args if isinstance(args, dict) else None


def _is_greeting(message: str) -> bool:
    normalized = re.sub(r"[^a-z ]", "", message.lower()).strip()
    return normalized in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "thanks",
        "thank you",
    }


def _classify(message: str) -> str:
    if _is_greeting(message):
        return "greeting"
    lowered = message.lower()
    if any(
        term in lowered
        for term in (
            "study",
            "exam",
            "programming",
            "learn",
            "prepare",
            "time management",
        )
    ):
        return "general"
    if any(
        term in lowered
        for term in (
            "astu",
            "university",
            "campus",
            "student",
            "registration",
            "admission",
            "calendar",
            "deadline",
            "dorm",
            "clinic",
            "office",
            "portal",
            "academic",
        )
    ):
        return "factual"
    return "out_of_scope"


class GraphPipeline:
    """Compile and invoke the optional graph while delegating RAG logic."""

    def __init__(self, service: RAGService = rag_service):
        self.service = service
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(GraphState)
        workflow.add_node("classify", self.classify_node)
        workflow.add_node("rewrite", self.rewrite_node)
        workflow.add_node("retrieve", self.retrieve_node)
        workflow.add_node("generate", self.generate_node)
        workflow.add_node("verify_citations", self.verify_citations_node)
        workflow.add_node("answer_or_abstain", self.answer_or_abstain_node)
        workflow.set_entry_point("classify")
        workflow.add_conditional_edges(
            "classify",
            self.route_after_classify,
            {"greeting": "answer_or_abstain", "continue": "rewrite"},
        )
        workflow.add_edge("rewrite", "retrieve")
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", "verify_citations")
        workflow.add_edge("verify_citations", "answer_or_abstain")
        workflow.add_edge("answer_or_abstain", END)
        return workflow.compile()

    @staticmethod
    def _trace(state: GraphState, node: str, **details: Any) -> List[Dict[str, Any]]:
        """Append redacted node facts without retaining user text or secrets."""
        return [*state.get("trace", []), {"node": node, **details}]

    def classify_node(self, state: GraphState) -> Dict[str, Any]:
        classification = _classify(state["message"])
        return {
            "classification": classification,
            "trace": self._trace(state, "classify", classification=classification),
        }

    def route_after_classify(self, state: GraphState) -> str:
        return "greeting" if state.get("classification") == "greeting" else "continue"

    def rewrite_node(self, state: GraphState) -> Dict[str, Any]:
        if state.get("classification") == "out_of_scope":
            return {
                "rewritten_query": state["message"],
                "trace": self._trace(
                    state,
                    "rewrite",
                    skipped=True,
                    changed=False,
                    reason="out_of_scope",
                ),
            }
        rewritten_query = self.service.rewrite_follow_up(
            state["message"], state.get("session_history", [])
        )
        return {
            "rewritten_query": rewritten_query,
            "trace": self._trace(
                state,
                "rewrite",
                skipped=False,
                changed=rewritten_query != state["message"].strip(),
            ),
        }

    def _normal_retrieval(self, query: str) -> List[Dict[str, Any]]:
        chunks, _ = self.service.retrieve_chunks(query)
        return chunks

    def _tool_retrieval(self, state: GraphState) -> Dict[str, Any]:
        query = state.get("rewritten_query", state["message"])
        prompt = (
            "Choose an indexed ASTU search tool for this factual question. "
            "Use a function call only when indexed evidence is needed. "
            "Do not answer the question in this routing step.\n"
            f"Question: {state['message']}\nSearch query: {query}"
        )
        try:
            response = self.service._generate_with_retry_and_fallback(
                prompt,
                generation_config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=TOOL_DECLARATIONS,
                ),
                accept_function_calls=True,
            )
            calls = _extract_function_calls(response)
            if not calls:
                return {
                    "retrieved_chunks": self._normal_retrieval(query),
                    "tool_calls": 0,
                    "tool_call_names": [],
                    "retrieval_mode": "normal_fallback",
                    "retrieval_fallback_reason": "no_tool_call",
                }
            retrieved: List[Dict[str, Any]] = []
            names: List[str] = []
            for call in calls[:MAX_TOOL_CALLS]:
                name, args = _call_name_and_args(call)
                if name not in {"search_astu_documents", "get_academic_calendar"} or args is None:
                    return {
                        "retrieved_chunks": self._normal_retrieval(query),
                        "tool_calls": 0,
                        "tool_call_names": [],
                        "retrieval_mode": "normal_fallback",
                        "retrieval_fallback_reason": "malformed_tool_call",
                    }
                if name == "search_astu_documents":
                    result = search_astu_documents(**args)
                else:
                    result = get_academic_calendar(**args)
                names.append(name)
                retrieved.extend(result)

            unique = {str(chunk.get("id")): chunk for chunk in retrieved}
            if not unique:
                return {
                    "retrieved_chunks": self._normal_retrieval(query),
                    "tool_calls": len(names),
                    "tool_call_names": names,
                    "retrieval_mode": "normal_fallback",
                    "retrieval_fallback_reason": "empty_tool_result",
                }
            return {
                "retrieved_chunks": list(unique.values()),
                "tool_calls": len(names),
                "tool_call_names": names,
                "retrieval_mode": "tool",
            }
        except (TypeError, ValueError, KeyError):
            return {
                "retrieved_chunks": self._normal_retrieval(query),
                "tool_calls": 0,
                "tool_call_names": [],
                "retrieval_mode": "normal_fallback",
                "retrieval_fallback_reason": "invalid_tool_arguments",
            }
        except Exception:
            return {
                "retrieved_chunks": self._normal_retrieval(query),
                "tool_calls": 0,
                "tool_call_names": [],
                "retrieval_mode": "normal_fallback",
                "retrieval_fallback_reason": "tool_error",
            }

    def retrieve_node(self, state: GraphState) -> Dict[str, Any]:
        if state.get("classification") == "out_of_scope":
            return {
                "retrieved_chunks": [],
                "tool_calls": 0,
                "tool_call_names": [],
                "retrieval_mode": "skipped",
                "trace": self._trace(state, "retrieve", mode="skipped", retrieved_count=0),
            }
        if state.get("classification") == "factual":
            result = self._tool_retrieval(state)
            return {
                **result,
                "trace": self._trace(
                    state,
                    "retrieve",
                    mode=result.get("retrieval_mode", "unknown"),
                    fallback_reason=result.get("retrieval_fallback_reason"),
                    tool_calls=result.get("tool_calls", 0),
                    tool_call_names=result.get("tool_call_names", []),
                    retrieved_count=len(result.get("retrieved_chunks", [])),
                ),
            }
        result = {
            "retrieved_chunks": self._normal_retrieval(state.get("rewritten_query", state["message"])),
            "tool_calls": 0,
            "tool_call_names": [],
            "retrieval_mode": "normal",
        }
        return {
            **result,
            "trace": self._trace(
                state,
                "retrieve",
                mode="normal",
                tool_calls=0,
                retrieved_count=len(result["retrieved_chunks"]),
            ),
        }

    def generate_node(self, state: GraphState) -> Dict[str, Any]:
        if state.get("classification") == "out_of_scope":
            chunks = None
        else:
            chunks = state.get("retrieved_chunks", [])
        answer, sources, diagnostics = self.service.answer_question_with_diagnostics(
            state["message"],
            retrieval_question=state.get("rewritten_query"),
            history=state.get("session_history", []),
            retrieved_chunks=chunks,
        )
        return {
            "draft_answer": answer,
            "sources": sources,
            "diagnostics": diagnostics,
            "trace": self._trace(
                state,
                "generate",
                grounding_status=diagnostics.get("grounding_status"),
                retrieved_count=diagnostics.get("retrieved_count", 0),
                source_count=len(sources),
                draft_nonempty=bool(answer.strip()),
            ),
        }

    def verify_citations_node(self, state: GraphState) -> Dict[str, Any]:
        classification = state.get("classification")
        diagnostics = state.get("diagnostics", {})
        sources = state.get("sources", [])
        passed = classification == "general" or (
            bool(sources)
            and diagnostics.get("grounding_status") in {"grounded", "navigational"}
        )
        return {
            "citation_check": {
                "passed": passed,
                "citations_count": len(sources),
                "grounding_status": diagnostics.get("grounding_status"),
            },
            "trace": self._trace(
                state,
                "verify_citations",
                passed=passed,
                citations_count=len(sources),
                grounding_status=diagnostics.get("grounding_status"),
            ),
        }

    def answer_or_abstain_node(self, state: GraphState) -> Dict[str, Any]:
        if state.get("classification") == "greeting":
            return {
                "final_answer": "Hello! I can help with ASTU information, campus navigation, and study guidance.",
                "sources": [],
                "trace": self._trace(state, "answer_or_abstain", outcome="greeting"),
            }
        if state.get("citation_check", {}).get("passed"):
            return {
                "final_answer": state.get("draft_answer", ""),
                "trace": self._trace(state, "answer_or_abstain", outcome="answer"),
            }
        return {
            "final_answer": _ABSTENTION_REPLY,
            "sources": [],
            "trace": self._trace(state, "answer_or_abstain", outcome="abstain"),
        }

    def invoke(self, message: str, session_history: Optional[List[Dict[str, Any]]] = None) -> GraphState:
        return self.graph.invoke(
            {"message": message, "session_history": session_history or []}
        )

    def mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()


graph_pipeline = GraphPipeline()
