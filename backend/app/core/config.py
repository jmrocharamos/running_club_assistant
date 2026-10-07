import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BASE_DIR / ".env")

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT == "production"

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))  # 7 days

AUTH_COOKIE_NAME = "access_token"
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "30")
)

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower()

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_GENERATION_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_GENERATION_TIMEOUT_SECONDS", "300"))
OLLAMA_CONTEXT_LENGTH = int(os.getenv("OLLAMA_CONTEXT_LENGTH", "32768"))
OLLAMA_MAX_OUTPUT_TOKENS = int(os.getenv("OLLAMA_MAX_OUTPUT_TOKENS", "16384"))

if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY is not set in the .env file")
