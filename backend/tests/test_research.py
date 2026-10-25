from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.research import ResearchAgent


def chunk(title="ASTU Registrar"):
    return {
        "id": "chunk-1",
        "text": "The ASTU Registrar handles registration and graduation.",
        "metadata": {
            "source_title": title,
            "source_url": "https://www.astu.edu.et/registrar",
            "academic_year": "2026/2027",
        },
    }


def service_with_model(response_text):
    service = MagicMock()
    service._generate_with_retry_and_fallback.return_value = SimpleNamespace(text=response_text)
    service.retrieve_chunks.return_value = ([chunk()], False)
    return service


def test_plan_limits_subquestions_to_four():
    service = service_with_model('{"subquestions":["one","two","three","four","five"]}')
    agent = ResearchAgent(service, max_model_calls=8)
    result = agent.plan_node({"topic": "ASTU registration", "model_calls": 0})
    assert result["subquestions"] == ["one", "two", "three", "four"]


def test_uncovered_topic_has_explicit_gap():
    service = service_with_model('{"subquestions":["international tuition fees"]}')
    service.retrieve_chunks.return_value = ([], False)
    service._generate_with_retry_and_fallback.side_effect = [
        SimpleNamespace(text='{"subquestions":["international tuition fees"]}'),
        SimpleNamespace(text='{"summary":"No verified fee data.","claims":[]}'),
    ]
    result = ResearchAgent(service).invoke("international tuition fees")
    assert result.unsupported_or_missing_items
    assert any("does not cover" in item for item in result.unsupported_or_missing_items)
    assert "does not cover" in result.summary.lower()


def test_critic_flags_and_removes_unsupported_claim():
    service = service_with_model(
        '{"supported_claims":["Registration is handled by the registrar."],'
        '"unsupported_claims":["The fee is 50,000 birr."]}'
    )
    agent = ResearchAgent(service)
    state = {
        "topic": "registration and fees",
        "retrieved_steps": [{"question": "registration", "chunks": [chunk()], "source_titles": ["ASTU Registrar"]}],
        "draft": {
            "summary": "Registration and fees.",
            "required_documents": [],
            "contacts": [],
            "claims": ["Registration is handled by the registrar.", "The fee is 50,000 birr."],
        },
        "claims": ["Registration is handled by the registrar.", "The fee is 50,000 birr."],
        "model_calls": 0,
    }
    result = agent.critic_node(state)
    assert result["claims"] == ["Registration is handled by the registrar."]
    assert "The fee is 50,000 birr." in result["unsupported_or_missing_items"]


def test_research_call_cap_is_enforced():
    service = service_with_model('{"subquestions":["one","two","three","four"]}')
    agent = ResearchAgent(service, max_model_calls=2)
    result = agent.invoke("many ASTU questions")
    assert result.unsupported_or_missing_items
    assert service._generate_with_retry_and_fallback.call_count <= 1
    assert service.retrieve_chunks.call_count <= 1


def test_research_endpoint_uses_chat_rate_limit():
    client = TestClient(app)
    with patch("app.main.GEMINI_API_KEY", "test-key"), patch(
        "app.main.research_agent.invoke",
        return_value={
            "summary": "ok",
            "steps": [],
            "required_documents": [],
            "contacts": [],
            "citations": [],
            "unsupported_or_missing_items": [],
        },
    ):
        responses = [client.post("/api/research", json={"topic": f"topic {index}"}) for index in range(61)]
    assert all(response.status_code == 200 for response in responses[:60])
    assert responses[-1].status_code == 429
    assert responses[-1].headers.get("Retry-After")
