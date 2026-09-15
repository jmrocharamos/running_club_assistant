# Langfuse observability

Instrumentation runs in FastAPI on Render (and local Python processes). Traces
are viewed in the Langfuse project dashboard; Vercel needs no Langfuse keys.

## Configuration

Use the project's existing `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and
`LANGFUSE_HOST`. `LANGFUSE_BASE_URL` is also supported and takes precedence over
`LANGFUSE_HOST`. Use the endpoint shown in the Langfuse project's setup page.

`LANGFUSE_TRACING_ENABLED=true` enables tracing when both keys exist. Set it to
`false` to disable it. Missing keys disable telemetry without preventing the app
from running. `ENVIRONMENT` labels the environment. Render's `RENDER_GIT_COMMIT`
is used as the release; `APP_RELEASE` is an optional local override.

## Workflows

- Plan creation: request, safety assessment and validation, generation, mode
  validation, and the saved recommendation identifier.
- Revision: request, feedback safety assessment, numbered generation attempts,
  load/mode validation, and the saved revised recommendation identifier.
- Chat: request, memory loading, coach context, retrieval, embedding generation,
  response generation, and memory persistence.
- End chat: memory loading, summary generation, and memory persistence.
- Knowledge indexing: embedding calls record text counts and token usage.

Nested observations share a trace ID. Authenticated workflows attach the opaque
application user UUID, not an email or name. Retrieval records chunk identifiers,
result counts, and distances, without query or document contents. Generations
record model and prompt version. Tokens are split into mutually exclusive input,
cached input, output, and reasoning output buckets. Langfuse infers cost from its
model pricing definitions; verify model pricing in the dashboard if costs are
missing. No fixed prices are embedded in application code.

## Trace names and filtering

| Trace name | Tags |
| --- | --- |
| Plan generation | `running-plan`, `new-plan` |
| Plan revision | `running-plan`, `revised-plan` |
| Coach chat | `coach-chat` |
| Chat memory summary | `coach-chat`, `memory-summary` |

Names and tags propagate to child observations. In Langfuse's trace list, filter
Tags by `revised-plan` to see revisions. Correction attempts are named
`Revision correction` and carry `correction-retry`; the first attempt is named
`Revision generation`. Both stay under the same `Plan revision` trace.
These labels apply to new traces after deployment, not historical traces.

## Privacy and failure handling

The app uses the standard OpenAI client with explicit metadata-only Langfuse
observations. Do not reintroduce the automatic `langfuse.openai` wrapper: it can
capture prompts and responses. Function arguments/results, survey answers,
health details, chat text, passwords, tokens, and embeddings are not sent to
Langfuse. Exception type names are recorded, without messages or tracebacks.
No raw-content opt-in is provided.

The SDK uploads asynchronously and flushes on application shutdown. Telemetry
initialization, observation, update, score, and flush failures do not replace
application results or exceptions. A forced process termination can lose queued
telemetry. Failed rating exports are best effort; the database remains the source
of truth, and saving the rating again retries the export. There is no durable
telemetry outbox.

## Migration and ratings

Apply the new migration **before starting the changed backend**:

```sh
cd backend
.venv/bin/alembic upgrade head
```

The nullable `recommendations.langfuse_trace_id` stores the root trace ID for
newly generated/revised plans. Existing plans remain null and cannot be linked
retroactively. The column is internal and is not exposed in the API response.

A saved plan rating is sent as the numeric `plan_rating` score (1–5), using a
stable score ID per plan so later rating changes update the same score. Scoring
occurs after the database commit and only for plans with a trace ID.

Migration `72d849ab01f3` has been applied locally for testing. Production still
needs this migration when these uncommitted changes are eventually deployed.
Downgrading drops only the trace-link column, so existing links would be lost.

## Test tomorrow

1. Run `.venv/bin/pytest -q` from `backend`. Tests disable external tracing;
   the SDK integration test uses an in-memory exporter and fake credentials.
2. Restart the local backend with the existing Langfuse project settings.
3. Generate a plan and inspect its trace in Langfuse, filtering by the
   `development` environment. Confirm the model calls are children of the request.
4. Add feedback and revise. A validation correction should show attempts 1 and 2.
5. Send a coach message, then end the chat. Confirm retrieval, embedding, summary,
   and memory save observations, with no prompt/response content.
6. Rate a newly generated plan, then change its rating. Verify one `plan_rating`
   score with the latest value on that plan's trace.
7. Set `LANGFUSE_TRACING_ENABLED=false`, restart, and confirm the same app flows
   work without new traces. Restore it when finished.

Automated tests do not call OpenAI or the Langfuse cloud. Live dashboard ingestion
and actual model cost display require the manual checks above.

References:
- https://langfuse.com/docs/observability/sdk/instrumentation
- https://langfuse.com/docs/observability/features/token-and-cost-tracking
- https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk
