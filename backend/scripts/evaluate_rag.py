"""Run the RAG evaluation dataset with a deterministic mocked model.

The evaluator intentionally uses the repository's persisted Chroma documents
and the existing RAGService. Embedding and generation are mocked so evaluation
is repeatable and never calls Gemini.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Allow ``python scripts/evaluate_rag.py`` when launched from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import CHROMA_PERSIST_DIR, DATA_DIR
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
    args = parser.parse_args()
    print(json.dumps(evaluate(use_graph=args.graph), indent=2))
