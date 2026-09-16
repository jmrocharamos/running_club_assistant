from app.services.telemetry import traced
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.client_openai import create_embeddings
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_chunk import KnowledgeChunk


DEFAULT_RESULTS_LIMIT = 5
MAX_COSINE_DISTANCE = 0.65

@traced("retrieve_knowledge", kind="retriever")
def retrieve_knowledge(
        db: Session,
        query: str,
        limit: int = DEFAULT_RESULTS_LIMIT,
) -> list[dict[str, Any]]:
    """Embed a query and return nearby knowledge chunks with source metadata.

    Blank queries return no results without calling the embedding API.
    """
    clean_query = query.strip()

    if not clean_query:
        return []

    if limit < 1:
        raise ValueError("Retrieval limit must be at least 1")

    query_embedding = create_embeddings([clean_query])[0]

    distance = KnowledgeChunk.embedding.cosine_distance(
        query_embedding,
    ).label("distance")

    rows = db.execute(
        select(
            KnowledgeChunk,
            KnowledgeBase,
            distance,
        )
        .join(
            KnowledgeBase,
            KnowledgeChunk.knowledge_base_id == KnowledgeBase.id,
        )
        .where(distance <= MAX_COSINE_DISTANCE)
        .order_by(distance)
        .limit(limit)
    ).all()

    return [
        {
            "chunk_id": str(chunk.id),
            "document_id": str(document.id),
            "title": document.title,
            "source": document.source,
            "content_status": (
                document.metadata_ or {}
            ).get("content_status"),
            "document_type": document.document_type,
            "content": chunk.content,
            "metadata": chunk.metadata_ or {},
            "distance": float(chunk_distance),
        }
        for chunk, document, chunk_distance in rows
    ]