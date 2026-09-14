from datetime import date


def calculate_weekly_distance_totals(
        training_days: list[dict],
) -> dict[int, float]:
    totals_by_week = {}

    for training_day in training_days:
        running = training_day.get("running")
        walking = training_day.get("walking")

        distance_km = 0.0

        if running is not None:
            distance_km += running["distance_km"]

        if walking is not None:
            distance_km += walking["distance_km"]

        if distance_km == 0:
            continue

        week_number = training_day["week_number"]

        totals_by_week[week_number] = (
            totals_by_week.get(week_number, 0) + distance_km
        )

    return {
        week_number: round(distance_km, 2)
        for week_number, distance_km
        in totals_by_week.items()
    }


def synchronize_weekly_distances(
        recommendation: dict,
) -> dict:
    content = recommendation["content"]
    training_days = content.get("training_days", [])

    # The model doesn't reliably emit training_days in chronological order
    # (it tends to follow preferred_training_days' input order instead), so
    # anything reading this array positionally -- the frontend's weekly
    # display, or the revision flow's date-consistency check -- needs a
    # guaranteed date order rather than trusting generation order.
    training_days.sort(key=lambda day: day["date"])

    totals_by_week = calculate_weekly_distance_totals(
        training_days
    )

    for week in content.get("weekly_distance", []):
        week_number = week["week_number"]

        week["distance_km"] = totals_by_week.get(
            week_number,
            0,
        )

    return recommendation


def validate_plan_mode(
        recommendation: dict,
        plan_mode: str,
        cleared_activities: list[str],
) -> dict:
    easy_intensities = {
        "recovery",
        "very_easy",
        "easy",
    }
    cleared = set(cleared_activities)

    for day in recommendation["content"]["training_days"]:
        running = day.get("running")
        walking = day.get("walking")

        if running is not None and walking is not None:
            raise ValueError(
                "A day cannot contain both running and walking."
            )

        if plan_mode == "normal_running" and walking is not None:
            raise ValueError(
                "normal_running cannot contain walking."
            )

        if plan_mode == "easy_running":
            if (
                running is not None
                and running["intensity_level"]
                not in easy_intensities
            ):
                raise ValueError(
                    "easy_running contains excessive intensity."
                )

            if (
                walking is not None
                and walking["type"] not in cleared
            ):
                raise ValueError(
                    "Walking activity was not explicitly cleared."
                )

        if plan_mode == "walk_run":
            if running is not None:
                raise ValueError(
                    "walk_run cannot contain running blocks."
                )

            if (
                walking is not None
                and walking["type"] == "walk"
                and "walk" not in cleared
            ):
                raise ValueError(
                    "Pure walking was not explicitly cleared."
                )

        if plan_mode == "walk_only":
            if running is not None:
                raise ValueError(
                    "walk_only cannot contain running blocks."
                )

            if (
                walking is not None
                and walking["type"] != "walk"
            ):
                raise ValueError(
                    "walk_only cannot contain walk-run sessions."
                )

    return recommendation


def validate_revision_load(
        recommendation: dict,
        remaining_plan: dict,
        survey: dict,
        plan_mode: str,
) -> dict:
    """Check measurable adapted load constraints against the selected schedule.

    Only compare full weeks. Baseline recovery reductions remain permitted;
    this is a consistency check, not a clinical progression prescription.
    """
    days = recommendation["content"]["training_days"]
    limit = survey.get("max_session_minutes")
    if limit is not None:
        for day in days:
            duration = sum(
                (day.get(activity) or {}).get("duration_minutes", 0)
                for activity in ("running", "walking", "strength", "mobility")
            )
            if duration > limit:
                raise ValueError(
                    f"{day['date']} totals {duration} minutes, exceeding {limit}."
                )

    if plan_mode != "walk_run":
        return recommendation

    def weekly_load(training_days):
        result = {}
        for day in training_days:
            count, distance = result.get(day["week_number"], (0, 0.0))
            activity = day.get("running") or day.get("walking")
            result[day["week_number"]] = (
                count + int(activity is not None),
                distance + (activity["distance_km"] if activity else 0.0),
            )
        return result

    actual = weekly_load(days)
    baseline = weekly_load(remaining_plan["remaining_training_days"])
    revision_date = date.fromisoformat(remaining_plan["revision_date"])
    full_weeks = sorted(
        (week for week in remaining_plan["remaining_weekly_distance"]
         if date.fromisoformat(week["start_date"]) >= revision_date
         and (date.fromisoformat(week["end_date"])
              - date.fromisoformat(week["start_date"])).days == 6),
        key=lambda week: week["start_date"],
    )
    for previous, current in zip(full_weeks, full_weeks[1:]):
        before, after = previous["week_number"], current["week_number"]
        old_count, old_distance = actual.get(before, (0, 0.0))
        count, distance = actual.get(after, (0, 0.0))
        base_old_count, base_old_distance = baseline.get(before, (0, 0.0))
        base_count, base_distance = baseline.get(after, (0, 0.0))
        if count < old_count and base_count >= base_old_count:
            raise ValueError(
                f"Week {after} drops from {old_count} to {count} locomotion "
                "sessions without a baseline recovery reduction. Start with "
                "fewer sessions and keep frequency stable or build gradually."
            )
        if distance < old_distance - 0.01 and base_distance >= base_old_distance:
            raise ValueError(
                f"Week {after} drops from {old_distance:g} to {distance:g} km "
                "without a baseline recovery reduction. Start at reduced load."
            )
        if count > old_count and old_count > 0 and distance > old_distance + 0.01:
            raise ValueError(
                f"Week {after} increases frequency and distance together. "
                "Split the previous week's distance across shorter sessions."
            )
    return recommendation
