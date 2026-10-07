# OpenAI/Ollama production rollout

Production continues to use OpenAI for generation and embeddings. Local Ollama
settings live in the ignored development `.env`; they do not configure Render.
Ollama on a developer's computer is not reachable through Render's `localhost`.

## Preparation before merging

1. In the Render API service's environment, set `AI_PROVIDER=openai` and
   `EMBEDDING_PROVIDER=openai`, preserving the existing API key and other secrets.
2. Set its start command, with root directory `backend`, to:

   ```bash
   alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

   On the current single-instance free service this runs migrations before the
   new process starts. A failed migration prevents Uvicorn from starting. Saving
   Render settings can deploy the existing `main` commit; it does not merge the
   feature branch. The existing code only knows the old migration head, so that
   settings deployment does not apply the feature branch's migrations.

   A paid service can instead use `alembic upgrade head` as its pre-deploy command
   and keep a Uvicorn-only start command. See [Render deployment commands](https://render.com/docs/deploys#pre-deploy-command).
3. Verify the settings deployment becomes live and the existing API still
   responds. Confirm the feature branch is tested and up to date with `main`.
4. Merge only after explicit approval. Render watches `main` and auto-deploys
   commits to it, so a merge starts the production rollout.

This sequence applies the feature migrations during the merge deployment,
before starting the updated API. If migrations must be applied before the merge
itself, use the feature branch's Alembic files with a production connection:
running the old `main` files will not discover the new migrations.

## Migration contents

The expected previous head is `72d849ab01f3`. The new head is `d932a4b81e60`.

- `c81a9e7d203b` creates separate OpenAI and Ollama embedding tables. It copies
  existing 1536-dimensional vectors and timestamps into the OpenAI table under
  `text-embedding-3-small`. It preserves the legacy column and all chunk IDs.
- `d932a4b81e60` allows the legacy vector column to be null and fills the new
  `embedding_title` column from each source document. OpenAI vectors remain in
  both the legacy column and the new provider table.

There is no model call or paid re-embedding step in either migration. Do not run
knowledge synchronization or indexing as part of this rollout: preserve the
existing documents and copied vectors until deployment verification finishes.

## Verification after deployment

Check Render's deployment logs for both migrations and a successful Uvicorn
startup. Run this read-only query against the production database:

```sql
SELECT
    (SELECT version_num FROM alembic_version) AS migration,
    (SELECT count(*) FROM knowledge_chunks) AS chunks,
    (SELECT count(*) FROM knowledge_embeddings_openai
     WHERE model = 'text-embedding-3-small') AS openai_vectors,
    (SELECT count(*) FROM knowledge_embeddings_ollama) AS ollama_vectors,
    (SELECT count(*) FROM knowledge_chunks c
     LEFT JOIN knowledge_embeddings_openai e
       ON e.chunk_id = c.id AND e.model = 'text-embedding-3-small'
     WHERE e.chunk_id IS NULL) AS missing_openai_vectors,
    (SELECT count(*) FROM knowledge_chunks c
     JOIN knowledge_embeddings_openai e
       ON e.chunk_id = c.id AND e.model = 'text-embedding-3-small'
     WHERE c.embedding::text IS DISTINCT FROM e.embedding::text
        OR c.created_at IS DISTINCT FROM e.created_at
        OR c.updated_at IS DISTINCT FROM e.updated_at) AS copy_mismatches,
    (SELECT count(*) FROM knowledge_chunks c
     JOIN knowledge_base k ON k.id = c.knowledge_base_id
     WHERE c.embedding_title IS DISTINCT FROM k.title) AS title_mismatches;
```

For the 7 October baseline, expect head `d932a4b81e60`, 155 chunks, 155 OpenAI
vectors, zero Ollama vectors, and zero missing vectors or mismatches. A different
count requires checking whether documents were changed after the baseline.

Then verify API liveness at `/` and use an authorized account in the frontend to
check login, saved plans, a grounded club-knowledge chat answer, plan generation,
and feedback/revision. Those authenticated checks are still required after the
merge; local tests and a liveness response cannot establish production behavior.

## Rollback

Keep the expanded schema when rolling back application code. For this rollout,
the migrations retain legacy OpenAI vectors for the previous retrieval code.
Do not delete provider tables or downgrade production as a routine rollback.

An older commit does not know the new Alembic revision. If redeploying that
commit, first set its start command back to
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`; otherwise its Alembic startup
can fail with an unknown revision. Restore the migration-first command when
deploying code that includes the new migration history. Pause knowledge indexing
during an old-code rollback; it does not maintain the new provider tables.

Downgrading the schema requires an OpenAI legacy vector for every chunk.
Local-only chunks require rebuilding the OpenAI index first. Rehearsed downgrade
behavior is not a reason to remove production embedding data.

## Evidence recorded on 7 October 2026

- Backend suite: 110 tests and 22 subtests passed; one existing Starlette
  deprecation warning.
- A disposable local PostgreSQL database was migrated to the old production
  head, seeded with 155 synthetic chunks, and upgraded using the actual Alembic
  files. All vectors and timestamps were copied exactly, titles were filled,
  the nullable legacy column was verified, and the Ollama table was empty.
- A repeated upgrade, downgrade to the old head, and re-upgrade passed. The
  disposable database was removed; no production data was used in the rehearsal.
- Before the rollout, production was verified at `72d849ab01f3` with 155 chunks,
  155 legacy vectors, correct dimensions, and no orphaned chunks.
- Production provider settings were explicitly set to OpenAI. Startup-command
  confirmation and the post-merge production checks must be recorded separately.
- The provider-settings deployment of the existing `main` commit became live.
  API and frontend liveness requests returned HTTP 200.

The Render database currently reports an expiration date of 14 October 2026.
Address its retention or hosting plan separately before that date; this code
merge does not change the database's expiration.

See [local AI evaluation evidence and limits](LOCAL_AI_EVALUATION.md) for the
model-quality checks completed during implementation.
