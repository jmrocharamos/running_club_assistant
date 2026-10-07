from sqlalchemy import select

from app.services.embedding_service import create_query_embedding, get_embedding_index
from app.db.session import SessionLocal, engine
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_chunk import KnowledgeChunk


THRESHOLD = 0.65

TEST_QUERIES = [
    "How can I book the Berlin Braves gym?",
    "What should I eat before a long run?",
    "When are the yoga classes?",
    "What is the capital of France?",
]


def main() -> None:
    engine.echo = False
    storage, model = get_embedding_index()
    print(f"Embedding model: {model}; table: {storage.__tablename__}")

    with SessionLocal() as db:
        for query in TEST_QUERIES:
            query_embedding = create_query_embedding(query)

            distance = storage.embedding.cosine_distance(
                query_embedding,
            ).label("distance")

            rows = db.execute(
                select(
                    KnowledgeBase.title,
                    KnowledgeChunk.chunk_index,
                    distance,
                )
                .select_from(KnowledgeChunk)
                .join(storage, storage.chunk_id == KnowledgeChunk.id)
                .join(
                    KnowledgeBase,
                    KnowledgeChunk.knowledge_base_id
                    == KnowledgeBase.id,
                )
                .where(storage.model == model)
                .order_by(distance)
                .limit(5)
            ).all()

            print(f"\nQUESTION: {query}")

            for title, chunk_index, chunk_distance in rows:
                chunk_distance = float(chunk_distance)

                decision = (
                    "ACCEPT"
                    if chunk_distance <= THRESHOLD
                    else "REJECT"
                )

                print(
                    f"{chunk_distance:.4f} | "
                    f"{decision} | "
                    f"{title} | "
                    f"chunk {chunk_index}"
                )


if __name__ == "__main__":
    main()
