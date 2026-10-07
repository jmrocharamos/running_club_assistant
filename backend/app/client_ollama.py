"""Ollama API calls. Provider selection belongs to the calling services."""

import json
import math
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import (
    OLLAMA_BASE_URL,
    OLLAMA_EMBEDDING_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    ENVIRONMENT,
    OLLAMA_MODEL,
    OLLAMA_GENERATION_TIMEOUT_SECONDS,
    OLLAMA_CONTEXT_LENGTH,
    OLLAMA_MAX_OUTPUT_TOKENS,
)
from app.schemas.running_structured_outputs import ChatReplyOutput, ChatSummaryOutput, RunningPlanOutput
from app.schemas.training_safety import TrainingSafetyAssessment
from app.schemas.feedback_revision import FeedbackSafetyAssessment
from app.services.telemetry import safe_update, trace_step


def create_embeddings(texts: list[str]) -> list[list[float]]:
    """Return one finite, consistently sized vector per input, without truncation.

    Raise HTTP errors for server failures and ValueError for malformed vectors.
    Database-specific dimension checks belong to the embedding service.
    """
    if not texts:
        return []

    with trace_step(
        "create_embeddings",
        kind="embedding",
        model=OLLAMA_EMBEDDING_MODEL,
        metadata={"text_count": len(texts)},
    ) as observation:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={
                "model": OLLAMA_EMBEDDING_MODEL,
                "input": texts,
                "truncate": False,
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise ValueError("Ollama embedding count does not match input count.")

        dimensions = None
        for vector in embeddings:
            if not isinstance(vector, list) or not vector:
                raise ValueError("Ollama returned an empty or invalid embedding.")
            if dimensions is None:
                dimensions = len(vector)
            if len(vector) != dimensions or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            ):
                raise ValueError("Ollama returned inconsistent or non-finite embeddings.")

        tokens = payload.get("prompt_eval_count")
        if isinstance(tokens, int) and tokens >= 0:
            safe_update(observation, usage_details={"input": tokens})

        return embeddings


def _generate(
    input_text: str,
    instructions: str,
    prompt_version: str,
    output_schema: type[BaseModel],
    feature: str,
    *,
    plan_mode: str | None = None,
) -> dict[str, Any]:
    """Request schema-constrained JSON; reject incomplete or invalid output.

    Raw inputs, outputs, and thinking text are never attached to telemetry.
    Domain validation remains the responsibility of the existing services.
    """
    schema = output_schema.model_json_schema()
    metadata = {"environment": ENVIRONMENT, "provider": "ollama"}
    if plan_mode is not None:
        metadata["plan_mode"] = plan_mode
    with trace_step(
        feature, kind="generation", model=OLLAMA_MODEL,
        version=prompt_version, metadata=metadata,
    ) as observation:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": (
                        instructions + "\n\nReturn only JSON matching this schema:\n"
                        + json.dumps(schema)
                    )},
                    {"role": "user", "content": input_text},
                ],
                "format": schema,
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0,
                    "num_ctx": OLLAMA_CONTEXT_LENGTH,
                    "num_predict": OLLAMA_MAX_OUTPUT_TOKENS,
                },
            },
            timeout=OLLAMA_GENERATION_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("done") is not True:
            raise ValueError("Ollama returned an incomplete generation.")
        if payload.get("done_reason") != "stop":
            raise ValueError("Ollama generation did not finish normally; check output limits.")
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned no structured output.")

        usage = {}
        for field, label in (("prompt_eval_count", "input"), ("eval_count", "output")):
            count = payload.get(field)
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                usage[label] = count
        if usage:
            safe_update(observation, usage_details=usage)
        return output_schema.model_validate_json(content).model_dump()


def get_chat_reply(input_text: str, instructions: str, prompt_version: str) -> dict[str, Any]:
    return _generate(input_text, instructions, prompt_version, ChatReplyOutput, "chatbot")


def summarize_conversation(input_text: str, instructions: str, prompt_version: str) -> dict[str, Any]:
    return _generate(input_text, instructions, prompt_version, ChatSummaryOutput, "coach_memory_summary")


def get_training_safety_assessment(input_text: str, instructions: str, prompt_version: str) -> dict[str, Any]:
    return _generate(input_text, instructions, prompt_version, TrainingSafetyAssessment, "training_safety")


def get_feedback_safety_assessment(input_text: str, instructions: str, prompt_version: str) -> dict[str, Any]:
    return _generate(input_text, instructions, prompt_version, FeedbackSafetyAssessment, "feedback_safety")


def get_recommendation(
    input_text: str, instructions: str, prompt_version: str,
    plan_mode: str | None = None,
) -> dict[str, Any]:
    return _generate(
        input_text, instructions, prompt_version, RunningPlanOutput,
        "running_plan", plan_mode=plan_mode,
    )
