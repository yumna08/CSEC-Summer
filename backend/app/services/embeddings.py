import logging
import time
from typing import List
from google import genai
from google.genai.errors import APIError
from app.core.config import GEMINI_API_KEY, GEMINI_EMBEDDING_MODEL
from app.core.tracing import tracer

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key
        self._model = model
        self._client: genai.Client | None = None

    @property
    def api_key(self) -> str:
        return self._api_key if self._api_key is not None else GEMINI_API_KEY

    @property
    def model(self) -> str:
        return self._model if self._model is not None else GEMINI_EMBEDDING_MODEL

    @property
    def client(self) -> genai.Client:
        key = self.api_key
        if not key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        if self._client is None:
            self._client = genai.Client(api_key=key)
        return self._client

    def embed_query(self, query: str) -> List[float]:
        """Generate embedding vector for a single query text."""
        query = query.strip()
        if not query:
            raise ValueError("Query string cannot be empty.")

        try:
            started = time.perf_counter()
            response = self.client.models.embed_content(
                model=self.model,
                contents=query,
            )
            tracer.record_model_call(
                "embedding",
                self.model,
                round((time.perf_counter() - started) * 1000, 3),
                response,
            )
            if not response.embeddings or not response.embeddings[0].values:
                raise ValueError("Embedding model returned an empty embedding.")
            return list(response.embeddings[0].values)
        except APIError as e:
            tracer.record_model_call(
                "embedding",
                self.model,
                round((time.perf_counter() - started) * 1000, 3),
            )
            logger.error("Gemini API error during query embedding: %s", str(e))
            raise RuntimeError(f"Embedding API error: {e.message or 'Request failed'}") from e
        except Exception as e:
            tracer.record_model_call(
                "embedding",
                self.model,
                round((time.perf_counter() - started) * 1000, 3),
            )
            logger.error("Failed to generate query embedding: %s", str(e))
            raise RuntimeError(f"Embedding generation failed: {str(e)}") from e

    def embed_documents(self, texts: List[str], batch_size: int = 40) -> List[List[float]]:
        """Generate embedding vectors for a list of document chunks with batching."""
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = [t if t.strip() else " " for t in texts[i : i + batch_size]]
            try:
                response = self.client.models.embed_content(
                    model=self.model,
                    contents=batch,
                )
                if not response.embeddings:
                    raise ValueError("Embedding model returned empty response for batch.")

                for emb in response.embeddings:
                    all_embeddings.append(list(emb.values))
            except APIError as e:
                logger.error("Gemini API error during batch embedding: %s", str(e))
                raise RuntimeError(f"Batch embedding API error: {e.message or 'Request failed'}") from e
            except Exception as e:
                logger.error("Failed to generate batch embeddings: %s", str(e))
                raise RuntimeError(f"Batch embedding failed: {str(e)}") from e

        return all_embeddings


# Global singleton instance
embedding_service = EmbeddingService()
