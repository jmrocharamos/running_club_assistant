import json
from app.services.plan_calendar_service import build_plan_calendar


def build_training_safety_input(survey):
    answers = survey.get("answers") or {}

    return json.dumps(
        {
            "current_issue_areas": (
                answers.get("current_issue_areas") or []
            ),
            "current_pain_level": answers.get(
                "current_pain_level"
            ),
            "medically_cleared_activities": answers.get(
                "medically_cleared_activities"
            ),
        },
        ensure_ascii=False,
    )


def build_running_plan_input(user, survey, plan_mode):
    answers = survey['answers']

    preferred_days = ", ".join(
        answers.get("preferred_training_days", [])
    )

    plan_start_date = (
        answers.get("plan_start_date")
        or str(survey.get('created_at', ''))[:10]
    )

    equipment = ", ".join(
        answers.get("available_equipment", [])
    )

    issue_areas = ", ".join(
        answers.get("current_issue_areas", [])
    )

    cleared_activities = ", ".join(
        answers.get("medically_cleared_activities") or []
    ) or "not provided"

    calendar = build_plan_calendar(
        plan_start_date, answers["plan_duration_weeks"],
        answers["preferred_training_days"],
        answers.get("target_event_date") if plan_mode == "normal_running" else None,
    )

    long_run_day = (
        answers.get("preferred_long_run_day") or "none (no dedicated long run)"
    )

    return f"""
    REQUIRED PLAN MODE: {plan_mode}

    The following user completed a running plan survey.

    USER INFORMATION

    Name: {user.get("full_name")}
    Age: {user.get("age")}
    Weight: {answers.get("weight_kg")} kg

    RUNNING SURVEY

    Main goal: {answers.get("goal")}
    Target distance: {answers.get("target_distance")}
    Experience level: {answers.get("experience_level")}
    Plan duration: {answers.get("plan_duration_weeks")} weeks
    Plan start date: {plan_start_date}
    Target event date: {answers.get("target_event_date")}

    Current weekly distance: {answers.get("current_weekly_distance_km")} km
    Runs per week: {answers.get("runs_per_week")}
    Longest recent run: {answers.get("longest_recent_run_km")} km

    Preferred training days: {preferred_days}
    Preferred long-run day: {long_run_day}
    Maximum session duration: {answers.get("max_session_minutes")} minutes
    Preferred terrain: {answers.get("preferred_terrain")}
    Available equipment: {equipment}

    Current issue areas: {issue_areas}
    Current pain level: {answers.get("current_pain_level")}/10
    Medically cleared activities: {cleared_activities}

    Recovery level: {answers.get("recovery_level")}
    Average sleep duration: {answers.get("average_sleep_duration")}
    Stress level: {answers.get("stress_level")}

    Main preference: {answers.get("main_preference")}
    Recommendation detail level: {answers.get("detail_level")}

    AUTHORITATIVE CALENDAR

    {json.dumps(calendar)}

    Copy the weekly boundaries and week numbers exactly. Schedule sessions only
    on available_training_days from this calendar, using its dates and lowercase
    weekday labels. An adapted plan may use fewer available days, but must never
    add another weekday or date. Include all numbered weeks even when some
    available days have no session.

    Create a safe and personalized running plan using the user information
    and survey answers above.

    Do not invent information that was not provided.
    Respect the preferred training days, current running level, weekly distance,
    pain level, available equipment, and plan duration.
    """.strip()
