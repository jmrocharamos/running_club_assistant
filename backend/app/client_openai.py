from typing import Any
from dotenv import load_dotenv
from openai import OpenAI
from app.services.telemetry import trace_step, safe_update
from app.core.config import ENVIRONMENT
from app.schemas.feedback_revision import FeedbackSafetyAssessment
from app.schemas.running_structured_outputs import RunningPlanOutput, ChatReplyOutput, ChatSummaryOutput
from app.schemas.training_safety import TrainingSafetyAssessment

load_dotenv()

client = OpenAI()


def get_training_safety_assessment(
    input_text: str,
    instructions: str,
    prompt_version: str,
) -> dict[str, Any]:
    response = _parse_response(
        model="gpt-5-mini",
        reasoning={"effort":"minimal"},
        instructions=instructions,
        input=input_text,
        text_format=TrainingSafetyAssessment,
        metadata={
            "feature": "training_safety",
            "environment": ENVIRONMENT,
            "prompt_version": prompt_version,
        },
    )

    assessment = response.output_parsed

    if assessment is None:
        raise ValueError(
            "OpenAI returned no training safety assessment."
        )

    return assessment.model_dump()


def get_recommendation(
        input_text: str,
        instructions: str,
        prompt_version: str,
        plan_mode: str | None = None,
) -> dict[str, Any]:
    metadata = {
        "feature": "running_plan",
        "environment": ENVIRONMENT,
        "prompt_version": prompt_version,
    }

    if plan_mode is not None:
        metadata["plan_mode"] = plan_mode

    response = _parse_response(
        model="gpt-5-mini",
        instructions=instructions,
        input=input_text,
        text_format=RunningPlanOutput,
        metadata=metadata,
    )

    structured_output = response.output_parsed

    if structured_output is None:
        raise ValueError(
            "OpenAI returned no structured running plan output."
        )

    return structured_output.model_dump()


def get_feedback_safety_assessment(
        input_text: str,
        instructions: str,
        prompt_version: str,
) -> dict[str, Any]:
    response = _parse_response(
        model="gpt-5-mini",
        reasoning={"effort":"minimal"},
        instructions=instructions,
        input=input_text,
        text_format=FeedbackSafetyAssessment,
        metadata={
            "feature": "feedback_safety",
            "environment": ENVIRONMENT,
            "prompt_version": prompt_version,
        },
    )

    assessment = response.output_parsed

    if assessment is None:
        raise ValueError(
            "OpenAI returned no feedback safety assessment."
        )

    return assessment.model_dump()


def get_chat_reply(input_text: str, instructions: str, prompt_version: str) -> dict[str, Any]:
    response = _parse_response(
        model="gpt-5-mini",
        instructions=instructions,
        input=input_text,
        text_format=ChatReplyOutput,
        metadata={
            "feature": "chatbot",
            "environment": ENVIRONMENT,
            "prompt_version": prompt_version,
        },
    )

    structured_output = response.output_parsed

    if structured_output is None:
        raise ValueError(
            "OpenAI returned no structured chat reply output."
        )

    return structured_output.model_dump()


def summarize_conversation(input_text: str, instructions: str, prompt_version: str) -> dict[str, Any]:
    response = _parse_response(
        model="gpt-4o-mini",
        instructions=instructions,
        input=input_text,
        text_format=ChatSummaryOutput,
        metadata={
            "feature": "coach_memory_summary",
            "environment": ENVIRONMENT,
            "prompt_version": prompt_version,
        },
    )

    structured_output = response.output_parsed

    if structured_output is None:
        raise ValueError(
            "OpenAI returned no structured chat summary output."
        )

    return structured_output.model_dump()


def create_embeddings(texts: list[str]) -> list[list[float]]:
    response = _embed(
        model="text-embedding-3-small",
        input=texts,
    )

    return [item.embedding for item in response.data]



def _parse_response(**kwargs):
    metadata = kwargs.get("metadata", {})
    with trace_step(
        metadata.get("feature", "openai_response"), kind="generation",
        model=kwargs["model"], version=metadata.get("prompt_version"),
        metadata={"environment": ENVIRONMENT},
    ) as observation:
        response = client.responses.parse(**kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
            reasoning = getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0
            safe_update(observation, usage_details={
                "input": usage.input_tokens - cached,
                "input_cached_tokens": cached,
                "output": usage.output_tokens - reasoning,
                "output_reasoning_tokens": reasoning,
            })
        if response.output_parsed is None:
            safe_update(observation, level="ERROR", status_message="MissingStructuredOutput")
        return response


def _embed(**kwargs):
    with trace_step("create_embeddings", kind="embedding", model=kwargs["model"],
                    metadata={"text_count": len(kwargs["input"])}) as observation:
        response = client.embeddings.create(**kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            safe_update(observation, usage_details={"input": usage.prompt_tokens})
        return response
