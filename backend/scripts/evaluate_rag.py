"""Run the RAG evaluation dataset with either mocked or real model calls.

The default mode is deterministic and never calls Gemini. ``--real`` enables a
small, delayed run against the configured Gemini client and writes measured
results separately from the mocked artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Allow ``python scripts/evaluate_rag.py`` when launched from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import CHROMA_PERSIST_DIR, DATA_DIR
from app.core.config import (
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL,
)
from app.services.embeddings import embedding_service
from app.services.rag import RAGService, extract_substantive_tokens, is_source_location_query
from app.services.vector_store import VectorStoreService


class MockResponse:
    def __init__(self, text: str):
        self.text = text


class MockGeminiModels:
    def generate_content(self, *, model: str, contents: str, config: Any = None) -> MockResponse:
        question_match = re.search(r"Student Question: (.+)", contents)
        question = question_match.group(1).strip() if question_match else ""
        if "No verified ASTU-specific documents were retrieved" in contents:
            if any(term in question.lower() for term in ("study", "exam", "programming", "prepare")):
                return MockResponse(
                    "A useful approach is to set a specific study goal, divide it into timed sessions, and review your progress.\n\nSOURCES_USED: NONE"
                )
            return MockResponse(
                "Verified information for this ASTU-specific inquiry is not available in the indexed sources. "
                "Please check https://www.astu.edu.et or https://portal.astu.edu.et.\n\nSOURCES_USED: NONE"
            )

        blocks = re.findall(
            r"--- Reference Source \[(\d+)\]: (.*?) ---\n(.*?)(?=--- Reference Source \[|\Z)",
            contents,
            re.DOTALL,
        )
        if is_source_location_query(question) and blocks:
            index, header, _ = blocks[0]
            url_match = re.search(r"URL: (\S+)", header)
            url = url_match.group(1) if url_match and url_match.group(1) != "N/A" else "https://www.astu.edu.et"
            return MockResponse(f"The verified ASTU source is available at {url}.\n\nSOURCES_USED: [{index}]")

        index, _, evidence = blocks[0]
        evidence = " ".join(evidence.split())[:900]
        return MockResponse(f"The indexed ASTU reference states: {evidence}\n\nSOURCES_USED: [{index}]")


class MockGeminiClient:
    def __init__(self):
        self.models = MockGeminiModels()


class LexicalEvaluationStore:
    """Use persisted chunks with deterministic lexical retrieval for evaluation."""

    def __init__(self, persist_dir: Path):
        source_store = VectorStoreService(persist_dir=persist_dir)
        data = source_store.collection.get(include=["documents", "metadatas"])
        self.chunks = [
            {"id": item_id, "text": text, "metadata": metadata or {}}
            for item_id, text, metadata in zip(
                data.get("ids", []), data.get("documents", []), data.get("metadatas", [])
            )
        ]

    def similarity_search(self, *, top_k: int, query_tokens: set[str], is_navigational: bool, **_: Any) -> List[Dict[str, Any]]:
        scored = []
        for chunk in self.chunks:
            metadata = chunk["metadata"]
            searchable = " ".join(
                [
                    chunk["text"],
                    metadata.get("source_title", ""),
                    metadata.get("source_url", ""),
                ]
            ).lower()
            overlap = len({token for token in query_tokens if token in searchable})
            if overlap == 0 and is_navigational:
                title = metadata.get("source_title", "").lower()
                url = metadata.get("source_url", "").lower()
                if "homepage" in title or "portal.astu.edu.et" in url:
                    overlap = 1
            if overlap:
                item = dict(chunk)
                item["distance"] = max(0.12, 0.36 - (overlap * 0.02))
                item["relevance_score"] = 1.0 - item["distance"]
                item["token_overlap"] = overlap
                scored.append(item)
        scored.sort(key=lambda item: (item["token_overlap"], -item["distance"]), reverse=True)
        return scored[:top_k]


class CountingModels:
    """Count real Gemini calls and pace them without logging prompt contents."""

    def __init__(self, delegate: Any, counter: Dict[str, Any], delay_seconds: float):
        self._delegate = delegate
        self._counter = counter
        self._delay_seconds = delay_seconds

    def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        self._counter["model_calls"] += 1
        try:
            return self._delegate.generate_content(*args, **kwargs)
        finally:
            time.sleep(self._delay_seconds)

    def embed_content(self, *args: Any, **kwargs: Any) -> Any:
        self._counter["model_calls"] += 1
        try:
            return self._delegate.embed_content(*args, **kwargs)
        finally:
            time.sleep(self._delay_seconds)


class CountingClient:
    def __init__(self, delegate: Any, counter: Dict[str, Any], delay_seconds: float):
        self._delegate = delegate
        self.models = CountingModels(delegate.models, counter, delay_seconds)


def _select_questions(dataset: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    if not 1 <= limit <= 20:
        raise ValueError("--limit must be between 1 and 20")
    if limit >= len(dataset):
        return dataset
    preferred_categories = [
        "student_services",
        "admissions_and_registration",
        "academic_procedures",
        "official_contacts",
        "general_student_advice",
        "unindexed_missing_info",
    ]
    selected: List[Dict[str, Any]] = []
    for category in preferred_categories:
        item = next((entry for entry in dataset if entry["category"] == category), None)
        if item is not None:
            selected.append(item)
        if len(selected) == limit:
            return selected
    for item in dataset:
        if item not in selected:
            selected.append(item)
        if len(selected) == limit:
            break
    return selected


def _safe_error(error: Exception, api_key: str) -> str:
    message = str(error).replace(api_key, "[REDACTED]")
    return f"{error.__class__.__name__}: {message[:500]}"


def _score_result(item: Dict[str, Any], answer: str, sources: List[Any], diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    expected_behavior = item["expected_behavior"]
    is_general_advice = item.get("category") == "general_student_advice"
    source_text = " ".join(getattr(source, "title", "").lower() for source in sources)
    answer_text = answer.lower()
    expected_sources = [source.lower() for source in item["expected_sources"]]
    expected_terms = [term.lower() for term in item["required_evidence_terms"]]
    source_match = not expected_sources or any(source in source_text for source in expected_sources)
    evidence_match = not expected_terms or all(term in answer_text for term in expected_terms)
    actual_abstained = diagnostics.get("grounding_status") == "abstained"

    if expected_behavior == "answer" and is_general_advice:
        # General study guidance intentionally bypasses ASTU retrieval. It is
        # correct only when it is answered without fabricated ASTU citations.
        behavior_correct = not actual_abstained and not sources and evidence_match
        citation_correct = not sources
    elif expected_behavior == "answer":
        behavior_correct = not actual_abstained and bool(sources) and source_match and evidence_match
        citation_correct = bool(sources) and source_match
    elif expected_behavior == "abstain":
        behavior_correct = actual_abstained and not sources
        citation_correct = not sources
    else:
        behavior_correct = diagnostics.get("grounding_status") in {
            "grounded",
            "general_advice",
            "abstained",
        }
        citation_correct = not expected_sources or source_match

    failure_reasons: List[str] = []
    if not behavior_correct:
        if expected_behavior == "answer" and not is_general_advice and not diagnostics.get("retrieved_count"):
            failure_reasons.append("retrieval miss")
        if (expected_behavior == "answer" and actual_abstained) or (
            expected_behavior == "abstain" and not actual_abstained
        ):
            failure_reasons.append("wrong abstention")
        if expected_behavior == "answer" and (not citation_correct or not evidence_match):
            failure_reasons.append("bad citation")
        if not failure_reasons:
            failure_reasons.append("scoring bug")
    elif expected_behavior == "answer" and not citation_correct:
        failure_reasons.append("bad citation")

    return {
        "id": item["id"],
        "behavior_correct": behavior_correct,
        "citation_correct": citation_correct,
        "abstained": actual_abstained,
        "latency_ms": None,
        "model_calls": 0,
        "retrieved_count": diagnostics.get("retrieved_count", 0),
        "grounding_status": diagnostics.get("grounding_status"),
        "failure_reasons": failure_reasons,
    }


def evaluate_real(use_graph: bool = False, limit: int = 6, delay_seconds: float = 1.5) -> Dict[str, Any]:
    """Run a small real-model evaluation, failing closed on API/quota errors."""
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    dataset_path = DATA_DIR / "evaluation_dataset.json"
    dataset = _select_questions(json.loads(dataset_path.read_text(encoding="utf-8")), limit)
    base_result: Dict[str, Any] = {
        "status": "failed",
        "pipeline": "graph" if use_graph else "legacy",
        "model_type": f"real Gemini model, {len(dataset)} questions",
        "questions_requested": len(dataset),
        "delay_seconds_between_model_calls": delay_seconds,
        "fallback_models": GEMINI_FALLBACK_MODEL,
        "retries_per_model": 0,
        "results": [],
    }
    if not api_key:
        base_result["error"] = "GEMINI_API_KEY is missing or empty; real evaluation was not run."
        return base_result

    import app.services.rag as rag_module

    counter = {"model_calls": 0}
    service = RAGService(
        api_key=api_key,
        model=GEMINI_MODEL,
        fallback_model=GEMINI_FALLBACK_MODEL,
        # Keep the fallback model chain enabled while avoiding repeated quota
        # retries during this intentionally small evaluation run.
        max_retries=0,
    )
    service._client = CountingClient(genai.Client(api_key=api_key), counter, delay_seconds)
    original_embedding_client = embedding_service._client
    embedding_service._client = CountingClient(genai.Client(api_key=api_key), counter, delay_seconds)
    graph_module = None
    original_graph_service = None
    graph = None
    if use_graph:
        import app.services.graph as graph_module

        original_graph_service = graph_module.rag_service
        graph_module.rag_service = service
        from app.services.graph import GraphPipeline

        graph = GraphPipeline(service)

    results: List[Dict[str, Any]] = []
    failed_question: Dict[str, Any] | None = None
    try:
        for item in dataset:
            started = time.perf_counter()
            calls_before = counter["model_calls"]
            try:
                if graph is None:
                    answer, sources, diagnostics = service.answer_question_with_diagnostics(item["query"])
                else:
                    state = graph.invoke(item["query"], session_history=[])
                    answer = state.get("final_answer", "")
                    sources = state.get("sources", [])
                    diagnostics = state.get("diagnostics", {})
                scored = _score_result(item, answer, sources, diagnostics)
                scored["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
                scored["model_calls"] = counter["model_calls"] - calls_before
                results.append(scored)
            except Exception as error:
                failed_question = {
                    "id": item["id"],
                    "error": _safe_error(error, api_key),
                    "model_calls_before_failure": counter["model_calls"] - calls_before,
                }
                break
    finally:
        embedding_service._client = original_embedding_client
        if graph_module is not None:
            graph_module.rag_service = original_graph_service

    if failed_question is not None:
        base_result["error"] = failed_question["error"]
        base_result["failed_question"] = failed_question
        base_result["questions_completed"] = len(results)
        base_result["results"] = results
        base_result["quota_or_rate_limit"] = any(
            marker in failed_question["error"].lower()
            for marker in ("quota", "resource_exhausted", "rate limit", "429")
        )
        return base_result

    count = len(results)
    base_result.update(
        {
            "status": "completed",
            "questions_completed": count,
            "accuracy": round(sum(result["behavior_correct"] for result in results) / count, 4),
            "citation_correctness": round(sum(result["citation_correct"] for result in results) / count, 4),
            "abstention_rate": round(sum(result["abstained"] for result in results) / count, 4),
            "average_latency_ms": round(sum(result["latency_ms"] for result in results) / count, 3),
            "model_calls_per_question": round(sum(result["model_calls"] for result in results) / count, 3),
            "results": results,
        }
    )
    return base_result


def evaluate(use_graph: bool = False) -> Dict[str, Any]:
    dataset_path = DATA_DIR / "evaluation_dataset.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    service = RAGService(api_key="mock-key", max_retries=0)
    service._client = MockGeminiClient()

    import app.services.rag as rag_module

    lexical_store = LexicalEvaluationStore(CHROMA_PERSIST_DIR)
    original_store = rag_module.vector_store
    original_embedding = rag_module.embedding_service
    rag_module.vector_store = lexical_store
    rag_module.embedding_service = type("MockEmbedding", (), {"embed_query": lambda self, _: [0.0]})()
    graph = None
    if use_graph:
        from app.services.graph import GraphPipeline

        graph = GraphPipeline(service)

    results: List[Dict[str, Any]] = []
    try:
        for item in dataset:
            started = time.perf_counter()
            if graph is None:
                answer, sources, diagnostics = service.answer_question_with_diagnostics(item["query"])
            else:
                result = graph.invoke(item["query"], session_history=[])
                answer = result.get("final_answer", "")
                sources = result.get("sources", [])
                diagnostics = result.get("diagnostics", {})
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            source_text = " ".join(source.title.lower() for source in sources)
            answer_text = answer.lower()
            expected_behavior = item["expected_behavior"]
            expected_sources = [source.lower() for source in item["expected_sources"]]
            expected_terms = [term.lower() for term in item["required_evidence_terms"]]
            source_match = not expected_sources or any(source in source_text for source in expected_sources)
            evidence_match = not expected_terms or all(term in answer_text for term in expected_terms)
            if expected_behavior == "answer":
                behavior_correct = bool(sources) and source_match and evidence_match
            elif expected_behavior == "abstain":
                behavior_correct = not sources and diagnostics["grounding_status"] == "abstained"
            else:
                behavior_correct = diagnostics["grounding_status"] in {"grounded", "general_advice", "abstained"}
            results.append(
                {
                    "id": item["id"],
                    "behavior_correct": behavior_correct,
                    "citation_correct": bool(sources) and source_match if expected_behavior == "answer" else not sources,
                    "abstained": diagnostics["grounding_status"] == "abstained",
                    "latency_ms": latency_ms,
                    "grounding_status": diagnostics["grounding_status"],
                }
            )
    finally:
        rag_module.vector_store = original_store
        rag_module.embedding_service = original_embedding

    count = len(results)
    return {
        "dataset": str(dataset_path),
        "pipeline": "graph" if use_graph else "legacy",
        "model": "deterministic mock Gemini; no external API calls",
        "retrieval": "lexical mock over persisted Chroma chunks",
        "cases": count,
        "behavior_accuracy": round(sum(item["behavior_correct"] for item in results) / count, 4),
        "citation_correctness": round(sum(item["citation_correct"] for item in results) / count, 4),
        "abstention_rate": round(sum(item["abstained"] for item in results) / count, 4),
        "mean_latency_ms": round(sum(item["latency_ms"] for item in results) / count, 3),
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--delay-seconds", type=float, default=1.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.real:
        result = evaluate_real(
            use_graph=args.graph,
            limit=args.limit,
            delay_seconds=max(0.0, args.delay_seconds),
        )
    else:
        result = evaluate(use_graph=args.graph)
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.real and result.get("status") != "completed":
        raise SystemExit(2)
