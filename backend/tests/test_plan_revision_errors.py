from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import feedbacks
from app.services.plan_revision_service import PlanFinishedError, build_remaining_plan_context


def plan_for(day):
    return {"content": {"training_days": [{
        "date": day.isoformat(), "week_number": 1, "running": None,
    }], "weekly_distance": []}}


def test_finished_plan_has_specific_error():
    today = date.today()
    with pytest.raises(PlanFinishedError, match="This plan has finished"):
        build_remaining_plan_context(plan_for(today - timedelta(days=1)), today)


@pytest.mark.parametrize("offset", [0, 1])
def test_today_and_future_dates_remain_revisable(offset):
    today = date.today()
    day = today + timedelta(days=offset)
    remaining = build_remaining_plan_context(plan_for(day), today)
    assert remaining["remaining_training_days"][0]["date"] == day.isoformat()


def test_date_shift_still_works_without_mutating_original():
    today = date.today()
    original = plan_for(today)
    shifted = today + timedelta(days=2)
    remaining = build_remaining_plan_context(original, today, shifted)
    assert remaining["remaining_training_days"][0]["date"] == shifted.isoformat()
    assert original["content"]["training_days"][0]["date"] == today.isoformat()


def test_malformed_date_is_not_reported_as_finished():
    original = plan_for(date.today())
    original["content"]["training_days"][0]["date"] = "invalid"
    with pytest.raises(ValueError) as error:
        build_remaining_plan_context(original, date.today())
    assert not isinstance(error.value, PlanFinishedError)


def test_finished_revision_stops_before_ai_and_writes(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    recommendation = SimpleNamespace(
        id=uuid4(), user_id=user.id, survey_id=uuid4(),
        recommendation_type="running_plan", title="Old plan",
        content=plan_for(date.today() - timedelta(days=1))["content"],
        explanation=None, survey_snapshot={},
    )
    db = Mock()
    db.get.return_value = recommendation
    monkeypatch.setattr(feedbacks, "get_feedback_by_recommendation_id", lambda *_: [
        SimpleNamespace(created_at=date.today(), feedback={"notes": "Please revise"}),
    ])
    assess = Mock()
    generate = Mock()
    monkeypatch.setattr(feedbacks, "assess_feedback_safety", assess)
    monkeypatch.setattr(feedbacks, "get_recommendation", generate)
    with pytest.raises(HTTPException) as error:
        feedbacks.revise_recommendation_from_feedback(recommendation.id, user, db)
    assert error.value.status_code == 409
    assert error.value.detail == "This plan has finished. Generate a new plan."
    assess.assert_not_called()
    generate.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()
