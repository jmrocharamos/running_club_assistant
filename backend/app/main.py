from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
from app.services.telemetry import shutdown_telemetry
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, users, surveys, recommendations, chatbot, feedbacks




@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await run_in_threadpool(shutdown_telemetry)


app = FastAPI(title="Running AI App", lifespan=lifespan)

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

# uvicorn app.main:app --reload --port 5002