import sys
from pathlib import Path

# Allow importing from backend/app when running this script directly.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BACKEND_DIR))

from sqlalchemy import text

from app.services.embedding_service import get_embedding_index
from app.db.session import SessionLocal
from app.models.knowledge_base import KnowledgeBase
from app.services.knowledge_indexing_service import index_document


def main() -> None:
    db = SessionLocal()

    try:
        # Serialize indexing runs; the transaction releases this lock.
        db.execute(text("SELECT pg_advisory_xact_lock(728193041)"))
        storage, model = get_embedding_index()
        print(f"Indexing {model} into {storage.__tablename__}")

        documents = db.query(KnowledgeBase).all()
        total_chunks = 0

        for document in documents:
            count = index_document(db, document)
            total_chunks += count
            print(f"{document.title}: {count} chunks")


        db.commit()
        print(f"Indexed {len(documents)} documents into {total_chunks} chunks")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
