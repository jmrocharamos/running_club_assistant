"""Provider selection and validation shared by embedding consumers."""

import math

from app.core.config import EMBEDDING_PROVIDER, OLLAMA_EMBEDDING_MODEL


def get_embedding_index():
    """Return the selected storage model and exact embedding model identity."""
    from app.models.knowledge_embedding import (
        KnowledgeEmbeddingOpenAI, KnowledgeEmbeddingOllama,
    )

    if EMBEDDING_PROVIDER == "openai":
        return KnowledgeEmbeddingOpenAI, "text-embedding-3-small"
    if EMBEDDING_PROVIDER == "ollama":
        return KnowledgeEmbeddingOllama, OLLAMA_EMBEDDING_MODEL
    raise ValueError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")


def create_query_embedding(query: str) -> list[float]:
    """Apply Qwen's retrieval instruction to queries, never to documents."""
    storage, model = get_embedding_index()
    if EMBEDDING_PROVIDER == "ollama" and model.startswith("qwen3-embedding"):
        query = (
            "Instruct: Given a running club question, retrieve relevant passages "
            "that answer the question\nQuery: " + query
        )
    return create_embeddings(
        [query], expected_dimensions=storage.embedding.type.dim,
    )[0]


def create_embeddings(
    texts: list[str],
    *,
    expected_dimensions: int | None = None,
) -> list[list[float]]:
    """Embed with the configured provider; optionally require index dimensions.

    Import clients lazily so local embeddings do not require an OpenAI key.
    Matching dimensions alone does not prove index/model compatibility; each
    embedding model must use its own rebuilt index.
    """
    if EMBEDDING_PROVIDER == "openai":
        from app.client_openai import create_embeddings as embed
    elif EMBEDDING_PROVIDER == "ollama":
        from app.client_ollama import create_embeddings as embed
    else:
        raise ValueError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")

    if not texts:
        return []

    vectors = embed(texts)
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ValueError("Embedding count does not match input count.")

    dimensions = expected_dimensions
    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise ValueError("Embedding provider returned an empty or invalid vector.")
        if dimensions is None:
            dimensions = len(vector)
        if len(vector) != dimensions:
            raise ValueError(
                f"Embedding has {len(vector)} dimensions; expected {dimensions}. "
                "Prepare a matching index before switching embedding providers."
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError("Embedding provider returned non-finite or invalid values.")

    return vectors
