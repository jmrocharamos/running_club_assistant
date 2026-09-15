import os
import re
from pathlib import Path

from dotenv import dotenv_values

# Tests must never export traces to a real Langfuse project.
os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

BASE_DIR = Path(__file__).resolve().parents[1]
_env_values = dotenv_values(BASE_DIR / ".env")
_real_database_url = _env_values.get("DATABASE_URL") or os.environ["DATABASE_URL"]
_test_database_url = re.sub(r"/[^/]+$", "/running_club_test", _real_database_url)

# Must happen before any `app.*` module is imported, since app/db/session.py
# and app/core/config.py read these at import time.
os.environ["DATABASE_URL"] = _test_database_url
os.environ.setdefault("JWT_SECRET_KEY", _env_values.get("JWT_SECRET_KEY", "test-secret-key"))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("FRONTEND_BASE_URL", "http://localhost:3000")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402,F401  registers every model on Base
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_db():
    with SessionLocal() as session:
        session.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        session.execute(text("TRUNCATE TABLE knowledge_base RESTART IDENTITY CASCADE"))
        session.commit()
    yield


@pytest.fixture
def client():
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture
def second_client():
    """A separate cookie jar, simulating a second browser session/user."""
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session
