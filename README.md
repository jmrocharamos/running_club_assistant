# Running Club Assistant

An AI-assisted running coach with personalized training plans, feedback-driven
revisions, and a conversational coach grounded in club knowledge. Built with
Next.js, FastAPI, PostgreSQL, and OpenAI, with Langfuse tracing for AI workflows.

**[Open the app](https://running-club-assistant.vercel.app)** ·
**[API documentation](https://running-club-assistant-api.onrender.com/docs)**

## What you can do

- Create an account and complete a running survey with goals, availability,
  experience, equipment, and health constraints.
- Generate a training plan with running or walking, strength, and mobility.
- Submit feedback and revise the remaining plan. Safety checks can request a
  health update or pause generation for coach review.
- Browse saved plans, mark favorites, and give plans a 1–5 rating.
- Chat with a coach using survey and plan context, conversation memory, and
  relevant club documents retrieved through vector search.
- Manage your profile and review survey history.

## Architecture

```mermaid
flowchart LR
    Browser[Runner's browser] --> Frontend[Next.js frontend · Vercel]
    Frontend -->|/api forwarding| Backend[FastAPI backend · Render]
    Backend --> DB[(PostgreSQL + pgvector · Render)]
    Backend --> OpenAI[OpenAI · generation and embeddings]
    Backend --> Langfuse[Langfuse · traces, usage and ratings]
```

The browser calls `/api` on the frontend domain. Next.js forwards those requests
to FastAPI, keeping authentication cookies on the frontend domain. FastAPI
validates the JWT cookie and resource ownership on protected endpoints.

Locally, PostgreSQL runs in Docker; the backend and frontend run directly on your
machine. The local Compose file does not deploy the application servers.

| Component | Technology |
| --- | --- |
| Frontend | Next.js 16, React, TypeScript, Tailwind CSS, shadcn/ui |
| Forms and server state | React Hook Form, Zod, TanStack Query |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Database and retrieval | PostgreSQL, pgvector, LangChain text splitting |
| AI | OpenAI structured responses and embeddings |
| Observability | Langfuse workflow traces, tags, token usage, and plan-rating scores |

## Run locally

### Prerequisites

- Python 3.12 (the local development version)
- Node.js 22 LTS and npm
- Docker with Docker Compose
- An OpenAI API key for generation, chat, and embedding calls
- A Langfuse project if you want tracing (optional)

### 1. Set up the backend

```bash
git clone https://github.com/jmrocharamos/running_club_assistant.git
cd running_club_assistant/backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` before continuing:

| Variable | Local configuration |
| --- | --- |
| `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` | Credentials used by the local Docker database |
| `DATABASE_URL` | `postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DATABASE` |
| `OPENAI_API_KEY` | Your API key; kept on the backend |
| `JWT_SECRET_KEY` | A randomly generated secret |
| `ENVIRONMENT` | `development` for local HTTP |
| `FRONTEND_BASE_URL` | `http://localhost:3000` |
| `LANGFUSE_TRACING_ENABLED` | Set to `false` to work without Langfuse |

Use matching database credentials in the `POSTGRES_*` variables and
`DATABASE_URL`. The `postgresql+psycopg://` prefix selects the installed Psycopg 3
driver. URL-encode special characters in connection-string credentials.

Generate a JWT secret locally:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(64))'
```

Keep real credentials in ignored environment files or hosting-platform secrets;
never commit them. [Langfuse setup](docs/LANGFUSE.md) explains its optional keys.

### 2. Start the database and API

From `backend`, with the virtual environment active:

```bash
docker compose up -d --wait
alembic upgrade head
alembic current
uvicorn app.main:app --reload --port 5002
```

The API runs at `http://localhost:5002`; interactive documentation is at
`http://localhost:5002/docs`. Alembic creates the schema and enables pgvector.
Migrations do not create users or populate the knowledge base.

### 3. Start the frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

The example uses `NEXT_PUBLIC_API_BASE_URL=/api` and
`API_BACKEND_URL=http://localhost:5002`. Open `http://localhost:3000`, register an
account, and complete a survey. Sign in with your email address, not username.

### 4. Populate club knowledge

From `backend`, with the virtual environment active:

```bash
python -m scripts.sync_knowledge_base
python -m scripts.index_knowledge_base
```

The first command synchronizes documents from `backend/knowledge_docs`. The
second rebuilds the knowledge chunks and embeddings, replacing existing chunks
in a transaction. It calls the OpenAI embeddings API and incurs usage charges.
Run indexing when setting up a new database or updating the source documents,
not on every server startup.

## Tests and checks

Backend tests use a separate local database named `running_club_test`. Create it
once using the configured local database user (the command below uses the example
username):

```bash
cd backend
docker compose exec db createdb -U running_club running_club_test
docker compose exec db psql -U running_club -d running_club_test -c 'CREATE EXTENSION IF NOT EXISTS vector;'
.venv/bin/pytest -q
```

If the test database already exists, skip `createdb`. Keep `backend/.env` pointed
at your local database when running tests: fixtures derive the test connection
from it and create, truncate, and drop application tables in `running_club_test`.
The automated suite mocks AI calls and disables external Langfuse export; the SDK
test uses an in-memory exporter.

Frontend checks, from the repository root:

```bash
cd frontend
npm test
npm run lint
npx tsc --noEmit
npm run build
```

See [frontend reliability checks](frontend/tests/README.md) and
[Langfuse verification](docs/LANGFUSE.md#verification) for manual checks.

## Deployment

### FastAPI and PostgreSQL on Render

The backend uses Render's native Python runtime, with managed PostgreSQL and
pgvector in the same region. No application Dockerfile is required.

| Setting | Value |
| --- | --- |
| Root directory | `backend` |
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health-check path | `/` (application liveness only) |

Set `DATABASE_URL` to Render's **internal** database URL, using the
`postgresql+psycopg://` prefix. Configure `OPENAI_API_KEY`, a production
`JWT_SECRET_KEY`, `ENVIRONMENT=production`, and
`FRONTEND_BASE_URL=https://running-club-assistant.vercel.app`. Add the Langfuse
project settings to enable production traces. Keep secrets on Render.

**Apply migrations before starting code that depends on a changed schema.**
The Uvicorn start command above does not run Alembic. Where a pre-deploy command
is available, use `alembic upgrade head`. Otherwise, apply migrations manually
against the production database before deploying the new backend. For local
migration commands, use Render's external database connection with TLS; its
internal hostname is for services on Render's private network.

Use backward-compatible migrations when old and new versions overlap during a
deploy. Deploying code without its required migration can break plan queries.
See [Render's FastAPI guide](https://render.com/docs/deploy-fastapi) and
[deployment commands](https://render.com/docs/deploys#pre-deploy-command).

### Next.js on Vercel

Import the repository, choose **Next.js**, and set the root directory to
`frontend`. Configure these variables before building:

```dotenv
NEXT_PUBLIC_API_BASE_URL=/api
API_BACKEND_URL=https://running-club-assistant-api.onrender.com
```

Do not put API keys or database credentials in `NEXT_PUBLIC_*` variables. Rebuild
after changing the API URL configuration. The [frontend guide](frontend/README.md#vercel-deployment)
explains forwarding and login verification.

Local and production databases are separate. Deploying code or running migrations
does not copy accounts, plans, or embeddings between them.

## Observability

Langfuse groups model calls and service steps into workflow traces. Trace tags
include `new-plan`, `revised-plan`, `coach-chat`, `memory-summary`, and
`correction-retry`. Generation traces record model, prompt version, and token
usage; Langfuse can infer cost from its model pricing definitions.

New plans store an internal trace reference so a user's 1–5 rating can be attached
as a `plan_rating` score. This is user feedback, not an automated quality or
safety assessment. Application instrumentation excludes raw prompts, responses,
health details, passwords, and tokens. Telemetry failures do not block app flows.
See [Langfuse configuration and limitations](docs/LANGFUSE.md).

## Repository map

```text
backend/
  app/api/routes/       HTTP endpoints and authentication dependencies
  app/models/           SQLAlchemy database models
  app/schemas/          Request, response, and AI-output schemas
  app/prompts/          Generation, revision, safety, and chat prompts
  app/services/         Coaching, retrieval, validation, and telemetry
  alembic/              Database migrations
  knowledge_docs/       Club and training knowledge sources
  scripts/              Document synchronization and embedding indexing
  tests/                Backend regression tests
  compose.yaml          Local PostgreSQL + pgvector
frontend/
  src/app/              Pages and layouts
  src/components/       UI, survey, plan, and chat components
  src/hooks/            Queries and mutations
  src/lib/api/          API client and resource wrappers
  tests/                Frontend regression tests
docs/
  SYSTEM_FLOW_NOTES.md   AI flow and retrieval notes
  LANGFUSE.md            Observability setup and verification
```

## Current limitations

- Password-reset requests use a console email sender. No email provider is wired
  up, so reset links are logged rather than delivered to an inbox.
- Plan generation and revision run within HTTP requests. A request can time out
  while the backend continues generating; check saved plans before retrying.
- A coach-review safety response pauses the flow; it is not an integrated human
  review queue.
- Langfuse export is best effort, without a durable retry queue. Older plans
  without trace references cannot receive linked scores retroactively.
