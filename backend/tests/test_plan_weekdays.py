import pytest

from app.services.running_plan_service import synchronize_weekly_distances


def test_weekday_is_derived_from_date_instead_of_model_label():
    plan = {"content": {"training_days": [
        {"date": "2026-10-15", "day": "Friday", "week_number": 1},
        {"date": "2026-10-12", "day": "Monday", "week_number": 1},
    ], "weekly_distance": []}}
    result = synchronize_weekly_distances(plan)
    assert [(day["date"], day["day"]) for day in result["content"]["training_days"]] == [
        ("2026-10-12", "monday"), ("2026-10-15", "thursday"),
    ]


def test_invalid_generated_date_is_rejected():
    plan = {"content": {"training_days": [
        {"date": "2026-02-30", "day": "monday", "week_number": 1},
    ], "weekly_distance": []}}
    with pytest.raises(ValueError):
        synchronize_weekly_distances(plan)
