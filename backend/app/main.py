from contextlib import asynccontextmanager
import asyncio
from contextlib import suppress
import logging
import jwt
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from app.services.telemetry import shutdown_telemetry
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, users, surveys, recommendations, chatbot, feedbacks, demo
from app.core.config import AUTH_COOKIE_NAME, JWT_SECRET_KEY, JWT_ALGORITHM
from app.core.request_context import demo_deadline
from app.services import demo_session_service as demos
from app.db.session import SessionLocal




async def purge_demo_data():
    while True:
        try:
            def purge():
                with SessionLocal() as db:
                    demos.cleanup(db)
            await run_in_threadpool(purge)
        except Exception:
            # Cleanup can retry after temporary database downtime. Never log
            # connection strings or demo content.
            logging.getLogger(__name__).warning("Demo cleanup will retry")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(purge_demo_data()) if demos.DEMO_ENABLED else None
    try:
        yield
    finally:
        if cleanup_task:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
        await run_in_threadpool(shutdown_telemetry)


app = FastAPI(title="Running AI App", lifespan=lifespan)


@app.middleware("http")
async def demo_request_deadline(request, call_next):
    deadline = None
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token and request.url.path not in {"/demo/start", "/demo/config", "/auth/login", "/auth/register", "/auth/forgot-password", "/auth/reset-password"}:
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
            if payload.get("kind") == "demo":
                deadline = float(payload["exp"])
        except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
            pass
    context = demo_deadline.set(deadline)
    try:
        response = await call_next(request)
        if deadline is not None and demos.now().timestamp() >= deadline and request.url.path not in {"/demo/start", "/demo/config", "/auth/login", "/auth/register"}:
            return JSONResponse({"detail": {"reason": "demo_expired", "message": "Your 15-minute demo has ended."}}, status_code=401)
        return response
    finally:
        demo_deadline.reset(context)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Running AI app is working"}

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(surveys.router)
app.include_router(recommendations.router)
app.include_router(chatbot.router)
app.include_router(feedbacks.router)
app.include_router(demo.router)

# uvicorn app.main:app --reload --port 5002
