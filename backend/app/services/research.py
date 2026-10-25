"""Bounded, evidence-first research workflow built on the existing RAG retriever."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.core.config import RAG_TOP_K, RESEARCH_MAX_MODEL_CALLS
from app.schemas.research import ResearchCitation, ResearchResponse, ResearchStep
from app.services.rag import SYSTEM_INSTRUCTION, RAGService, rag_service
from app.services.rag import GenerationCallLimitReached
from app.core.tracing import observe_node


MAX_SUBQUESTIONS = 4
_GAP_PREFIX = "The indexed knowledge base does not cover: "


class ResearchState(TypedDict, total=False):
    topic: str
    subquestions: List[str]
    retrieved_steps: List[Dict[str, Any]]
    draft: Dict[str, Any]
    claims: List[str]
    unsupported_or_missing_items: List[str]
    final_report: Dict[str, Any]
    model_calls: int


def _response_text(response: Any) -> str:
    return str(getattr(response, "text", "") or "").strip()


def _json_payload(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None


def _clean_strings(values: Any, limit: int = 8) -> List[str]:
    if not isinstance(values, list):
        return []
    clean: List[str] = []
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip() not in clean:
            clean.append(value.strip()[:1000])
        if len(clean) == limit:
            break
    return clean


class ResearchAgent:
    def __init__(
        self,
        service: RAGService = rag_service,
        max_model_calls: int = RESEARCH_MAX_MODEL_CALLS,
    ):
        self.service = service
        self.max_model_calls = max(1, int(max_model_calls))
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(ResearchState)
        workflow.add_node("plan", self.plan_node)
        workflow.add_node("retrieve", self.retrieve_node)
        workflow.add_node("synthesize", self.synthesize_node)
        workflow.add_node("critic", self.critic_node)
        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "retrieve")
        workflow.add_edge("retrieve", "synthesize")
        workflow.add_edge("synthesize", "critic")
        workflow.add_edge("critic", END)
        return workflow.compile()

    def _can_call(self, state: ResearchState) -> bool:
        return state.get("model_calls", 0) < self.max_model_calls

    def _model_call(self, state: ResearchState, prompt: str) -> tuple[Optional[Any], int]:
        starting_calls = state.get("model_calls", 0)
        call_count = [starting_calls]
        if call_count[0] >= self.max_model_calls:
            return None, call_count[0]

        def guard(_: str) -> None:
            if call_count[0] >= self.max_model_calls:
                raise GenerationCallLimitReached
            call_count[0] += 1

        try:
            response = self.service._generate_with_retry_and_fallback(
                prompt,
                generation_config=None,
                model_call_guard=guard,
            )
        except GenerationCallLimitReached:
            return None, call_count[0]
        # Mocked model clients used by tests may not invoke the guard callback;
        # still count the logical generation operation in that case.
        if call_count[0] == starting_calls:
            call_count[0] += 1
        return response, call_count[0]

    @observe_node("research.plan")
    def plan_node(self, state: ResearchState) -> Dict[str, Any]:
        topic = state["topic"].strip()
        if not self._can_call(state):
            return {
                "subquestions": [topic],
                "unsupported_or_missing_items": [_GAP_PREFIX + "the research plan could not be generated."],
            }

        prompt = (
            "Create a research plan for an ASTU student question. Split the topic into at most four "
            "focused sub-questions. Return only JSON in the form {\"subquestions\":[\"...\"]}. "
            "Do not answer the questions and do not invent subtopics unrelated to the topic.\n"
            f"Topic: {topic}"
        )
        missing: List[str] = []
        try:
            response, calls = self._model_call(state, prompt)
            payload = _json_payload(_response_text(response)) if response is not None else None
            values = payload.get("subquestions") if isinstance(payload, dict) else payload
            subquestions = _clean_strings(values, MAX_SUBQUESTIONS)
        except Exception:
            calls = state.get("model_calls", 0) + 1
            subquestions = []
            missing.append(_GAP_PREFIX + "the research plan could not be generated.")

        if not subquestions:
            subquestions = [topic]
        return {
            "subquestions": subquestions[:MAX_SUBQUESTIONS],
            "model_calls": calls,
            "unsupported_or_missing_items": missing,
        }

    @observe_node("research.retrieve")
    def retrieve_node(self, state: ResearchState) -> Dict[str, Any]:
        steps: List[Dict[str, Any]] = []
        missing = list(state.get("unsupported_or_missing_items", []))
        calls = state.get("model_calls", 0)
        for subquestion in state.get("subquestions", [])[:MAX_SUBQUESTIONS]:
            if calls >= self.max_model_calls:
                missing.append(_GAP_PREFIX + f"{subquestion} (research call cap reached).")
                break
            # One retrieval embedding is counted as one model call for the
            # request budget; vector search itself is local and read-only.
            calls += 1
            chunks, _ = self.service.retrieve_chunks(subquestion, top_k=RAG_TOP_K)
            source_titles = [
                str(chunk.get("metadata", {}).get("source_title", ""))
                for chunk in chunks
                if chunk.get("metadata", {}).get("source_title")
            ]
            steps.append({"question": subquestion, "chunks": chunks, "source_titles": source_titles})
            if not chunks:
                missing.append(_GAP_PREFIX + subquestion)
        return {
            "retrieved_steps": steps,
            "model_calls": calls,
            "unsupported_or_missing_items": missing,
        }

    @staticmethod
    def _citations(retrieved_steps: List[Dict[str, Any]]) -> List[ResearchCitation]:
        citations: List[ResearchCitation] = []
        seen = set()
        for step in retrieved_steps:
            for chunk in step.get("chunks", []):
                metadata = chunk.get("metadata", {})
                title = str(metadata.get("source_title", "")).strip()
                if not title:
                    continue
                key = (title, metadata.get("source_url"), metadata.get("academic_year"), step["question"])
                if key in seen:
                    continue
                seen.add(key)
                citations.append(
                    ResearchCitation(
                        title=title,
                        url=metadata.get("source_url") or None,
                        academic_year=metadata.get("academic_year") or None,
                        subquestion=step["question"],
                    )
                )
        return citations

    def _safe_draft(self, state: ResearchState) -> Dict[str, Any]:
        steps = state.get("retrieved_steps", [])
        return {
            "summary": "The research report is limited to evidence found in the indexed ASTU knowledge base.",
            "steps": [
                {
                    "question": step["question"],
                    "finding": (
                        "Indexed evidence was retrieved for this sub-question."
                        if step.get("chunks")
                        else "No indexed evidence was retrieved for this sub-question."
                    ),
                }
                for step in steps
            ],
            "required_documents": [],
            "contacts": [],
            "claims": [],
        }

    @observe_node("research.synthesize")
    def synthesize_node(self, state: ResearchState) -> Dict[str, Any]:
        safe_draft = self._safe_draft(state)
        if not self._can_call(state):
            return {"draft": safe_draft, "claims": [], "model_calls": state.get("model_calls", 0)}

        evidence = json.dumps(
            [
                {
                    "question": step["question"],
                    "chunks": [chunk.get("text", "") for chunk in step.get("chunks", [])],
                }
                for step in state.get("retrieved_steps", [])
            ],
            ensure_ascii=False,
        )
        prompt = (
            f"{SYSTEM_INSTRUCTION}\n\n"
            "Synthesize a concise research report using only the supplied indexed evidence. "
            "Return JSON with summary, steps, required_documents, contacts, and claims arrays. "
            "Claims must be directly supported by the evidence; leave arrays empty when unsupported. "
            "Do not include citations in the JSON; the application derives them from retrieved chunks.\n"
            f"Topic: {state['topic']}\nEvidence: {evidence}"
        )
        try:
            response, calls = self._model_call(state, prompt)
            payload = _json_payload(_response_text(response)) if response is not None else None
            draft = payload if isinstance(payload, dict) else safe_draft
        except Exception:
            calls = state.get("model_calls", 0) + 1
            draft = safe_draft
        claims = _clean_strings(draft.get("claims"), limit=20)
        draft = {
            "summary": str(draft.get("summary", safe_draft["summary"]))[:4000],
            "steps": draft.get("steps") if isinstance(draft.get("steps"), list) else safe_draft["steps"],
            "required_documents": _clean_strings(draft.get("required_documents")),
            "contacts": _clean_strings(draft.get("contacts")),
            "claims": claims,
        }
        return {"draft": draft, "claims": claims, "model_calls": calls}

    @observe_node("research.critic")
    def critic_node(self, state: ResearchState) -> Dict[str, Any]:
        claims = _clean_strings(state.get("claims", []), limit=20)
        missing = list(state.get("unsupported_or_missing_items", []))
        supported: List[str] = []
        unsupported: List[str] = []
        calls = state.get("model_calls", 0)

        if claims and self._can_call(state):
            evidence = json.dumps(
                [chunk.get("text", "") for step in state.get("retrieved_steps", []) for chunk in step.get("chunks", [])],
                ensure_ascii=False,
            )
            prompt = (
                "Criticize each research claim against the supplied indexed evidence. Return only JSON "
                "with supported_claims and unsupported_claims arrays. Any claim not directly supported "
                "must be placed in unsupported_claims.\n"
                f"Claims: {json.dumps(claims, ensure_ascii=False)}\nEvidence: {evidence}"
            )
            try:
                response, calls = self._model_call(state, prompt)
                payload = _json_payload(_response_text(response)) if response is not None else None
                if isinstance(payload, dict):
                    supported = _clean_strings(payload.get("supported_claims"), limit=20)
                    unsupported = _clean_strings(payload.get("unsupported_claims"), limit=20)
            except Exception:
                calls = state.get("model_calls", 0) + 1

        if claims and not supported and not unsupported:
            # Fail closed if the critic is unavailable or cannot be parsed.
            unsupported = claims
        unsupported = list(dict.fromkeys(unsupported + [claim for claim in claims if claim not in supported and claim not in unsupported]))
        missing.extend(unsupported)
        draft = dict(state.get("draft", self._safe_draft(state)))
        draft["claims"] = [claim for claim in claims if claim not in unsupported]
        summary = str(draft.get("summary", "")).strip()
        if missing and "does not cover" not in summary.lower():
            summary = f"{summary} {_GAP_PREFIX.rstrip()} some requested details."
        draft["summary"] = summary.strip()

        citations = self._citations(state.get("retrieved_steps", []))
        step_models = []
        for step in state.get("retrieved_steps", []):
            source_titles = list(dict.fromkeys(step.get("source_titles", [])))
            step_models.append(
                ResearchStep(
                    question=step["question"],
                    status="supported" if step.get("chunks") else "missing",
                    evidence_count=len(step.get("chunks", [])),
                    sources=source_titles,
                )
            )
        report = ResearchResponse(
            summary=summary,
            steps=step_models,
            required_documents=_clean_strings(draft.get("required_documents")),
            contacts=_clean_strings(draft.get("contacts")),
            citations=citations,
            unsupported_or_missing_items=list(dict.fromkeys(missing)),
        ).model_dump()
        return {
            "draft": draft,
            "claims": draft["claims"],
            "unsupported_or_missing_items": list(dict.fromkeys(missing)),
            "final_report": report,
            "model_calls": calls,
        }

    def invoke(self, topic: str) -> ResearchResponse:
        state = self.graph.invoke({"topic": topic.strip(), "model_calls": 0})
        return ResearchResponse.model_validate(state["final_report"])


research_agent = ResearchAgent()
