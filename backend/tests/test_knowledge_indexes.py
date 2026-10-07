from sqlalchemy import select

from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_embedding import KnowledgeEmbeddingOpenAI, KnowledgeEmbeddingOllama
from app.services import knowledge_indexing_service as indexing
from app.services import knowledge_retrieval_service as retrieval


def select_provider(monkeypatch, storage, model):
    monkeypatch.setattr(indexing, "get_embedding_index", lambda: (storage, model))
    monkeypatch.setattr(indexing, "create_embeddings", lambda texts, **kwargs: [
        [0.1] * kwargs["expected_dimensions"] for _ in texts
    ])


def add_document(db):
    document = KnowledgeBase(
        title="Club run", source="test.md",
        content="The weekly club run meets at the park every Tuesday evening.",
    )
    db.add(document)
    db.flush()
    return document


def test_local_index_preserves_openai_vectors_and_chunk_ids(db_session, monkeypatch):
    document = add_document(db_session)
    select_provider(monkeypatch, KnowledgeEmbeddingOpenAI, "text-embedding-3-small")
    indexing.index_document(db_session, document)
    original = db_session.scalars(select(KnowledgeChunk)).one().id
    select_provider(monkeypatch, KnowledgeEmbeddingOllama, "qwen3-embedding:0.6b")
    indexing.index_document(db_session, document)
    indexing.index_document(db_session, document)
    assert db_session.scalars(select(KnowledgeChunk)).one().id == original
    assert db_session.scalars(select(KnowledgeEmbeddingOpenAI)).one().chunk_id == original
    assert db_session.scalars(select(KnowledgeEmbeddingOllama)).one().chunk_id == original


def test_changed_text_invalidates_other_provider_vectors(db_session, monkeypatch):
    document = add_document(db_session)
    select_provider(monkeypatch, KnowledgeEmbeddingOpenAI, "text-embedding-3-small")
    indexing.index_document(db_session, document)
    original = db_session.scalars(select(KnowledgeChunk)).one().id
    document.content = "The weekly club run now meets at the stadium on Thursday morning."
    select_provider(monkeypatch, KnowledgeEmbeddingOllama, "qwen3-embedding:0.6b")
    indexing.index_document(db_session, document)
    assert db_session.scalars(select(KnowledgeChunk)).one().id != original
    assert db_session.scalars(select(KnowledgeEmbeddingOpenAI)).all() == []
    assert len(db_session.scalars(select(KnowledgeEmbeddingOllama)).all()) == 1


def test_title_change_invalidates_embeddings(db_session, monkeypatch):
    document = add_document(db_session)
    select_provider(monkeypatch, KnowledgeEmbeddingOpenAI, "text-embedding-3-small")
    indexing.index_document(db_session, document)
    document.title = "Updated club run"
    select_provider(monkeypatch, KnowledgeEmbeddingOllama, "qwen3-embedding:0.6b")
    indexing.index_document(db_session, document)
    assert db_session.scalars(select(KnowledgeEmbeddingOpenAI)).all() == []
    assert db_session.scalars(select(KnowledgeChunk)).one().embedding_title == document.title


def test_retrieval_filters_provider_and_exact_model(db_session, monkeypatch):
    document = add_document(db_session)
    select_provider(monkeypatch, KnowledgeEmbeddingOpenAI, "text-embedding-3-small")
    indexing.index_document(db_session, document)
    select_provider(monkeypatch, KnowledgeEmbeddingOllama, "qwen3-embedding:0.6b")
    indexing.index_document(db_session, document)
    monkeypatch.setattr(retrieval, "create_query_embedding", lambda query: [0.1] * 1024)
    monkeypatch.setattr(retrieval, "get_embedding_index", lambda: (
        KnowledgeEmbeddingOllama, "qwen3-embedding:0.6b",
    ))
    assert len(retrieval.retrieve_knowledge(db_session, "club run")) == 1
    monkeypatch.setattr(retrieval, "get_embedding_index", lambda: (
        KnowledgeEmbeddingOllama, "another-model",
    ))
    assert retrieval.retrieve_knowledge(db_session, "club run") == []
