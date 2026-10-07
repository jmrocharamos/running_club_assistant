from copy import deepcopy
from unittest.mock import Mock

import pytest

from app.services.plan_calendar_service import build_plan_calendar, validate_plan_calendar
from app.services import recommendation_generation_service as generation


def example():
    answers = {"plan_start_date": "2026-10-12", "plan_duration_weeks": 4,
               "preferred_training_days": ["monday", "thursday"], "current_pain_level": 0,
               "current_issue_areas": ["none"]}
    calendar = build_plan_calendar(answers["plan_start_date"], 4, answers["preferred_training_days"])
    plan = {"content": {"summary": "Test plan", "safety_notes": [],
            "weekly_distance": [{k: v for k, v in week.items() if k != "available_training_days"}
                                for week in calendar],
            "training_days": [{**day, "week_number": week["week_number"],
                               "running": {"distance_km": 2, "intensity_level": "easy"}}
                              for week in calendar for day in week["available_training_days"]]},
            "explanation": {"why_this_plan_fits": []}}
    return {"answers": answers}, plan


def test_partial_first_week_and_event_date_are_explicit():
    calendar = build_plan_calendar("2026-10-14", 2, ["monday", "thursday"], "2026-10-18")
    assert calendar[0]["start_date"] == "2026-10-14"
    assert calendar[0]["end_date"] == "2026-10-18"
    assert [day["date"] for day in calendar[0]["available_training_days"]] == ["2026-10-15", "2026-10-18"]
    assert calendar[1]["start_date"] == "2026-10-19"


@pytest.mark.parametrize("change", ["unavailable", "duplicate", "wrong_week", "wrong_boundary"])
def test_rejects_schedule_deviations(change):
    survey, plan = example()
    if change == "unavailable":
        plan["content"]["training_days"][0].update(date="2026-10-13", day="tuesday")
    elif change == "duplicate":
        plan["content"]["training_days"].append(deepcopy(plan["content"]["training_days"][0]))
    elif change == "wrong_week":
        plan["content"]["training_days"][0]["week_number"] = 2
    else:
        plan["content"]["weekly_distance"][0]["start_date"] = "2026-10-11"
    with pytest.raises(ValueError):
        validate_plan_calendar(plan, survey, "normal_running")


def test_corrects_once_and_returns_only_valid_calendar(monkeypatch):
    survey, good = example()
    bad = deepcopy(good)
    bad["content"]["training_days"][0].update(date="2026-10-13", day="tuesday")
    monkeypatch.setattr(generation, "build_running_plan_input", lambda *args: "calendar input")
    model = Mock(side_effect=[bad, good])
    monkeypatch.setattr(generation, "get_recommendation", model)
    result = generation.generate_recommendation("synthetic", {}, survey)
    assert result is good
    assert model.call_count == 2
    assert "VALIDATION FAILURE" in model.call_args.args[0]


def test_failed_correction_raises_instead_of_returning_invalid_plan(monkeypatch):
    survey, bad = example()
    bad["content"]["training_days"][0].update(date="2026-10-13", day="tuesday")
    monkeypatch.setattr(generation, "build_running_plan_input", lambda *args: "calendar input")
    model = Mock(side_effect=[deepcopy(bad), deepcopy(bad)])
    monkeypatch.setattr(generation, "get_recommendation", model)
    with pytest.raises(ValueError, match="allowed training dates"):
        generation.generate_recommendation("synthetic", {}, survey)
    assert model.call_count == 2
