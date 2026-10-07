# Local AI with Ollama

Generation and embeddings have independent provider settings. Chat, memory
summaries, training safety, feedback safety, initial plans, and plan revisions
all use `AI_PROVIDER`. Knowledge indexing and retrieval use `EMBEDDING_PROVIDER`.
Both default to OpenAI when no setting is supplied.

## Generation provider

After installing `qwen3.5:9b`, set these in `backend/.env` and restart the API:

```dotenv
AI_PROVIDER=ollama
OLLAMA_MODEL=qwen3.5:9b
OLLAMA_GENERATION_TIMEOUT_SECONDS=300
OLLAMA_CONTEXT_LENGTH=32768
OLLAMA_MAX_OUTPUT_TOKENS=16384
```

Set `AI_PROVIDER=openai` and restart to return generation to the existing
OpenAI models. Switching generation does not change the embedding index.
Fully local mode (`AI_PROVIDER=ollama`, `EMBEDDING_PROVIDER=ollama`) does not
require an OpenAI key. Mixed mode still needs a key for its OpenAI operations.

Ollama uses the native `/api/chat` endpoint with the existing Pydantic JSON
schema, non-streaming responses, temperature zero, and thinking disabled.
Schema validation and the existing application safety/activity/load checks
remain in place. Truncated or malformed output fails the request and is not
silently replaced with an OpenAI call. Feedback decisions are also checked
for consistent plan modes. Telemetry records provider, model, version, and
token counts without prompts, responses, or thinking text.

Initial plans receive an application-generated calendar of available dates.
Weekday labels are derived from dates, and week boundaries, duplicate dates,
and availability are validated before persistence. A failed calendar or activity
check allows one correction attempt; a second failure saves no plan.

The adapter has been tested with `qwen3.5:9b`; other models need evaluation.
The context and output budgets, available memory, and model speed matter for
long plans. Generation still runs inside HTTP requests: slow local inference
can exceed frontend/proxy time limits even when Ollama's backend timeout is
longer. Running session duration is not mechanically verifiable with the
current plan schema, which does not have a running-duration field.

## Embedding provider

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

## Live evaluations

From `backend`, run the opt-in synthetic scenarios:

```bash
.venv/bin/python -m scripts.evaluate_ai --provider ollama --workflows all
.venv/bin/python -m scripts.evaluate_ai --provider openai --workflows chat
```

Both commands default to Ollama retrieval to compare generation with the same
retrieval setup. Use `--embedding-provider openai` to evaluate the other index.
The OpenAI command incurs API usage. Evaluations require a local database,
disable external telemetry, and do not save runner accounts or plans.

Reports under `backend/evaluation/results/` are gitignored. They include
synthetic outputs, latency, and heuristic checks for grounding, missing
knowledge, follow-ups, memory attribution, safety routing, and plan calendars.
Review the actual replies alongside scores. This small suite does not establish
clinical safety or comprehensive coaching quality.
