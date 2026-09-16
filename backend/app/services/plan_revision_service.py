from copy import deepcopy
from datetime import date
from typing import Any

from app.services.running_plan_service import (
    calculate_weekly_distance_totals,
)


class PlanFinishedError(ValueError):
    """The plan has no dates left to revise."""


def build_remaining_plan_context(
        recommendation: dict[str, Any],
        revision_date: date,
        requested_start_date: date | None = None,
) -> dict[str, Any]:
    """Copy sessions dated on or after revision_date and recalculate their weekly totals.

    Optionally shift the remaining schedule to a new start date. Raise
    PlanFinishedError when no dates remain; leave the original plan unchanged.
    """
    content = deepcopy(recommendation.get("content") or {})
    training_days = content.get("training_days") or []
    weekly_distance = content.get("weekly_distance") or []

    remaining_training_days = []

    for training_day in training_days:
        training_date_value = training_day.get("date")

        if not training_date_value:
            raise ValueError('Every training day must have a date.')

        try:
            training_date = date.fromisoformat(training_date_value)

        except ValueError as error:
            raise ValueError(f'Invalid date format for training day: '
                             f'{training_date_value}') from error

        if training_date >= revision_date:
            remaining_training_days.append(training_day)

    if not remaining_training_days:
        raise PlanFinishedError("This plan has finished. Generate a new plan.")

    remaining_week_numbers = {
        training_day['week_number'] for training_day in remaining_training_days
    }

    remaining_distance_by_week = (
        calculate_weekly_distance_totals(
            remaining_training_days
        )
    )

    remaining_weekly_distance = [
        {
            **week,
            'distance_km': remaining_distance_by_week.get(
                week['week_number'],
                0,
            ),
        }
        for week in weekly_distance
        if week['week_number'] in remaining_week_numbers
    ]

    if requested_start_date is not None:
        old_start_date = date.fromisoformat(remaining_training_days[0]['date'])
        delta = requested_start_date - old_start_date

        for training_day in remaining_training_days:
            shifted = date.fromisoformat(training_day['date']) + delta
            training_day['date'] = shifted.isoformat()
            training_day['day'] = shifted.strftime('%A').lower()

        for week in remaining_weekly_distance:
            week['start_date'] = (date.fromisoformat(week['start_date']) + delta).isoformat()
            week['end_date'] = (date.fromisoformat(week['end_date']) + delta).isoformat()

    return {
        'revision_date': revision_date.isoformat(),
        'remaining_week_numbers': sorted(remaining_week_numbers),
        'remaining_weekly_distance': remaining_weekly_distance,
        'remaining_training_days': remaining_training_days,
    }
