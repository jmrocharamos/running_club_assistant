# Production database migration to Neon

Completed on **14 October 2026**. The frontend remains on Vercel and the
FastAPI backend remains on Render; production PostgreSQL now runs on Neon.

## Hosting and connection

- Neon resource: `running-club-assistant-db`, Frankfurt, Free plan.
- PostgreSQL 18; the existing pgvector schema and embeddings were restored.
- Render service: `running-club-assistant-api`.
- `DATABASE_URL` is stored in Render's environment, with the
  `postgresql+psycopg://` driver prefix and TLS enabled.
- The URL is direct/unpooled because the current start command runs
  `alembic upgrade head` and Uvicorn with the same environment. If application
  traffic is moved to Neon's pooler later, give Alembic a separate direct URL.
- SQLAlchemy uses `pool_pre_ping=True` to replace disconnected pooled
  connections before serving a request.

## Data preservation

A private custom-format `pg_dump` archive was exported before changing the
backend connection. The source was then set to read-only and a final archive
was taken to prevent writes from diverging during cutover.

All 11 public tables matched by row count and sorted row checksum. Database
sequences and constraint definitions also matched. Existing accounts, surveys,
plans, feedback, coach memory, password-reset records, knowledge documents,
chunks, and provider-specific embeddings were preserved.

The source used pgvector 0.8.1; Neon supplied 0.8.6. All 155 OpenAI embeddings
retained their 1,536 dimensions, and cosine-distance queries were checked on
the restored database. No embedding regeneration was performed.

## Verification

- Render's deployment became live with the Neon connection.
- Registration and login were exercised through Vercel's `/api` forwarding.
- Authenticated profile, survey-list, and recommendation-list requests passed.
- The temporary verification account was removed after those checks.
- Connection recovery is checked by disconnecting only a dedicated test
  connection and verifying SQLAlchemy reconnects successfully.

These checks confirm storage, authentication and API forwarding. They do not
constitute a new evaluation of AI coaching quality.

## Recovery

The old Render database was not deleted manually. Its free instance was due
to expire on 14 October 2026, so it is not a durable rollback destination.
Keep the private export in a secure location; never commit connection strings
or database archives to this repository.

To recover from an archive, provision an empty compatible PostgreSQL database,
restore with `pg_restore --no-owner --no-acl --single-transaction`, verify data
and Alembic revision, and update Render's connection before deploying.
After new production writes on Neon, use a fresh Neon backup for recovery
rather than reverting to the older pre-migration export.
