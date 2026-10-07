"""Compute allowed initial-plan dates and reject model schedule deviations."""

from datetime import date, timedelta


def build_plan_calendar(start_date, weeks, preferred_days, event_date=None):
    start = date.fromisoformat(str(start_date))
    calendar = []
    for number in range(1, weeks + 1):
        end = start + timedelta(days=6 - start.weekday())
        available = []
        current = start
        while current <= end:
            weekday = current.strftime("%A").lower()
            if weekday in preferred_days or current.isoformat() == str(event_date):
                available.append({"date": current.isoformat(), "day": weekday})
            current += timedelta(days=1)
        calendar.append({"week_number": number, "start_date": start.isoformat(),
                         "end_date": end.isoformat(), "available_training_days": available})
        start = end + timedelta(days=1)
    return calendar


def validate_plan_calendar(recommendation, survey, plan_mode):
    answers = survey["answers"]
    start = answers.get("plan_start_date") or str(survey.get("created_at", ""))[:10]
    calendar = build_plan_calendar(
        start, answers["plan_duration_weeks"], answers["preferred_training_days"],
        answers.get("target_event_date") if plan_mode == "normal_running" else None,
    )
    content = recommendation["content"]
    weeks = content["weekly_distance"]
    if len(weeks) != len(calendar):
        raise ValueError("The plan must contain exactly the requested number of weeks.")
    for expected, actual in zip(calendar, weeks):
        for key in ("week_number", "start_date", "end_date"):
            if actual[key] != expected[key]:
                raise ValueError("The plan changed the required weekly calendar.")
    allowed = {day["date"]: (week["week_number"], day["day"])
               for week in calendar for day in week["available_training_days"]}
    days = content["training_days"]
    if not days:
        raise ValueError("The plan must contain at least one training session.")
    seen = set()
    for day in days:
        if day["date"] in seen:
            raise ValueError("The plan contains duplicate training dates.")
        seen.add(day["date"])
        if allowed.get(day["date"]) != (day["week_number"], day["day"]):
            raise ValueError(
                f"Session {day['date']} does not match the allowed training dates and week numbers."
            )
    return recommendation
