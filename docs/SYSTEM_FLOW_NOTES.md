# Running Club Assistant: System Flow Notes

**Embedding storage update:** Indexing and retrieval now select OpenAI or
Ollama through `embedding_service.py`. Vectors live in provider-specific tables,
and unchanged chunks survive indexing. The detailed Group 1 descriptions below
of full chunk replacement and the legacy chunk vector column describe the
original OpenAI implementation. See [Local models](LOCAL_MODELS.md) for the
current indexing behavior and setup. Generation still uses OpenAI.

This is the end-to-end map to read before changing the application. It records
what the current code actually does, not a proposed architecture. Start with
the big picture, then jump to the workflow you are changing.

## Big picture

The application has three user-facing AI workflows that must not be confused:

1. **Chat with coach** combines live runner context, coach memory, the current
   conversation, and RAG excerpts.
2. **Generate training plan** combines the runner profile and latest survey with
   safety and plan-generation prompts. **It does not currently use RAG, coach
   memory, or chat history.**
3. **Revise a training plan** combines one stored plan, feedback attached to
   that plan, a safety decision, and the remaining schedule. It creates a new
   recommendation instead of overwriting the selected one.

```text
CHAT
runner message
    |-- semantic retrieval ------------> official/general knowledge excerpts
    |-- build_coach_context() ----------> current runner database facts
    |-- coach_memory.summary -----------> learned chat summary + current chat
    `-- build_chatbot_input() ----------> get_chat_reply() ----------> reply

PLAN GENERATION
latest running-plan survey + basic user data
    `-- safety assessment -> plan prompt -> structured plan -> validation -> DB

PLAN REVISION
selected stored plan + its feedback
    `-- safety routing -> remaining dates -> revision prompt -> validation -> DB
```

The frontend, FastAPI backend, PostgreSQL database, and OpenAI calls fit
together like this:

```text
Browser / Next.js
  -> typed API wrapper
  -> TanStack Query hook or mutation
  -> FastAPI route
  -> authentication + Pydantic validation
  -> service / prompt / OpenAI client as needed
  -> SQLAlchemy + PostgreSQL
  -> Pydantic response
  -> frontend cache
  -> rendered page or chat widget
```

## Documentation coverage

- [x] Group 1 — RAG ingestion, indexing, retrieval, and augmentation.
- [x] Group 2 — Runtime foundation and authentication.
- [x] Group 3 — Database models, relationships, and ownership.
- [x] Group 4 — Survey creation, validation, history, and deletion.
- [x] Group 5 — Training-plan safety, generation, validation, and persistence.
- [x] Group 6 — Live coach context.
- [x] Group 7 — Coach memory and the complete chat lifecycle.
- [x] Group 8 — OpenAI client, prompt boundaries, and structured outputs.
- [x] Group 9 — Feedback, health updates, and plan revision.
- [x] Group 10 — Plan reads, favorites, ratings, and deletion.
- [x] Group 11 — Frontend providers, API wrappers, caching, and user journeys.
- [x] Group 12 — Endpoint map, file map, boundaries, and debugging order.

Recommended reading order for the AI core is Group 1 (RAG), Group 6 (live
context), Group 7 (memory/chat), Group 8 (LLM boundary), Group 5 (new plans),
then Group 9 (revisions). Groups 2–4 explain the application foundation those
flows depend on.

---

# Group 1 — How RAG works

## 1. What “RAG” means in this project

RAG means **retrieval-augmented generation**. The application does not train or
fine-tune the chat model on Braves documents. Instead it:

1. stores curated Markdown documents;
2. splits them into smaller passages;
3. converts each passage into an embedding vector;
4. converts the runner's latest message into another vector;
5. finds the stored vectors closest in meaning to that message; and
6. places the matching text passages into the chat model's input.

The LLM therefore receives relevant reference text at answer time. The
embedding model finds text; the chat model writes the answer. These are two
different model calls with different jobs.

## 2. The two separate RAG phases

```text
OFFLINE / MANUAL PREPARATION
knowledge_docs/*.md
  -> load_knowledge_documents()
  -> parse_knowledge_document()
  -> sync_knowledge_documents()
  -> knowledge_base table (whole documents)
  -> chunk_document()
  -> _build_embedding_input()
  -> create_embeddings()
  -> knowledge_chunks table (passages + vectors)

ONLINE / ON EVERY CHAT MESSAGE
runner's latest message
  -> retrieve_knowledge()
  -> create_embeddings([message])
  -> PostgreSQL cosine-distance query
  -> at most 5 chunks with distance <= 0.65
  -> _format_knowledge()
  -> build_chatbot_input()
  -> get_chat_reply()
  -> answer
```

The offline phase is not invoked by the chat endpoint. Adding or editing a
Markdown file has no effect on chat until the sync and index scripts are run.

## 2.1 Where the R, A, and G happen

The name **RAG** describes three distinct operations in the online chat flow:

```text
R — RETRIEVAL
chatbot.py
retrieve_knowledge(db, chat_data.message)
    |
    `-> returns knowledge_chunks: list[dict]

A — AUGMENTATION
chatbot.py
build_chatbot_input(
    chat_data.message,
    coach_context,
    coach_memory.summary,
    conversation_history,
    knowledge_chunks,          # retrieval result enters here
)
    |
    `-> chatbot_input.py inserts the formatted chunks under
        "RETRIEVED KNOWLEDGE EXCERPTS"

G — GENERATION
chatbot.py
get_chat_reply(input_text, instructions, "simple")
    |
    `-> client_openai.py sends the augmented input to gpt-5-mini
        and returns {"reply": "..."}
```

### R — Retrieval and its arguments

In `chat_with_coach()` the call is:

```python
knowledge_chunks = retrieve_knowledge(
    db,
    chat_data.message,
)
```

`retrieve_knowledge()` accepts:

- `db`: the request's SQLAlchemy database session, used to query pgvector;
- `query`: here, only the latest runner message;
- `limit`: optional maximum result count, defaulting to 5.

Its return value is assigned to `knowledge_chunks`. This list is the bridge
from Retrieval to Augmentation.

### A — Where retrieval is appended to the model input

The retrieval result is not appended to the conversation history and is not
saved in coach memory. It is passed as the fifth argument of
`build_chatbot_input()`:

```python
input_text = build_chatbot_input(
    chat_data.message,
    coach_context,
    coach_memory.summary,
    conversation_history,
    knowledge_chunks,
)
```

Those positional arguments map to this function signature in
`backend/app/prompts/chatbot_input.py`:

```python
def build_chatbot_input(
    message,
    coach_context,
    memory,
    conversation_history,
    knowledge_chunks,
) -> str:
```

Inside that function, this expression performs the actual augmentation:

```python
RETRIEVED KNOWLEDGE EXCERPTS

{_format_knowledge(knowledge_chunks)}
```

`_format_knowledge()` turns the list of dictionaries into readable reference
blocks. The resulting blocks become part of the temporary `input_text` string
sent for this one answer. “Augmented” therefore means **the retrieved passages
are inserted into the LLM input alongside the runner context, memory,
conversation, and current message**. It does not mean the LLM or its training
data is permanently changed.

### G — Generation and its arguments

Back in `chat_with_coach()`, the augmented string is passed to:

```python
result = get_chat_reply(
    input_text,
    instructions,
    "simple",
)
```

The arguments are:

- `input_text`: the complete augmented input assembled above;
- `instructions`: `SIMPLE_CHATBOT_PROMPT`, returned by
  `get_chatbot_prompt()`; this defines the coach role and grounding rules;
- `prompt_version`: `"simple"`; this is attached as observability metadata,
  not shown as content to the runner.

In `backend/app/client_openai.py`, `get_chat_reply()` makes the generative model
call:

```python
client.responses.parse(
    model="gpt-5-mini",
    instructions=instructions,
    input=input_text,
    text_format=ChatReplyOutput,
    metadata={...},
)
```

The OpenAI request arguments have these jobs:

- `model`: chooses the model that writes the answer;
- `instructions`: supplies stable behavior and grounding rules;
- `input`: supplies the per-request augmented information and question;
- `text_format`: requires structured output matching `ChatReplyOutput`;
- `metadata`: labels the call for tracing/observability.

`response.output_parsed` is converted to a dictionary. The route takes
`result["reply"]`, appends that generated reply and the runner's message to
`current_conversation`, commits memory, and returns the reply to the frontend.

In one sentence: **Retrieval returns `knowledge_chunks`; Augmentation renders
those chunks inside `input_text`; Generation sends that `input_text` plus the
coach instructions to `gpt-5-mini`.**

## 3. Source documents

Location: `backend/knowledge_docs/*.md`

Each top-level Markdown file is one knowledge document. Files under subfolders
such as `sources/` and `images/` are not loaded because the loader uses the
non-recursive pattern `directory.glob("*.md")`.

Every loaded document must have YAML frontmatter surrounded by `---`. Required
metadata fields are:

- `title`
- `document_type`
- `publisher`
- `content_origin`
- `content_status`
- `language`
- `topics`

The Markdown after the frontmatter is the document body. Titles must be unique
across all loaded files. Dates produced by YAML are converted to strings so the
metadata can be stored safely in PostgreSQL JSONB.

Important functions in
`backend/app/services/knowledge_document_service.py`:

- `parse_knowledge_document(path)` validates frontmatter and returns a database
  shaped dictionary. It separates `title` and `document_type`, stores the body
  as `content`, produces a source such as
  `knowledge_docs/club_weekly_running_calendar.md`, and keeps the remaining
  metadata in `metadata_`.
- `load_knowledge_documents(directory)` loads all top-level Markdown files in
  sorted filename order and rejects duplicate titles.
- `sync_knowledge_documents(db, documents)` makes the table mirror the loaded
  files. It matches by `source`, creates new rows, updates changed rows, and
  deletes rows whose source file is no longer present.

## 4. Syncing whole documents into PostgreSQL

Entrypoint: `backend/scripts/sync_knowledge_base.py`

Run from `backend/`:

```bash
python scripts/sync_knowledge_base.py
```

The script:

1. loads `backend/knowledge_docs/*.md`;
2. opens a SQLAlchemy session;
3. calls `sync_knowledge_documents()`;
4. commits the transaction; and
5. prints the created/updated/unchanged/deleted titles.

A database document whose source file disappeared is deleted. Its chunks are
also deleted through the foreign key's `ON DELETE CASCADE` behavior.

Database model: `backend/app/models/knowledge_base.py`

`KnowledgeBase` stores each complete source document:

- `id`: UUID primary key;
- `title`: human-readable title;
- `content`: full Markdown body without frontmatter;
- `document_type`: category used when formatting retrieved results;
- `source`: source file path;
- `metadata`: JSONB containing publisher, status, topics, and other fields;
- timestamps.

Syncing changes only `knowledge_base`. It does not create or refresh vectors.

### `sync_knowledge_documents()` step by step

The function follows one rule: `backend/knowledge_docs` is the source of truth,
and `knowledge_base` mirrors it. It reports four possible outcomes.

Suppose the database starts with documents A, B, and C, while the filesystem
loader supplies A, B, and D:

1. It reads all existing rows once: `[A, B, C]`.
2. It builds a `documents_by_source` dictionary. This provides direct lookups
   and avoids a database query for each input file.
3. For incoming A, it finds the existing row. If any parsed field differs, A is
   added to `updated`; otherwise it is added to `unchanged`.
4. For incoming B, it performs the same comparison.
5. For incoming D, the lookup finds no row, so it stages
   `KnowledgeBase(**data)` and reports D as `created`.
6. It builds the set of incoming source paths: A, B, and D.
7. It checks the rows that existed before synchronization. C's source is absent
   from that set, so it stages deletion of C and reports it as `deleted`.
8. It returns the action report. The caller, not this function, commits.

The remaining bookkeeping serves two purposes:

- **Efficiency:** existing rows are loaded once and found through a dictionary.
- **Clear reporting:** the script tells the developer exactly what it created,
  updated, left unchanged, and deleted.

Identity is intentionally based only on `source`. Renaming a Markdown file is
treated as deleting the old source and creating a new one. Editing its title or
content without renaming the file updates the existing row.

## 5. Chunking and indexing

Entrypoint: `backend/scripts/index_knowledge_base.py`

Run this after syncing:

```bash
python scripts/index_knowledge_base.py
```

This is a **full rebuild**, not an incremental update:

1. it stages deletion of every existing `KnowledgeChunk` row;
2. reads every `KnowledgeBase` document;
3. calls `chunk_document(document.content)`;
4. builds embedding input for every surviving chunk;
5. makes one embeddings API request per document;
6. stages new chunk rows; and
7. commits once, after all documents are processed.

If an exception occurs before the commit, closing the session rolls back the
staged deletion and inserts. That protects the previous index from a partial
rebuild.

### How `chunk_document()` splits text

File: `backend/app/services/knowledge_chunking_service.py`

It uses two LangChain splitters in sequence:

1. `MarkdownHeaderTextSplitter` first divides content around `#`, `##`, and
   `###` headings and records the heading trail as metadata (`h1`, `h2`, `h3`).
   Headers remain in the chunk text because `strip_headers=False`.
2. `RecursiveCharacterTextSplitter` then keeps chunks around 800 characters,
   with 100 characters of overlap between adjacent size-based chunks.

`_has_substantive_content()` drops chunks with fewer than 20 meaningful
characters after ignoring heading lines, images, and Markdown link targets.
This prevents image-only or heading-only passages from entering the index.

### What is embedded

`_build_embedding_input(document_title, chunk)` in the indexing script creates:

```text
document title
heading > subheading > sub-subheading

actual chunk content
```

Adding the document title and heading trail helps short passages carry their
meaning into vector space. This enriched string is sent only to the embeddings
API. The database stores the original chunk content and heading metadata, not
the enriched embedding input.

`create_embeddings(texts)` in `backend/app/client_openai.py` calls OpenAI's
`text-embedding-3-small`. Its returned vectors are kept in the same order as
the inputs. The indexing script asserts that the chunk and vector counts match.

### Where vectors live

Model: `backend/app/models/knowledge_chunk.py`

Migration:
`backend/alembic/versions/a4f72fbaa05d_create_knowledge_chunks_table.py`

`KnowledgeChunk` stores:

- its own UUID;
- `knowledge_base_id`, with cascade deletion from the parent document;
- zero-based `chunk_index` within that document;
- original chunk `content`;
- a 1536-dimensional pgvector `embedding`;
- heading metadata as JSONB;
- timestamps.

The migration enables PostgreSQL's `vector` extension. It creates a normal
index on `knowledge_base_id`, but no HNSW or IVFFlat vector index. Retrieval is
therefore an exact cosine-distance ordering over eligible chunk rows. That is
simple and accurate for a small knowledge base, but will become slower as the
number of chunks grows.

## 6. Retrieval for a chat message

File: `backend/app/services/knowledge_retrieval_service.py`

Function: `retrieve_knowledge(db, query, limit=5)`

It performs these exact steps:

1. strips whitespace from the query;
2. returns `[]` without an API call if the result is empty;
3. rejects limits below 1;
4. embeds only the cleaned query using the same
   `text-embedding-3-small` helper;
5. asks pgvector to calculate cosine distance between the query and every
   stored chunk embedding;
6. joins each chunk to its parent `KnowledgeBase` document;
7. keeps only results whose distance is at most `0.65`;
8. orders ascending, so the smallest/closest distance is first; and
9. returns at most 5 results by default.

Cosine distance is lower when two embeddings point in more similar semantic
directions. `0.65` is a distance ceiling, not a “65% relevance score.” The
current value is hard-coded as `MAX_COSINE_DISTANCE`, and there is no keyword
search, reranker, per-topic filter, recency filter, or document-diversity rule.
Several top chunks may therefore come from the same source document.

Every returned dictionary contains the chunk and document IDs, title, source,
content status, document type, original content, heading metadata, and numeric
distance. Not all of those fields are later shown to the LLM.

### A subtle but important boundary

The retrieval query is only `chat_data.message`, the runner's latest message.
The current conversation, coach memory, and live runner context are not used to
search the vector database. They are added later for answer generation. A
follow-up such as “What time is it?” may retrieve poorly because the standalone
message does not say which club session “it” refers to, even though the chat
history contains that information.

## 7. Putting retrieved knowledge into the LLM input

API entrypoint: `chat_with_coach()` in
`backend/app/api/routes/chatbot.py`

For each `POST /chatbot/` request, the route first loads runner context and
memory. Inside one error boundary it then:

1. calls `retrieve_knowledge(db, chat_data.message)`;
2. passes the results to `build_chatbot_input()`; and
3. calls `get_chat_reply()`.

File: `backend/app/prompts/chatbot_input.py`

`_format_knowledge()` renders each retrieved chunk as:

```text
[document_type] Document title
Source: knowledge_docs/file.md
Status: content_status
chunk text
```

Chunks are separated by blank lines. If none passes the threshold, the prompt
contains `No relevant knowledge found.` It does not include distance, IDs, or
the complete JSON metadata.

`build_chatbot_input()` creates one large input containing, in order:

1. live runner background;
2. previous-session memory summary;
3. the current session transcript;
4. retrieved knowledge excerpts;
5. the latest runner message; and
6. a final instruction to use those sections in the reply.

The latest message appears twice in the full request lifecycle: once as the
retrieval query and once as the message the chat model must answer.

## 8. How the model is told to use RAG

File: `backend/app/prompts/chatbot_prompt.py`

`get_chatbot_prompt()` supplies `SIMPLE_CHATBOT_PROMPT` as the OpenAI
instructions. Its key grounding rules are:

- personalize with runner context and memory when relevant;
- use only relevant excerpts;
- do not mix rules or schedules from different club services;
- use retrieved excerpts as the only source for official Berlin Braves facts;
- admit when an official fact is missing instead of guessing;
- preserve the status warnings on time-sensitive information; and
- allow clearly distinguished general coaching knowledge for general running
  questions even when RAG finds nothing.

File: `backend/app/client_openai.py`

`get_chat_reply()` sends those instructions and the assembled input to
`gpt-5-mini` through the OpenAI Responses API. The result is parsed as
`ChatReplyOutput`, whose only field is `reply`. If structured parsing produces
no output, it raises an error.

The API response returns only the answer text. Retrieved source titles,
distances, and citations are not exposed to the frontend, and there is no
post-generation check that each factual statement is supported by a retrieved
passage.

If embedding, database retrieval, prompt building, or answer generation raises
inside the route's `try`, the client receives HTTP 502 with a generic retry
message. The reply is appended to the current conversation and committed only
after successful generation.

## 9. The complete call chain

### Build or refresh the knowledge index

```text
scripts/sync_knowledge_base.py:main
  -> load_knowledge_documents
       -> parse_knowledge_document (once per top-level Markdown file)
  -> sync_knowledge_documents
  -> db.commit

scripts/index_knowledge_base.py:main
  -> delete all KnowledgeChunk rows (staged)
  -> for each KnowledgeBase row:
       -> chunk_document
       -> _build_embedding_input (once per chunk)
       -> create_embeddings (one batch API call per document)
       -> db.add(KnowledgeChunk) (once per chunk)
  -> db.commit
```

### Answer one chat message

```text
POST /chatbot/
  -> chat_with_coach
       -> get_or_create_coach_memory
       -> build_coach_context
       -> get_chatbot_prompt
       -> retrieve_knowledge
            -> create_embeddings([latest message])
            -> pgvector cosine-distance SELECT
       -> build_chatbot_input
            -> _format_conversation
            -> _format_knowledge
       -> get_chat_reply
            -> OpenAI Responses API + ChatReplyOutput
       -> append user and assistant turns to current_conversation
       -> db.commit
  -> {"reply": "..."}
```

## 10. What RAG currently does not do

- It does not automatically watch or index changed files.
- It does not retrieve for training-plan generation.
- It does not use coach memory or conversation history to form the search
  query.
- It does not combine semantic search with exact keyword search.
- It does not rerank results after pgvector search.
- It does not filter by publisher, topic, status, or date.
- It does not guarantee one result per document.
- It does not return citations to the UI.
- It has no automated tests covering parsing, chunking, indexing, retrieval, or
  prompt injection at the time these notes were written.
- It has no approximate vector index; the database orders exact distances.

These are current boundaries, not necessarily bugs. They are the places to
inspect first when retrieved answers seem irrelevant, stale, unsupported, or
slow.

## 11. Safe update procedure

After adding or editing a knowledge document:

```bash
cd backend
python scripts/sync_knowledge_base.py
python scripts/index_knowledge_base.py
```

Then test the real `POST /chatbot/` flow with:

- a direct question whose answer uses distinctive wording from the document;
- a paraphrase, to verify semantic rather than exact-word retrieval;
- an unrelated question, to verify weak chunks are excluded;
- a time-sensitive club question, to verify the status warning survives; and
- a follow-up question containing a pronoun, to expose the current
  latest-message-only retrieval limitation.

The database container must be running, migrations must be at head, and OpenAI
credentials must be configured for both indexing and live retrieval.

## 12. Debugging checklist

When the coach fails to use expected knowledge, check in this order:

1. Is the source a top-level `.md` file in `backend/knowledge_docs/`?
2. Does it have all required frontmatter fields and a unique title?
3. Was the sync script run, and did it report created or updated?
4. Was the index script run after the sync?
5. Does `knowledge_chunks` contain chunks for the document?
6. Is the expected passage substantive and present in a stored chunk?
7. Does `retrieve_knowledge()` return it for the standalone latest message?
8. Is its cosine distance at most `0.65`, and is it inside the top five?
9. Does `_format_knowledge()` place it in the assembled chatbot input?
10. Do the chatbot instructions permit using it for this type of question?

---

# Group 2 — Application foundation and authentication

## 13. Runtime components

The application runs as three main processes/services:

- **Next.js frontend** at `http://localhost:3000`.
- **FastAPI backend** normally at `http://127.0.0.1:5002`.
- **PostgreSQL with pgvector** in Docker, exposed only on localhost.

`frontend/src/app/layout.tsx` installs the application providers around every
page. `frontend/src/app/(app)/layout.tsx` wraps protected pages with
`AuthGuard` and `AppShell`. `backend/app/main.py` creates FastAPI, permits the
local frontend through credentialed CORS, and registers all route modules.

`backend/app/db/session.py` creates the SQLAlchemy engine and `SessionLocal`.
The `get_db()` dependency gives each request a session and closes it afterward.
Routes or services explicitly call `commit()`; closing the session is not a
substitute for committing.

## 14. Authentication flow

The browser never receives the JWT through JavaScript-accessible storage.
Registration and login set it in an HTTP-only cookie called `access_token`.

```text
login/register form
  -> authApi.login/register
  -> POST /auth/login or /auth/register
  -> validate credentials / create user
  -> create_access_token(user.id)
  -> set_auth_cookie(response, token)
  -> browser stores HTTP-only cookie
  -> later apiClient requests use credentials: "include"
```

Important backend functions:

- `hash_password()` and `verify_password()` in `core/security.py` use the
  recommended `pwdlib` password hasher.
- `create_access_token()` creates a signed HS256 JWT containing the user UUID,
  issued-at time, and expiry.
- `set_auth_cookie()` sets HTTP-only, same-site-lax cookie attributes. `secure`
  is enabled only when `ENVIRONMENT=production`.
- `get_current_user()` reads and decodes the cookie and loads the user. Most
  application routes depend on this function.
- Ownership helpers such as `_get_owned_survey()` and
  `_get_owned_recommendation()` additionally ensure a valid user cannot read or
  mutate another runner's resource.

Frontend authentication has two layers:

1. `frontend/src/proxy.ts` checks whether the cookie exists before protected
   navigation. This is only an optimistic check; it cannot prove the JWT is
   valid.
2. `SessionProvider` calls `GET /auth/me`. `AuthGuard` waits for that result and
   redirects to `/login` when the backend rejects the session.

`frontend/src/lib/api/client.ts` centralizes every fetch. It includes cookies,
parses JSON, turns status codes into typed `ApiError` objects, and emits an
unauthorized event for a mid-session 401. `SessionProvider` responds by clearing
cached server data. `BroadcastChannel` in `session-sync.ts` tells other browser
tabs when a login/logout changes the shared cookie.

## 15. Registration, profile, and password flows

- `POST /auth/register` checks unique email and username, hashes the password,
  creates the user, logs them in immediately, and returns `UserRead`.
- `POST /auth/login` verifies email/password and sets a new cookie.
- `POST /auth/logout` requires a valid session and deletes the cookie.
- `GET /auth/me` and `GET /users/me` both return the current user.
- `PATCH /users/me` applies only fields supplied by `UserUpdate` and commits.
- `POST /auth/change-password` verifies the current password before replacing
  the hash.
- `POST /auth/forgot-password` always returns the same message to avoid account
  enumeration. For a known user it stores only a SHA-256 hash of a random reset
  token. Local email delivery prints the link through the configured sender.
- `POST /auth/reset-password` hashes the submitted token, rejects missing,
  expired, or used rows, changes the password, and marks the token used.

Important files:

- Backend: `api/routes/auth.py`, `api/routes/users.py`, `core/security.py`,
  `core/config.py`, `services/email_sender.py`, and the auth/user schemas.
- Frontend: public auth pages, `SessionProvider`, `AuthGuard`, `proxy.ts`,
  `lib/api/auth.ts`, and `lib/validation/auth.ts`.

---

# Group 3 — Data model and ownership

## 16. Main database relationships

```text
User
  |--< Survey
  |      `--< Recommendation
  |              `--< Feedback
  |--< Feedback
  `--- CoachMemory (maximum one per user)

KnowledgeBase
  `--< KnowledgeChunk

User
  `--< PasswordResetToken
```

What each model means:

- `User`: identity, credentials, profile, measurements, interests, and contact
  fields.
- `Survey`: an immutable historical set of answers used to request a plan.
  `deleted_at` implements soft deletion.
- `Recommendation`: a generated plan. It stores structured `content`, an
  `explanation`, and a `survey_snapshot` so the plan retains its original input
  even if newer surveys are created.
- `Feedback`: chronological free text attached to one recommendation. Structured
  health updates are encoded into the same text column with a
  `HEALTH_UPDATE_V1` marker.
- `CoachMemory`: one JSONB summary per user, containing long-term chat summary
  fields and the current unsummarized conversation.
- `KnowledgeBase` and `KnowledgeChunk`: the RAG whole-document and searchable
  passage layers described in Group 1.
- `PasswordResetToken`: hashed, expiring, single-use password reset records.

Physical deletion cascades down foreign keys. Application survey deletion is
normally soft, so its recommendations remain. Deleting a recommendation is
physical and its feedback is deleted through cascade behavior.

## 17. API ownership rule

The frontend never chooses an arbitrary `user_id` for current-user operations.
The backend derives it from the signed cookie. Resource routes return 404 both
when a record is missing and when it belongs to someone else, avoiding disclosure
that another user's record exists.

---

# Group 4 — Survey lifecycle

## 18. Creating a survey

The UI uses `SurveyForm`, a five-step React Hook Form wizard:

1. goals and timeline;
2. experience and current volume;
3. schedule, terrain, and equipment;
4. health, recovery, sleep, and stress; and
5. nutrition/personalization preferences.

`frontend/src/lib/validation/survey.ts` performs client-side Zod validation.
The backend repeats authoritative validation with
`RunningPlanSurveyAnswers` in `backend/app/schemas/survey.py`. Important
cross-field rules include unique training days, enough days for the requested
run frequency, a long-run day contained in preferred days, consistent “none”
choices, explicit clearance when pain/issues exist, and an event date later
than the plan start.

The save path is:

```text
SurveyForm.onSubmit
  -> surveysApi.create(answers)
  -> POST /surveys/
  -> SurveyCreate discriminates by survey_type
  -> create_survey()
  -> answers.model_dump(mode="json")
  -> INSERT Survey
  -> commit + SurveyRead
```

The frontend currently creates only running-plan surveys. The enum and backend
union also mention shoe recommendations, but there is no shoe-plan generation
workflow.

## 19. Survey history and deletion

- `GET /surveys/` returns the user's non-deleted surveys newest first.
- `GET /surveys/latest` returns the newest non-deleted survey or 404.
- `GET /surveys/{id}` returns an owned survey even if it was soft-deleted.
- `DELETE /surveys/{id}` sets `deleted_at`; it does not remove the row.

There is deliberately no survey update endpoint. A new survey represents a new
historical state. Existing recommendations keep their own `survey_snapshot`.

Important boundary: `build_coach_context()` currently selects the latest
running-plan survey without filtering `deleted_at`. A soft-deleted survey can
therefore still become chat context even though list/latest endpoints hide it.

---

# Group 5 — Generate-plan flow

## 20. Frontend orchestration

On `frontend/src/app/(app)/survey/new/page.tsx`, a successful survey creation is
immediately followed by `useGenerateRecommendation()`:

```text
save survey successfully
  -> POST /recommendations/generate
  -> show simulated generation progress
  -> success: navigate to /plans/{new id}
  -> failure: keep saved survey and offer generation retry
```

The generation request has a 180-second browser timeout. The progress labels in
`use-generation-progress.ts` are simulated from elapsed time; the backend does
not stream real stage progress.

The dashboard and plans page can also render `GeneratePlanButton`. It calls the
same endpoint and therefore always uses the latest non-deleted running-plan
survey, not a survey ID supplied by the browser.

## 21. Backend endpoint preparation

`generate_recommendation_for_current_user()` in
`api/routes/recommendations.py`:

1. authenticates the user;
2. selects their newest non-deleted survey;
3. returns 404 when none exists;
4. rejects a non-running-plan survey;
5. calculates age from the user's birth date;
6. builds a small user dictionary (`full_name`, `age`);
7. builds a survey dictionary (`answers`, `created_at`); and
8. calls the generation service.

## 22. Safety-mode selection

`generate_recommendation()` in
`services/recommendation_generation_service.py` begins with
`assess_training_safety()`.

For the simple healthy case—pain is zero and issue areas are exactly
`{"none"}`—the service selects `normal_running` locally without an LLM call.
Otherwise it:

1. formats only issue areas, pain, and cleared activities with
   `build_training_safety_input()`;
2. loads `TRAINING_SAFETY_PROMPT_V1`;
3. calls `get_training_safety_assessment()` using `gpt-5-mini`; and
4. parses a `TrainingSafetyAssessment` containing `plan_mode` and `message`.

Available modes are:

- `normal_running`
- `easy_running`
- `walk_run`
- `walk_only`
- `blocked`

`validate_training_safety()` then enforces the result in deterministic Python.
It prevents normal running with a concern, requires explicit clearance for an
adapted plan, maps each mode to required clearance, and restricts pain above 3
to walk-only or blocked. If mode is `blocked`, the service raises
`TrainingBlockedError`; the route returns HTTP 409 with reason
`training_blocked` rather than generating a plan.

## 23. Plan prompt and generation

When generation is allowed:

1. `get_running_plan_prompt(plan_mode)` selects normal or adapted instructions
   and a prompt-version label.
2. `build_running_plan_input(user, survey, plan_mode)` formats runner identity,
   dates, goal, current volume, schedule, equipment, health, recovery, and
   preferences.
3. `get_recommendation()` calls `gpt-5-mini` through
   `client.responses.parse()`.
4. `text_format=RunningPlanOutput` requires the model response to match the
   Pydantic structured-output schema.

Normal-plan instructions cover frequency, preferred days, progressive load,
long runs, taper/event behavior, strength/mobility, calendar construction, and
distance consistency. Adapted instructions replace those with the selected
safety boundary and explicitly prohibit unsafe intensity or uncleared activity.

`RunningPlanOutput` contains:

```text
content
  |-- summary
  |-- weekly_distance[]
  |-- training_days[]
  |     |-- running or walking
  |     |-- strength
  |     |-- mobility
  |     `-- notes
  `-- safety_notes[]

explanation
  `-- why_this_plan_fits[]
```

## 24. Deterministic post-processing

The model result is not saved immediately:

- `synchronize_weekly_distances()` sorts training days by ISO date, calculates
  weekly totals from running plus walking blocks, and overwrites every reported
  weekly distance with the calculated value.
- `validate_plan_mode()` rejects a day containing both running and walking,
  walking in normal mode, excessive intensity in easy-running mode, continuous
  running in walk-run mode, uncleared walking variants, and non-walk activity in
  walk-only mode.

Structured-output parsing validates field presence, allowed literal values, and
positive distances. The Python post-processing protects important invariants
that the model can still violate semantically.

## 25. Persistence and errors

After successful generation, the route:

1. counts the user's non-revised plans with `get_next_plan_number()`;
2. creates a title such as `Plan 3 · Build Endurance`;
3. stores the generated content and explanation;
4. copies the current answers into `survey_snapshot`;
5. commits a new `Recommendation`; and
6. returns `RecommendationRead` with HTTP 201.

Unexpected safety/generation/validation failures become HTTP 502. A blocked
safety decision becomes HTTP 409. No recommendation row is created on failure.
Langfuse observes plan generation and receives user ID, feature, environment,
prompt version, and plan-mode metadata through the OpenAI wrapper.

### Critical boundary

Plan generation does **not** call `retrieve_knowledge()`,
`build_coach_context()`, or `get_or_create_coach_memory()`. Official Braves
documents, previous chats, memory, feedback, and prior plans do not influence a
new plan. Only basic user data, the latest survey, application prompts, and the
model do.

---

# Group 6 — Coach context

## 26. Context is current database data, not memory

`build_coach_context(db, user)` in
`backend/app/services/coach_context_service.py` builds a fresh read-only
snapshot for every chat message. It queries:

- the latest running-plan survey;
- the three most recent running-plan recommendations; and
- the five most recent feedback entries across the user's plans.

The returned object contains:

- `profile`: full name, height, and interests;
- `latest_survey`: timestamp plus selected fields listed in `SURVEY_FIELDS`;
- `recent_plans`: ID, title, summary, rating, and creation time; and
- `recent_feedback`: recommendation ID, plan title, feedback text, and time.

This data is reconstructed from live tables on every message. It is not copied
into long-term chat memory. The chat prompt says newer feedback should be
treated as more current than older survey answers and recent plans as
historical rather than automatically active.

Context and memory answer different questions:

```text
Coach context: What does the application database say now?
Coach memory:  What stable facts did the runner explicitly say in past chats?
```

---

# Group 7 — Coach memory and chat lifecycle

## 27. Memory shape and creation

`CoachMemory` has a unique `user_id`, so each runner has at most one row. Its
JSONB `summary` follows `CoachMemorySummary`:

```text
chat
  |-- current_goal: string or null
  |-- preferences: string[]
  |-- topics_of_interest: string[]
  |-- progress: string or null
  `-- current_conversation: ChatMessage[]
```

`get_or_create_coach_memory()` queries by user ID. When absent, it creates the
empty Pydantic default, adds it, and calls `flush()` so the row is available in
the current transaction. It does not commit; the calling route commits.

## 28. Sending a chat message

The complete backend order in `chat_with_coach()` is:

1. authenticate the runner;
2. get/create their memory row;
3. read `current_conversation`;
4. build fresh coach context;
5. retrieve knowledge using only the latest message;
6. build the augmented input from context, summary, transcript, RAG, and the
   latest message;
7. generate a structured `ChatReplyOutput` with `gpt-5-mini`;
8. append the user message and generated reply to `current_conversation`;
9. replace `coach_memory.summary` with the updated chat object;
10. commit; and
11. return only `{"reply": ...}`.

If retrieval or generation fails, the route returns HTTP 502 and does not append
either turn. The RAG chunks are temporary prompt context; they are not stored in
memory or returned as citations.

## 29. Frontend chat behavior

`CoachChatProvider` lives inside `AppShell`, so one chat widget is available on
all protected pages. On mount it loads `GET /chatbot/history` into the
`["chat", "history"]` TanStack Query cache with infinite stale time.

When the runner sends:

1. the provider optimistically appends the runner message to the local cache;
2. `chatApi.sendMessage()` posts it;
3. success appends the server reply;
4. a closed widget marks the reply unread; and
5. failure marks that optimistic message as failed so the UI can retry it.

The welcome message is UI-only and is not stored in the database. Assistant
responses are rendered through React Markdown; runner messages are rendered as
plain text.

## 30. Ending and summarizing a chat

Closing the widget does not end the conversation. The transcript remains in
`current_conversation`. The runner must choose **End chat**, which calls
`POST /chatbot/end`.

If the transcript is empty, the backend simply returns the current summary. If
it contains messages:

1. `_user_profile()` selects name, interests, and shoe size;
2. `build_conversation_summary_input()` combines that profile, previous memory,
   and the full current transcript;
3. `get_memory_summary_prompt()` supplies strict memory rules;
4. `summarize_conversation()` calls `gpt-4o-mini` and parses
   `ChatSummaryOutput`;
5. the backend replaces the long-term summary fields;
6. `current_conversation` is reset to `[]`; and
7. the row is committed and returned.

The memory prompt says to store only facts explicitly stated by the runner,
carry forward still-valid information, and avoid copying live survey/plan data,
temporary schedules, prices, registration status, relative dates, or assumed
medical clearance. Coach replies are not treated as runner facts.

The frontend clears/refetches chat history and displays the returned summary in
`EndChatSummaryDialog`. A new chat begins with an empty transcript but the
summary remains available for personalization.

## 31. Reading chat history

`GET /chatbot/history` ensures a memory row exists, commits if creation was
needed, and returns the current transcript plus summary fields. It does not call
an LLM, retrieve knowledge, or rebuild coach context.

---

# Group 8 — LLM boundary and prompt assembly

## 32. One centralized OpenAI client

`backend/app/client_openai.py` creates a Langfuse-wrapped OpenAI client and
contains the external model calls:

| Function | Model | Structured schema | Purpose |
| --- | --- | --- | --- |
| `create_embeddings()` | `text-embedding-3-small` | vector list | Index/query RAG |
| `get_training_safety_assessment()` | `gpt-5-mini` | `TrainingSafetyAssessment` | Select initial plan mode |
| `get_recommendation()` | `gpt-5-mini` | `RunningPlanOutput` | Generate or revise a plan |
| `get_feedback_safety_assessment()` | `gpt-5-mini` | `FeedbackSafetyAssessment` | Route revision safety |
| `get_chat_reply()` | `gpt-5-mini` | `ChatReplyOutput` | Answer a chat message |
| `summarize_conversation()` | `gpt-4o-mini` | `ChatSummaryOutput` | Compress an ended chat |

The prompt modules are split into two concepts:

- `*_prompt.py` returns stable **instructions**: role, constraints, safety rules,
  and output expectations.
- `*_input.py` formats per-request **input**: the particular runner, survey,
  plan, feedback, memory, RAG chunks, or conversation.

Prompt-version strings are metadata for observability and prompt tracking. The
Pydantic class passed as `text_format` constrains output shape; it does not by
itself guarantee every domain rule, which is why deterministic validators run
after plan generation.

## 33. Failure boundaries

Routes intentionally convert most OpenAI failures to generic HTTP 502 messages
so internal exceptions and provider details are not sent to the browser.
Pydantic request errors become 422. Domain prerequisites commonly use 400 or
404. Safety decisions that need user action use structured 409 responses.

The frontend API client maps these statuses into `ApiError.kind`, preserves the
backend `detail`, and lets components show specific flows such as blocked
generation, required health update, or coach review.

---

# Group 9 — Feedback and plan revision

## 34. Feedback storage

On a plan detail page, `FeedbackForm` calls
`POST /recommendations/{id}/feedback`. The backend checks ownership, validates
and trims text with `FeedbackCreate`, creates a `Feedback` row, and commits.
`GET /recommendations/{id}/feedback` returns entries oldest first, which is the
order used by the safety and revision prompts.

Feedback belongs only to the selected recommendation. A revised recommendation
starts with no copied feedback entries.

## 35. Revision safety routing

`POST /recommendations/{id}/revise` first requires at least one feedback entry.
It creates plain dictionaries from the selected recommendation and its feedback,
then calls `assess_feedback_safety()`:

```text
selected plan snapshot + chronological feedback
  -> build_feedback_safety_input()
  -> FEEDBACK_SAFETY_PROMPT_V4
  -> get_feedback_safety_assessment()
  -> FeedbackSafetyAssessment
```

The assessment has one of three decisions:

- `continue_revision`: automatic revision may proceed and `plan_mode` is set.
- `needs_health_update`: HTTP 409 asks the frontend for structured current
  health information; `plan_mode` is null.
- `requires_coach_review`: HTTP 409 pauses automatic revision; mode is
  `blocked`.

The safety prompt treats feedback as untrusted self-reported data, keeps a
reported health concern active, refuses to infer medical clearance from casual
free text, and uses the newest complete `HEALTH_UPDATE_V1` after a concern.

## 36. Structured health-update loop

When the frontend receives `needs_health_update`, `RegenerateSection` opens
`HealthUpdateDialog`. The runner supplies pain, warning symptoms, walking
response, professional clearance, cleared activities, and additional
restrictions.

`POST /recommendations/{id}/health-update` validates cross-field consistency,
then `build_health_update_feedback()` serializes the fields into a recognizable
`HEALTH_UPDATE_V1` text block and stores it as ordinary feedback. On success,
the frontend automatically requests revision again. The safety assessment now
sees the newer structured entry and either continues or requires coach review.

## 37. Building only the remaining plan

After safety allows revision, `build_remaining_plan_context()`:

1. deep-copies the selected plan so the stored original is not mutated;
2. parses every training date;
3. retains dates on or after today's revision date;
4. raises if no scheduled training remains;
5. retains only the corresponding weekly summaries;
6. recalculates remaining weekly distances; and
7. if feedback produced a requested start date, shifts all remaining training
   and week-boundary dates by the same delta.

The original week numbers remain. A date shift changes the ISO dates and weekday
labels, not the relative structure.

## 38. Revision generation and persistence

Normal revision uses `REMAINING_PLAN_FEEDBACK_PROMPT`. Adapted revision combines
`ADAPTED_REMAINING_PLAN_FEEDBACK_PROMPT_V1` with the selected mode's hard rules.
`build_feedback_revision_input()` supplies:

- historical `survey_snapshot`;
- selected plan title, summary, and safety notes;
- the safety contract;
- exact remaining weeks and training days; and
- feedback from oldest to newest.

`get_recommendation()` produces another `RunningPlanOutput`. The backend then:

1. sorts days and corrects weekly totals;
2. validates the safety mode;
3. verifies that returned training-date order exactly equals the required
   remaining-date order;
4. creates a new title such as `Original — Revised 1`;
5. inserts a new recommendation with the same survey and survey snapshot; and
6. leaves the original recommendation unchanged.

The prompt asks the model to preserve exact weekly boundary dates too, although
the explicit post-generation equality check currently compares training-day
dates only.

---

# Group 10 — Plans, favorites, ratings, and deletion

## 39. Recommendation read/write endpoints

- `GET /recommendations/`: all owned plans, newest first.
- `GET /recommendations/favorites`: only favorites, newest first.
- `GET /recommendations/survey/{survey_id}`: plans for an owned survey.
- `GET /recommendations/{id}`: one owned plan.
- `PATCH /recommendations/{id}/rating`: save an integer rating from 1 to 5.
- `PATCH /recommendations/{id}/favorite`: set the favorite boolean.
- `DELETE /recommendations/{id}`: physically delete the plan and its feedback.

The plan detail page renders the summary, weekly distance, training sessions,
why-it-fits explanation, safety notes, rating/favorite controls, feedback list,
and revision controls.

Favorite and rating hooks apply optimistic changes to the detail cache, roll
back on failure, and invalidate relevant queries afterward. Deletion removes the
detail cache and invalidates lists.

---

# Group 11 — Frontend architecture and user journeys

## 40. Provider and layout hierarchy

```text
RootLayout
  `-- AppProviders
       |-- QueryProvider (TanStack Query cache)
       `-- SessionProvider (GET /auth/me session state)
            `-- protected AppLayout
                 `-- AuthGuard
                      `-- AppShell
                           |-- sidebar + header + page
                           `-- CoachChatProvider + CoachChatWidget
```

`QueryProvider` allows up to two retries for ordinary queries, does not retry
not-found/validation failures, disables mutation retries, uses a 30-second
default stale time, and disables refetch-on-window-focus.

## 41. API and cache layers

The frontend follows one consistent path:

```text
component/page
  -> custom hook
  -> resource API wrapper
  -> apiClient
  -> FastAPI
```

- `lib/api/client.ts`: base URL, credentials, JSON, timeouts/abort conversion,
  HTTP error normalization, and unauthorized signaling.
- `lib/api/auth.ts`, `users.ts`, `surveys.ts`, `recommendations.ts`,
  `feedback.ts`, `chat.ts`: thin typed endpoint wrappers.
- `hooks/`: TanStack Query reads and mutations with cache updates.
- `lib/query-keys.ts`: shared keys so mutations invalidate the same data that
  pages read.
- `types/`: frontend representations of backend response/request schemas.
- `lib/validation/`: immediate form validation before backend validation.

Components do not call `fetch()` directly.

## 42. Complete primary runner journey

```text
Register or log in
  -> cookie session established
  -> SessionProvider caches current user
  -> dashboard
  -> create five-step survey
  -> backend validates and stores survey
  -> generate plan from latest survey
  -> backend safety gate + structured generation + validation
  -> plan detail page
  -> favorite/rate and add feedback
  -> request revision
       |-- safe -----------------------> new remaining-period plan
       |-- needs current health -------> health dialog -> retry revision
       `-- unsafe/unclear -------------> pause for coach review
  -> use global coach widget separately
       -> live context + memory + RAG -> answer
       -> end chat -> summarize memory for next session
```

## 43. Important frontend pages

- `/`: routes to dashboard or login after session restoration.
- `/dashboard`: combines current user, latest survey, recent recommendations,
  generation entry points, and a button to open chat.
- `/survey`: survey history.
- `/survey/new`: create survey, then generate; preserves the saved survey when
  generation fails so retry does not create another survey.
- `/survey/[id]`: view or soft-delete one survey.
- `/plans`: all recommendations and generation entry point.
- `/plans/[id]`: complete plan, feedback, revision, rating, favorite, deletion.
- `/favorites`: favorite recommendations.
- `/profile`: update profile and change password.
- Public auth pages: login, registration, forgot password, reset password.

---

# Group 12 — Endpoint and file map

## 44. Backend endpoint map

| Area | Endpoints | Main route file |
| --- | --- | --- |
| Auth | register, login, logout, me, password reset/change | `api/routes/auth.py` |
| User | get/update current profile | `api/routes/users.py` |
| Survey | schema, create, list, latest, get, soft-delete | `api/routes/surveys.py` |
| Plans | generate, list, favorites, get, rate, favorite, delete | `api/routes/recommendations.py` |
| Feedback | add/list, revise, health update | `api/routes/feedbacks.py` |
| Chat | message, end, history | `api/routes/chatbot.py` |

## 45. “Where should I look?” map

| Question | Start here |
| --- | --- |
| Why is a request unauthenticated? | `core/security.py`, `SessionProvider`, `api/client.ts` |
| Why was a survey rejected? | `schemas/survey.py`, frontend `validation/survey.ts` |
| Why was plan generation blocked? | `recommendation_generation_service.py`, `training_safety_prompt.py` |
| What did the plan model receive? | `running_plan_input.py`, `running_plan_prompt.py` |
| Why is a plan total wrong? | `running_plan_service.py` |
| Why did chat know a runner fact? | `coach_context_service.py`, `coach_memory`, `chatbot_input.py` |
| Why did chat miss club knowledge? | Group 1 and `knowledge_retrieval_service.py` |
| Why was revision paused? | `feedback_manager.py`, `feedback_safety_prompt.py` |
| Which dates can revision change? | `plan_revision_service.py`, `feedback_prompt.py` |
| Why is frontend data stale? | corresponding hook plus `query-keys.ts` |
| Where are model/provider calls? | `client_openai.py` |

## 46. System boundaries and known gaps

- RAG is used by chat only.
- Coach context and memory are used by chat only.
- New plan generation uses the newest active survey only.
- Plan revision uses feedback attached to one selected recommendation only.
- The application does not stream tokens or real generation progress.
- Retrieved knowledge sources are not returned to the frontend.
- Shoe recommendation types exist, but shoe generation is not implemented.
- Chat retrieval embeds only the latest message, so ambiguous follow-ups can
  retrieve poorly even when the transcript provides context.
- Survey soft deletion is not currently respected by `build_coach_context()`.
- RAG has no automated tests for parsing, chunking, indexing, retrieval, or
  prompt injection.

## 47. Debugging by workflow

For any failed flow, follow the same layers in order:

1. **UI state:** did the component call the expected mutation?
2. **Frontend validation:** did Zod or local component logic stop submission?
3. **API wrapper:** was the expected path/method/body used?
4. **Authentication:** was the cookie included and accepted?
5. **Backend request schema:** did Pydantic return 422?
6. **Route prerequisites/ownership:** did the route return 400/404/409?
7. **Prompt input:** was the intended current data actually included?
8. **OpenAI call:** which model/schema/prompt version was used?
9. **Deterministic validation:** did Python reject or adjust model output?
10. **Transaction:** was a commit reached?
11. **Frontend cache:** did the mutation update or invalidate the right key?

That sequence prevents debugging the model when the real problem is stale UI
state, a rejected request, missing prompt input, or an uncommitted database
change.
