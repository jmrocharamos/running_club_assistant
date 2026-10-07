# Local embeddings with Ollama

Generation, chat, safety assessments, and memory summaries still use OpenAI.
Only knowledge indexing and retrieval currently select an embedding provider.

From `backend`, apply the migrations before starting the updated backend:

```bash
.venv/bin/alembic upgrade head
```

Build and inspect the local index without changing the app's default provider:

```bash
EMBEDDING_PROVIDER=ollama .venv/bin/python -m scripts.index_knowledge_base
EMBEDDING_PROVIDER=ollama .venv/bin/python -m scripts.check_rag_distances
```

If no documents have been synchronized yet, first run:

```bash
.venv/bin/python -m scripts.sync_knowledge_base
```

To use the populated local index, set these in `backend/.env` and restart the API:

```dotenv
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
OLLAMA_TIMEOUT_SECONDS=120
```

To use OpenAI embeddings again, set `EMBEDDING_PROVIDER=openai` and restart.
The OpenAI embedding model is currently fixed to `text-embedding-3-small`.

## Storage and indexing behavior

- Shared passages live in `knowledge_chunks`.
- OpenAI embeddings live in `knowledge_embeddings_openai` (1536 dimensions).
- Ollama embeddings live in `knowledge_embeddings_ollama` (1024 dimensions).
- Retrieval filters the selected table by exact model name. Changing models
  requires indexing that model before using it. Models with other dimensions
  require additional storage changes.
- Qwen query embeddings include a retrieval instruction; document embeddings
  contain their title, headings, and passage text without that instruction.
- Indexing regenerates the selected model's vectors but preserves unchanged
  chunk IDs and other-provider embeddings. Changed text, headings, or titles
  replace the chunk and remove stale embeddings from all providers. Rebuild
  each provider after document changes before expecting equivalent coverage.
- Indexing runs in a transaction and rolls back on failure. An advisory lock
  serializes indexing script runs.
- The legacy chunk vector column remains nullable during migration; active
  retrieval no longer reads it. OpenAI indexing continues to fill it.

The cosine-distance cutoff remains 0.65 provisionally for both providers.
Use the diagnostic script with relevant and irrelevant questions to calibrate
it before relying on local retrieval quality. An unpopulated selected index
returns no knowledge passages; generation still runs with its other context.

The model server must be reachable from the backend. `localhost` works when
the backend and Ollama run on the same computer.

Downgrading the shared-chunk migration requires OpenAI vectors for every chunk;
rebuild the OpenAI index first if local-only chunks were added.
