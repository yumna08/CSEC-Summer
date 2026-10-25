"""Optional, redacted Langfuse tracing for graph, research, and model spans."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Iterator, Optional, TypeVar

from app.core.config import (
    LANGFUSE_ENABLED,
    LANGFUSE_ENVIRONMENT,
    LANGFUSE_HOST,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
)

logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


def _usage_metadata(response: Any) -> Dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    values = {}
    names = {
        "prompt_tokens": ("prompt_token_count", "prompt_tokens"),
        "completion_tokens": ("candidates_token_count", "completion_tokens"),
        "total_tokens": ("total_token_count", "total_tokens"),
    }
    for output_name, candidates in names.items():
        for candidate in candidates:
            value = usage.get(candidate) if isinstance(usage, dict) else getattr(usage, candidate, None)
            if isinstance(value, int):
                values[output_name] = value
                break
    return values


def _safe_result_metadata(result: Any) -> Dict[str, Any]:
    """Extract only structural counts/statuses; never serialize result text."""
    if not isinstance(result, dict):
        return {}
    metadata: Dict[str, Any] = {}
    for key in ("classification", "retrieval_mode", "tool_calls", "model_calls"):
        if isinstance(result.get(key), (str, int, float, bool)):
            metadata[key] = result[key]
    if isinstance(result.get("retrieved_chunks"), list):
        metadata["retrieved_count"] = len(result["retrieved_chunks"])
    if isinstance(result.get("sources"), list):
        metadata["citation_count"] = len(result["sources"])
    if isinstance(result.get("citation_check"), dict):
        metadata["citation_check_passed"] = bool(result["citation_check"].get("passed"))
    if isinstance(result.get("diagnostics"), dict):
        status = result["diagnostics"].get("grounding_status")
        if isinstance(status, str):
            metadata["grounding_status"] = status
    if isinstance(result.get("final_answer"), str):
        metadata["answer_present"] = bool(result["final_answer"])
    return metadata


class Tracer:
    def __init__(self) -> None:
        self.client: Any = None
        self.enabled = False
        if not LANGFUSE_ENABLED:
            return
        if not LANGFUSE_PUBLIC_KEY.strip() or not LANGFUSE_SECRET_KEY.strip():
            logger.warning("Langfuse tracing disabled: credentials are not configured")
            return
        try:
            from langfuse import Langfuse

            self.client = Langfuse(
                public_key=LANGFUSE_PUBLIC_KEY,
                secret_key=LANGFUSE_SECRET_KEY,
                host=LANGFUSE_HOST,
                environment=LANGFUSE_ENVIRONMENT,
                tracing_enabled=True,
            )
            self.enabled = True
        except Exception as error:  # pragma: no cover - depends on optional runtime
            logger.warning("Langfuse tracing unavailable (%s)", error.__class__.__name__)

    @contextmanager
    def node(self, name: str) -> Iterator[Dict[str, Any]]:
        metadata: Dict[str, Any] = {"component": "astu-campusguide", "node": name}
        started = time.perf_counter()
        if not self.enabled or self.client is None:
            yield metadata
            return
        try:
            with self.client.start_as_current_observation(
                name=name,
                as_type="span",
                metadata=metadata.copy(),
            ) as observation:
                yield metadata
                metadata["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
                observation.update(metadata=metadata)
        except Exception as error:  # pragma: no cover - remote exporter failure
            logger.warning("Langfuse span failed (%s)", error.__class__.__name__)

    def record_model_call(
        self,
        operation: str,
        model: str,
        latency_ms: float,
        response: Any = None,
    ) -> None:
        if not self.enabled or self.client is None:
            return
        metadata: Dict[str, Any] = {
            "component": "astu-campusguide",
            "operation": operation,
            "model": model,
            "latency_ms": latency_ms,
        }
        metadata.update(_usage_metadata(response))
        try:
            with self.client.start_as_current_observation(
                name=f"model.{operation}",
                as_type="generation" if operation == "generate" else "embedding",
                metadata=metadata,
                model=model,
                usage_details={key: value for key, value in _usage_metadata(response).items()},
            ):
                pass
        except Exception as error:  # pragma: no cover - remote exporter failure
            logger.warning("Langfuse model span failed (%s)", error.__class__.__name__)

    def flush(self) -> None:
        if self.enabled and self.client is not None:
            try:
                self.client.flush()
            except Exception as error:  # pragma: no cover - remote exporter failure
                logger.warning("Langfuse flush failed (%s)", error.__class__.__name__)


tracer = Tracer()


def observe_node(name: str) -> Callable[[F], F]:
    """Decorate a synchronous graph node with redacted timing/count metadata."""

    def decorator(function: F) -> F:
        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.node(name) as metadata:
                result = function(*args, **kwargs)
                metadata.update(_safe_result_metadata(result))
                return result

        return wrapper  # type: ignore[return-value]

    return decorator
