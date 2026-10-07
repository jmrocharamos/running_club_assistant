"""Stable generation interface with independently configurable AI provider."""

from importlib import import_module

from app.core.config import AI_PROVIDER
from app.schemas.running_structured_outputs import ChatReplyOutput, ChatSummaryOutput, RunningPlanOutput
from app.schemas.training_safety import TrainingSafetyAssessment
from app.schemas.feedback_revision import FeedbackSafetyAssessment


def _client():
    if AI_PROVIDER not in {"openai", "ollama"}:
        raise ValueError(f"Unsupported AI provider: {AI_PROVIDER}")
    # Local inference never initializes the OpenAI client or requires its key.
    return import_module(f"app.client_{AI_PROVIDER}")


def get_chat_reply(input_text: str, instructions: str, prompt_version: str) -> dict:
    result = _client().get_chat_reply(input_text, instructions, prompt_version)
    return ChatReplyOutput.model_validate(result).model_dump()


def summarize_conversation(input_text: str, instructions: str, prompt_version: str) -> dict:
    result = _client().summarize_conversation(input_text, instructions, prompt_version)
    return ChatSummaryOutput.model_validate(result).model_dump()


def get_training_safety_assessment(input_text: str, instructions: str, prompt_version: str) -> dict:
    result = _client().get_training_safety_assessment(input_text, instructions, prompt_version)
    return TrainingSafetyAssessment.model_validate(result).model_dump()


def get_feedback_safety_assessment(input_text: str, instructions: str, prompt_version: str) -> dict:
    result = _client().get_feedback_safety_assessment(input_text, instructions, prompt_version)
    return FeedbackSafetyAssessment.model_validate(result).model_dump()


def get_recommendation(
    input_text: str, instructions: str, prompt_version: str,
    plan_mode: str | None = None,
) -> dict:
    result = _client().get_recommendation(
        input_text, instructions, prompt_version, plan_mode=plan_mode,
    )
    return RunningPlanOutput.model_validate(result).model_dump()
