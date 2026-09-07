from sqlalchemy import select

from app.client_openai import create_embeddings
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

    with SessionLocal() as db:
        for query in TEST_QUERIES:
            query_embedding = create_embeddings([query])[0]

            distance = KnowledgeChunk.embedding.cosine_distance(
                query_embedding,
            ).label("distance")

            rows = db.execute(
                select(
                    KnowledgeBase.title,
                    KnowledgeChunk.chunk_index,
                    distance,
                )
                .join(
                    KnowledgeBase,
                    KnowledgeChunk.knowledge_base_id
                    == KnowledgeBase.id,
                )
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