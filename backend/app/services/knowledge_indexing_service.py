"""Synchronize shared chunks and rebuild only the selected embedding index."""

from collections import defaultdict, deque
import json

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.knowledge_chunk import KnowledgeChunk
from app.services.embedding_service import create_embeddings, get_embedding_index
from app.services.knowledge_chunking_service import chunk_document


def _build_embedding_input(document_title: str, chunk: dict) -> str:
    # Sort headings to keep inputs identical before and after JSONB storage.
    header_trail = " > ".join(
        str(chunk["metadata"][key]) for key in sorted(chunk["metadata"])
    )
    context = f"{document_title}\n{header_trail}" if header_trail else document_title
    return f"{context}\n\n{chunk['content']}"


def _chunk_key(content, metadata, title):
    return content, json.dumps(metadata or {}, sort_keys=True), title


def index_document(db: Session, document) -> int:
    """Stage indexing without committing; callers roll back failed rebuilds.

    Unchanged chunks retain IDs and other-provider vectors. Changed/removed
    chunks are replaced, cascading deletion of their now-stale embeddings.
    """
    storage, model = get_embedding_index()
    chunks = chunk_document(document.content)
    existing = db.scalars(select(KnowledgeChunk).where(
        KnowledgeChunk.knowledge_base_id == document.id,
    )).all()
    reusable = defaultdict(deque)
    for chunk in existing:
        reusable[_chunk_key(chunk.content, chunk.metadata_, chunk.embedding_title)].append(chunk)

    vectors = create_embeddings(
        [_build_embedding_input(document.title, chunk) for chunk in chunks],
        expected_dimensions=storage.embedding.type.dim,
    )
    current = []
    for index, chunk in enumerate(chunks):
        key = _chunk_key(chunk["content"], chunk["metadata"], document.title)
        if reusable[key]:
            row = reusable[key].popleft()
            row.chunk_index = index
        else:
            row = KnowledgeChunk(
                knowledge_base_id=document.id, chunk_index=index,
                content=chunk["content"], metadata_=chunk["metadata"],
                embedding_title=document.title,
            )
            db.add(row)
        current.append(row)

    for unused in reusable.values():
        for row in unused:
            db.delete(row)

    if storage.__tablename__ == "knowledge_embeddings_openai":
        for row, vector in zip(current, vectors):
            row.embedding = vector
    db.flush()

    if current:
        statement = insert(storage).values([
            {"chunk_id": row.id, "model": model, "embedding": vector}
            for row, vector in zip(current, vectors)
        ])
        db.execute(statement.on_conflict_do_update(
            index_elements=[storage.chunk_id, storage.model],
            set_={"embedding": statement.excluded.embedding, "updated_at": func.now()},
        ))
    return len(current)
