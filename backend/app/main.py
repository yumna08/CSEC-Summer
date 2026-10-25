import logging
import time
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.knowledge import router as knowledge_router
from app.core.config import (
    CHAT_RATE_LIMIT,
    CHAT_HISTORY_TURNS,
    CORS_ORIGINS,
    DATABASE_URL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    USE_GRAPH_PIPELINE,
)
from app.core.rate_limit import limiter
from app.core.structured_logging import configure_logging, request_id_context
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.research import ResearchRequest, ResearchResponse
from app.services.rag import rag_service
from app.services.memory import chat_memory
from app.services.graph import graph_pipeline
from app.services.vector_store import vector_store
from app.services.research import research_agent

logger = logging.getLogger(__name__)
configure_logging()

app = FastAPI(
    title="ASTU CampusGuide AI API",
    description="Backend API for the ASTU CampusGuide AI project with document ingestion and RAG.",
    version="0.3.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "").strip()
    if supplied and len(supplied) <= 128 and all(ord(char) >= 32 for char in supplied):
        return supplied
    return str(uuid4())


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = _request_id(request)
    token = request_id_context.set(request_id)
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "latency_ms": latency_ms,
            },
        )
        request_id_context.reset(token)
        raise

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    request_id_context.reset(token)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)

# Mount document management & ingestion endpoints
app.include_router(knowledge_router)


@app.get("/")
def root():
    return {
        "name": "ASTU CampusGuide AI",
        "status": "running",
        "version": "0.3.0",
    }


@app.get("/api/health")
def health(detailed: bool = False):
    """
    Health and readiness check.
    By default returns simple status. When detailed=True, reports component statuses
    for database, vector store, and AI provider configuration safely without leaking credentials.
    """
    if not detailed:
        return {"status": "healthy", "service": "campusguide-api"}

    details = {
        "status": "healthy",
        "service": "campusguide-api",
        "version": "0.3.0",
        "components": {},
    }

    # Vector store check
    try:
        count = vector_store.collection.count()
        details["components"]["vector_store"] = {
            "status": "ready",
            "indexed_chunks": count,
        }
    except Exception as e:
        logger.warning("Vector store health check failed: %s", str(e))
        details["components"]["vector_store"] = {
            "status": "unavailable",
            "error": "Vector store connection error",
        }
        details["status"] = "degraded"

    # Database check
    if not DATABASE_URL:
        details["components"]["database"] = {
            "status": "not_configured",
        }
    else:
        try:
            from sqlalchemy import text
            from app.db.database import get_engine
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            details["components"]["database"] = {
                "status": "connected",
            }
        except Exception as e:
            logger.warning("Database health check failed: %s", str(e))
            details["components"]["database"] = {
                "status": "disconnected",
                "error": "Connection failed",
            }
            details["status"] = "degraded"

    # AI configuration check
    details["components"]["ai_service"] = {
        "status": "configured" if bool(GEMINI_API_KEY) else "unconfigured",
        "model": GEMINI_MODEL,
    }

    return details


@app.post("/api/ai/test")
def test_gemini():
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured.",
        )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=(
                "You are testing ASTU CampusGuide AI. "
                "Reply with one short sentence welcoming an ASTU student."
            ),
        )

        if not response.text:
            raise HTTPException(
                status_code=502,
                detail="Gemini returned an empty response.",
            )

        return {
            "message": "Gemini connection successful.",
            "model": GEMINI_MODEL,
            "reply": response.text,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Gemini request failed. Check the backend terminal.",
        ) from None


@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit(CHAT_RATE_LIMIT)
def chat(request: Request, response: Response, chat_request: ChatRequest):
    """
    RAG-grounded chat endpoint:
    1. Embeds query
    2. Retrieves top relevant ASTU document chunks
    3. Prompts Gemini with evidence and strict grounding rules
    4. Returns grounded answer and contributing source citations
    """
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured.",
        )

    message = chat_request.message.strip()
    if not message:
        raise HTTPException(
            status_code=422,
            detail="Please enter a question.",
        )

    try:
        chat_memory.purge_expired()
        session_id = chat_memory.get_or_create_session(chat_request.session_id)
        history = chat_memory.get_recent_history(session_id, turns=CHAT_HISTORY_TURNS)
        chat_memory.append_message(session_id, "user", message)

        if USE_GRAPH_PIPELINE:
            graph_result = graph_pipeline.invoke(message, session_history=history)
            reply = graph_result.get("final_answer", "")
            sources = graph_result.get("sources", [])
        else:
            retrieval_question = rag_service.rewrite_follow_up(message, history)
            reply, sources = rag_service.answer_question(
                message,
                retrieval_question=retrieval_question,
                history=history,
            )
        cited_source_ids = [
            value
            for source in sources
            for value in (
                source.url,
                source.document_name,
                source.title,
            )
            if value
        ]
        chat_memory.append_message(
            session_id,
            "assistant",
            reply,
            cited_source_ids=cited_source_ids,
        )
        return ChatResponse(reply=reply, sources=sources, session_id=session_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error in /api/chat: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail="An internal server error occurred while processing your request.",
        ) from None


@app.delete("/api/chat/sessions/{session_id}")
def delete_chat_session(session_id: str):
    """Delete all stored turns for one opaque chat session id."""
    deleted = chat_memory.delete_session(session_id)
    return {"session_id": session_id, "deleted": deleted}


@app.post("/api/research", response_model=ResearchResponse)
@limiter.limit(CHAT_RATE_LIMIT)
def research(request: Request, response: Response, research_request: ResearchRequest):
    """Build a bounded, cited report from indexed ASTU evidence."""
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured.",
        )
    try:
        return research_agent.invoke(research_request.topic)
    except HTTPException:
        raise
    except Exception:
        # Deliberately omit the topic from logs and exception details.
        logger.exception("Research request failed")
        raise HTTPException(
            status_code=500,
            detail="An internal server error occurred while preparing the research report.",
        ) from None
