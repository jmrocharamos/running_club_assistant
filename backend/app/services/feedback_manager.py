from app.services.telemetry import traced
from app.client_openai import get_feedback_safety_assessment
from app.prompts.feedback_safety_prompt import get_feedback_safety_prompt
from app.prompts.feedback_safety_input import build_feedback_safety_input


@traced("assess_feedback_safety", kind="guardrail")
def assess_feedback_safety(
        recommendation,
        feedback_entries,
        prompt_version="safety4",
):
    instructions = get_feedback_safety_prompt(
        prompt_version,
    )

    input_text = build_feedback_safety_input(
        recommendation,
        feedback_entries,
    )

    return get_feedback_safety_assessment(
        input_text,
        instructions,
        prompt_version,
    )
