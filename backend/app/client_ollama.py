"""Ollama embedding calls. Provider selection belongs to the calling service."""

import math

import httpx

from app.core.config import (
    OLLAMA_BASE_URL,
    OLLAMA_EMBEDDING_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
)
from app.services.telemetry import safe_update, trace_step


def create_embeddings(texts: list[str]) -> list[list[float]]:
    """Return one finite, consistently sized vector per input, without truncation.

    Raise HTTP errors for server failures and ValueError for malformed vectors.
    Database-specific dimension checks belong to the embedding service.
    """
    if not texts:
        return []

    with trace_step(
        "create_embeddings",
        kind="embedding",
        model=OLLAMA_EMBEDDING_MODEL,
        metadata={"text_count": len(texts)},
    ) as observation:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={
                "model": OLLAMA_EMBEDDING_MODEL,
                "input": texts,
                "truncate": False,
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise ValueError("Ollama embedding count does not match input count.")

        dimensions = None
        for vector in embeddings:
            if not isinstance(vector, list) or not vector:
                raise ValueError("Ollama returned an empty or invalid embedding.")
            if dimensions is None:
                dimensions = len(vector)
            if len(vector) != dimensions or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            ):
                raise ValueError("Ollama returned inconsistent or non-finite embeddings.")

        tokens = payload.get("prompt_eval_count")
        if isinstance(tokens, int) and tokens >= 0:
            safe_update(observation, usage_details={"input": tokens})

        return embeddings
