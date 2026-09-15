from app.services.telemetry import traced

from app.client_openai import (
    get_recommendation,
    get_training_safety_assessment,
)
from app.prompts.running_plan_input import (
    build_running_plan_input,
    build_training_safety_input,
)
from app.prompts.running_plan_prompt import (
    get_running_plan_prompt,
)
from app.prompts.training_safety_prompt import (
    get_training_safety_prompt,
)
from app.services.running_plan_service import (
    synchronize_weekly_distances,
    validate_plan_mode,
)


@traced("assess_training_safety", kind="guardrail")
def assess_training_safety(
    survey,
    prompt_version="safety1",
):
    answers = survey.get("answers") or {}

    issue_areas = set(
        answers.get("current_issue_areas") or []
    )
    pain_level = answers.get("current_pain_level")

    if (
            pain_level == 0
            and issue_areas == {"none"}
    ):
        return {
            "plan_mode": "normal_running",
            "message": "No current pain or injury issue was reported.",
        }

    instructions = get_training_safety_prompt(
        prompt_version
    )
    input_text = build_training_safety_input(
        survey
    )

    return get_training_safety_assessment(
        input_text,
        instructions,
        prompt_version,
    )


PLAN_MODE_CLEARANCE = {
    "walk_only": "walk",
    "walk_run": "walk_run",
    "easy_running": "run",
}


@traced("validate_training_safety", kind="guardrail")
def validate_training_safety(
    survey,
    assessment,
):
    answers = survey.get("answers") or {}

    issue_areas = set(
        answers.get("current_issue_areas") or []
    )
    pain_level = answers.get("current_pain_level")
    cleared_activities = set(
        answers.get("medically_cleared_activities") or []
    )
    plan_mode = assessment["plan_mode"]

    has_health_concern = (
        pain_level is None
        or pain_level > 0
        or issue_areas != {"none"}
    )

    if plan_mode == "blocked":
        return assessment

    if pain_level is None:
        raise ValueError(
            "Current pain level is required for an injury-adapted plan."
        )

    if not has_health_concern:
        if plan_mode != "normal_running":
            raise ValueError(
                "A healthy survey must use normal_running."
            )

        return assessment

    if plan_mode == "normal_running":
        raise ValueError(
            "normal_running cannot be used when pain or an issue is reported."
        )

    if not cleared_activities or "not_cleared" in cleared_activities:
        raise ValueError(
            "An injury-adapted plan requires reported medical clearance."
        )

    required_clearance = PLAN_MODE_CLEARANCE.get(
        plan_mode
    )

    if required_clearance not in cleared_activities:
        raise ValueError(
            f"{plan_mode} requires {required_clearance} clearance."
        )

    if pain_level > 3 and plan_mode != "walk_only":
        raise ValueError(
            "Pain above 3 only permits walk_only or blocked."
        )

    return assessment


class TrainingBlockedError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@traced("running_plan_generation")
def generate_recommendation(
    user_id,
    user,
    survey,
):
    safety_assessment = assess_training_safety(survey)
    safety_assessment = validate_training_safety(survey, safety_assessment)

    plan_mode = safety_assessment["plan_mode"]

    if plan_mode == "blocked":
        raise TrainingBlockedError(
            safety_assessment["message"]
        )

    prompt_version, instructions = get_running_plan_prompt(
        plan_mode
    )

    input_text = build_running_plan_input(
        user,
        survey,
        plan_mode,
    )

    recommendation = get_recommendation(
        input_text,
        instructions,
        prompt_version,
        plan_mode=plan_mode,
    )

    recommendation = synchronize_weekly_distances(
        recommendation
    )

    cleared_activities = (
        (survey.get("answers") or {}).get("medically_cleared_activities")
        or []
    )

    return validate_plan_mode(
        recommendation,
        plan_mode,
        cleared_activities,
    )
