from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.chat import SourceCitation
from app.services.graph import GraphPipeline, get_academic_calendar, search_astu_documents
from app.services.memory import chat_memory
from app.services.rag import RAGService


@pytest.fixture
def client():
    chat_memory.reset_for_testing()
    return TestClient(app)


def chunk(chunk_id="chunk-1"):
    return {
        "id": chunk_id,
        "text": "Registration is supported by the ASTU Registrar and Alumni Executive.",
        "metadata": {
            "source_title": "ASTU Registrar and Alumni Executive",
            "source_url": "https://www.astu.edu.et/registrar",
            "verification_status": "candidate",
        },
        "distance": 0.2,
        "relevance_score": 0.8,
        "token_overlap": 2,
    }


def pipeline_with_model(function_calls=None):
    service = RAGService(api_key="mock-key", max_retries=0)
    service._client = MagicMock()
    service._client.models.generate_content.return_value = SimpleNamespace(
        function_calls=function_calls or []
    )
    service.rewrite_follow_up = MagicMock(side_effect=lambda message, history: message)
    service.answer_question_with_diagnostics = MagicMock(
        return_value=(
            "Registration is supported by the registrar.",
            [SourceCitation(title="ASTU Registrar and Alumni Executive")],
            {"grounding_status": "grounded"},
        )
    )
    return service


def test_each_graph_node_can_run_individually():
    service = pipeline_with_model()
    pipeline = GraphPipeline(service)
    state = {"message": "What is the ASTU registration process?", "session_history": []}

    classified = pipeline.classify_node(state)
    assert classified["classification"] == "factual"
    rewritten = pipeline.rewrite_node({**state, **classified})
    assert rewritten["rewritten_query"] == state["message"]

    with patch.object(pipeline, "_normal_retrieval", return_value=[chunk()]):
        retrieved = pipeline.retrieve_node({**state, **classified, **rewritten, "classification": "general"})
    assert retrieved["retrieved_chunks"] == [chunk()]

    generated = pipeline.generate_node({
        **state,
        **classified,
        **rewritten,
        **retrieved,
        "classification": "general",
    })
    verified = pipeline.verify_citations_node({
        **state,
        **generated,
        "classification": "general",
    })
    final = pipeline.answer_or_abstain_node({
        **state,
        **generated,
        **verified,
        "classification": "general",
    })
    assert generated["draft_answer"]
    assert verified["citation_check"]["passed"] is True
    assert final["final_answer"] == generated["draft_answer"]
    assert [entry["node"] for entry in final["trace"]] == [
        "classify",
        "rewrite",
        "retrieve",
        "generate",
        "verify_citations",
        "answer_or_abstain",
    ]


def test_greeting_skips_retrieval_tools_and_model(client):
    service = pipeline_with_model()
    pipeline = GraphPipeline(service)
    with patch.object(pipeline, "_normal_retrieval") as retrieve, \
         patch("app.services.graph.search_astu_documents") as search:
        result = pipeline.invoke("Hello")

    retrieve.assert_not_called()
    search.assert_not_called()
    service._client.models.generate_content.assert_not_called()
    assert result["final_answer"].startswith("Hello!")


def test_factual_question_calls_search_tool_once():
    call = SimpleNamespace(
        name="search_astu_documents",
        args={"query": "ASTU registration process", "max_results": 4},
    )
    service = pipeline_with_model([call])
    pipeline = GraphPipeline(service)
    with patch("app.services.graph.search_astu_documents", return_value=[chunk()]) as search:
        result = pipeline.invoke("What is the ASTU registration process?")

    search.assert_called_once_with(query="ASTU registration process", max_results=4)
    assert result["tool_calls"] == 1
    assert result["trace"][2]["mode"] == "tool"
    assert result["trace"][2]["tool_call_names"] == ["search_astu_documents"]
    config = service._client.models.generate_content.call_args.kwargs["config"]
    assert len(config.tools[0].function_declarations) == 2


def test_malformed_tool_call_falls_back_to_normal_retrieval():
    call = SimpleNamespace(name="unknown_tool", args={})
    service = pipeline_with_model([call])
    pipeline = GraphPipeline(service)
    with patch.object(pipeline, "_normal_retrieval", return_value=[chunk()]) as normal, \
         patch("app.services.graph.search_astu_documents") as search:
        result = pipeline.invoke("What is the ASTU registration process?")

    normal.assert_called_once()
    search.assert_not_called()
    assert result["tool_calls"] == 0


def test_tool_call_cap_is_two():
    calls = [
        SimpleNamespace(
            name="search_astu_documents",
            args={"query": f"registration {index}", "max_results": 1},
        )
        for index in range(5)
    ]
    service = pipeline_with_model(calls)
    pipeline = GraphPipeline(service)
    with patch("app.services.graph.search_astu_documents", return_value=[chunk()]) as search:
        result = pipeline.invoke("What is the ASTU registration process?")

    assert search.call_count == 2
    assert result["tool_calls"] == 2


def test_unverified_citation_routes_to_abstention():
    service = pipeline_with_model()
    service.answer_question_with_diagnostics.return_value = (
        "Unsupported answer",
        [SourceCitation(title="Unverified source")],
        {"grounding_status": "abstained"},
    )
    pipeline = GraphPipeline(service)
    result = pipeline.invoke("What is the ASTU registration process?")

    assert result["final_answer"].startswith("I could not verify")
    assert result["sources"] == []


def test_tool_functions_validate_and_use_indexed_retrieval():
    with patch("app.services.graph.rag_service.retrieve_chunks", return_value=([chunk()], False)) as retrieve:
        assert search_astu_documents("registration", 2)[0]["id"] == "chunk-1"
        assert get_academic_calendar("2026/2027") == []
    retrieve.assert_any_call("registration", top_k=2)
    retrieve.assert_any_call("academic calendar 2026/2027", top_k=8)

    with pytest.raises(ValueError):
        search_astu_documents("", 2)
    with pytest.raises(ValueError):
        search_astu_documents("registration", 0)


def test_pipeline_flag_off_and_on_keep_response_shape(client):
    legacy_sources = [SourceCitation(title="Legacy source")]
    with patch("app.main.GEMINI_API_KEY", "test-key"), \
         patch("app.main.USE_GRAPH_PIPELINE", False), \
         patch("app.main.rag_service.answer_question", return_value=("legacy", legacy_sources)):
        legacy = client.post("/api/chat", json={"message": "What is the ASTU registration process?"})

    with patch("app.main.GEMINI_API_KEY", "test-key"), \
         patch("app.main.USE_GRAPH_PIPELINE", True), \
         patch("app.main.graph_pipeline.invoke", return_value={"final_answer": "graph", "sources": []}):
        graph = client.post("/api/chat", json={"message": "What is the ASTU registration process?"})

    assert legacy.status_code == graph.status_code == 200
    assert set((legacy.json())).issuperset({"reply", "sources", "session_id"})
    assert set((graph.json())).issuperset({"reply", "sources", "session_id"})
    assert legacy.json()["reply"] == "legacy"
    assert graph.json()["reply"] == "graph"
