# Running Club Assistant

FastAPI backend for an AI-assisted running club. The application stores users,
surveys, running recommendations, feedback, coach memory, and club knowledge.
PostgreSQL with pgvector runs in Docker, while FastAPI runs locally through the
project virtual environment.

A Next.js frontend lives in [`frontend/`](frontend/) — see
[`frontend/README.md`](frontend/README.md) for its setup and architecture.

For a code-level map of the AI flows, start with
[`docs/SYSTEM_FLOW_NOTES.md`](docs/SYSTEM_FLOW_NOTES.md). It currently contains
the deep RAG walkthrough and the study roadmap for coach context, memory, chat,
and plan generation.

Langfuse configuration and testing: [`docs/LANGFUSE.md`](docs/LANGFUSE.md).

## Features

- Cookie-based authentication and user-owned API routes
- Survey history with soft deletion
- Running-plan and feedback workflows
- Conversational running-coach endpoint with per-user memory
- SQLAlchemy database models and sessions
- Alembic database migrations
- PostgreSQL knowledge chunks with pgvector embeddings
- Pydantic schemas for request and response validation
- OpenAI integration for AI-generated running guidance
- Structured service layer for recommendation and feedback logic
- Environment-based configuration with `.env`

## Tech Stack

Python 3.12 · FastAPI · SQLAlchemy · Alembic · Pydantic · PostgreSQL ·
pgvector · Docker Compose · OpenAI API · Langfuse · Uvicorn

## Local Architecture

```text
FastAPI and Alembic (local Python environment)
                    |
                    | 127.0.0.1:5432
                    v
PostgreSQL 16 + pgvector (Docker container)
```

Only the database is containerized. The FastAPI application runs locally.

## Project Structure

```text
backend/
├── alembic/                # database migrations
├── app/
│   ├── api/routes/          # API endpoints
│   ├── db/                  # database setup and sessions
│   ├── models/              # SQLAlchemy models
│   ├── prompts/             # AI prompt inputs and templates
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # application logic
│   └── main.py              # FastAPI application entry point
├── compose.yaml             # PostgreSQL and pgvector container
├── .env.example             # safe environment-variable template
├── alembic.ini
└── requirements.txt

frontend/
├── src/
│   ├── app/                 # Next.js App Router pages
│   ├── components/          # UI components (app shell, survey, plans, chat...)
│   ├── hooks/                # TanStack Query hooks per resource
│   ├── lib/                  # API client, validation schemas, utilities
│   └── types/                 # TypeScript types mirroring backend schemas
├── .env.example
└── package.json
```

## Getting Started

Clone the repository and enter the backend directory:

```bash
git clone https://github.com/NothinginVain/running_club_assistant.git
cd running_club_assistant/backend
```

Create and activate a Python 3.12 virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create the local environment file:

```bash
cp .env.example .env
```

Replace every `CHANGE_ME` value in `.env`. Use the same generated database
password in `POSTGRES_PASSWORD` and `DATABASE_URL`. Never commit the real
`.env` file.

Start PostgreSQL with pgvector:

```bash
docker compose pull
docker compose up -d --wait
docker compose ps
```

Apply all database migrations from the local virtual environment:

```bash
alembic upgrade head
alembic current
```

Confirm that Alembic reports the latest migration from this checkout as the
current head. Migration identifiers change as the project evolves, so the
repository should not document a fixed revision identifier here.

Run the application:

```bash
uvicorn app.main:app --reload --port 5002
```

The API will be available at:

```text
http://127.0.0.1:5002
```

Interactive API documentation is available at:

```text
http://127.0.0.1:5002/docs
```

## Database Verification

List the database tables:

```bash
docker compose exec db \
  psql -U running_club -d running_club \
  -c "\dt public.*"
```

Verify pgvector:

```bash
docker compose exec db \
  psql -U running_club -d running_club \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

Stop the database without deleting its persistent volume:

```bash
docker compose stop
```

## What This Project Demonstrates

- Backend API design with FastAPI
- Database modeling with SQLAlchemy
- Reproducible schema evolution with Alembic
- Local containerized PostgreSQL development
- Input validation with Pydantic
- Layered project structure
- AI API integration
- Structured chatbot memory
- Semantic retrieval with LangChain, OpenAI embeddings, and pgvector
- Handling user feedback and recommendation data

## Future Improvements

- Expand automated coverage for AI and retrieval workflows
- Add production email delivery for password resets
- Expand recommendation history and analytics
