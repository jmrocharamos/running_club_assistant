from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from app.api.routes import feedbacks
from app.services.running_plan_service import validate_revision_load


def make_plan(counts, distances):
    start = date.today() + timedelta(days=(7 - date.today().weekday()) % 7)
    days, weeks = [], []
    for index, (count, distance) in enumerate(zip(counts, distances)):
        monday = start + timedelta(weeks=index)
        weeks.append(dict(week_number=index + 1, start_date=monday.isoformat(),
                          end_date=(monday + timedelta(days=6)).isoformat(), distance_km=distance))
        for slot in range(2):
            day = monday + timedelta(days=slot * 4)
            days.append(dict(week_number=index + 1, date=day.isoformat(), day=day.strftime('%A'), running=None,
                             walking=dict(type='walk_run', distance_km=distance / count,
                                          duration_minutes=30) if slot < count else None,
                             strength=dict(duration_minutes=15), mobility=dict(duration_minutes=6)))
    return dict(content=dict(training_days=days, weekly_distance=weeks))


def remaining(plan):
    return dict(revision_date=date.today().isoformat(),
                remaining_training_days=deepcopy(plan['content']['training_days']),
                remaining_weekly_distance=deepcopy(plan['content']['weekly_distance']))


def check(plan, baseline=None, context=None):
    return validate_revision_load(plan, context or remaining(baseline or make_plan([2]*4, [7, 7.5, 8.2, 9])),
                                  dict(max_session_minutes=60), 'walk_run')


def test_rejects_observed_frequency_reversal():
    with pytest.raises(ValueError, match='drops from 2 to 1'):
        check(make_plan([2, 1, 1, 1], [5, 3, 3.5, 4]))


def test_accepts_gradual_frequency_with_split_volume():
    check(make_plan([1, 1, 2, 2], [2.5]*4))


def test_accepts_stable_reduced_load():
    check(make_plan([1]*4, [2.5]*4))


def test_rejects_volume_drop_without_frequency_drop():
    with pytest.raises(ValueError, match='drops from 5 to 3 km'):
        check(make_plan([1]*4, [5, 3, 3, 3]))


def test_rejects_doubling_load_when_adding_session():
    with pytest.raises(ValueError, match='frequency and distance together'):
        check(make_plan([1, 1, 2, 2], [2.5, 2.5, 5, 5]))


def test_preserves_existing_recovery_week():
    plan = make_plan([2, 1, 1, 1], [5, 3, 3, 3])
    check(plan, baseline=plan)


def test_partial_first_week_is_not_compared():
    plan = make_plan([2, 1, 1, 1], [5, 3, 3, 3])
    context = remaining(make_plan([2]*4, [7]*4))
    first_start = date.fromisoformat(context['remaining_weekly_distance'][0]['start_date'])
    context['revision_date'] = (first_start + timedelta(days=1)).isoformat()
    check(plan, context=context)


@pytest.mark.parametrize('walking_minutes', [40, 44])
def test_rejects_observed_session_duration_overruns(walking_minutes):
    plan = make_plan([1]*4, [2.5]*4)
    plan['content']['training_days'][0]['walking']['duration_minutes'] = walking_minutes
    with pytest.raises(ValueError, match='exceeding 60'):
        check(plan)


def test_accepts_exact_duration_limit():
    plan = make_plan([1]*4, [2.5]*4)
    plan['content']['training_days'][0]['walking']['duration_minutes'] = 39
    check(plan)


def setup_revision(monkeypatch, outputs):
    user = SimpleNamespace(id=uuid4())
    original = make_plan([2]*4, [7, 7.5, 8.2, 9])
    rec = SimpleNamespace(id=uuid4(), user_id=user.id, survey_id=uuid4(),
        recommendation_type='running_plan', title='Return to running',
        content=original['content'], explanation=None, survey_snapshot=dict(max_session_minutes=60))
    db = Mock()
    db.get.return_value = rec
    monkeypatch.setattr(feedbacks, 'get_feedback_by_recommendation_id', lambda *_: [
        SimpleNamespace(created_at=date.today(), feedback='Plan is too hard')])
    monkeypatch.setattr(feedbacks, 'assess_feedback_safety', lambda *_: dict(
        decision='continue_revision', plan_mode='walk_run', medically_cleared_activities=['walk_run']))
    generate = Mock(side_effect=deepcopy(outputs))
    monkeypatch.setattr(feedbacks, 'get_recommendation', generate)
    return rec, user, db, generate


def test_retries_invalid_plan_and_saves_only_correction(monkeypatch):
    bad = make_plan([2, 1, 1, 1], [5, 3, 3.5, 4])
    good = make_plan([1, 1, 2, 2], [2.5]*4)
    rec, user, db, generate = setup_revision(monkeypatch, [bad, good])
    result = feedbacks.revise_recommendation_from_feedback(rec.id, user, db)
    assert result.content == good['content']
    assert generate.call_count == 2
    assert 'drops from 2 to 1' in generate.call_args.args[0]
    db.add.assert_called_once_with(result)
    db.commit.assert_called_once()


def test_failed_correction_does_not_save(monkeypatch):
    bad = make_plan([2, 1, 1, 1], [5, 3, 3.5, 4])
    rec, user, db, generate = setup_revision(monkeypatch, [bad, bad])
    with pytest.raises(HTTPException) as error:
        feedbacks.revise_recommendation_from_feedback(rec.id, user, db)
    assert error.value.status_code == 502
    assert 'No revised plan was saved' in error.value.detail
    assert generate.call_count == 2
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_partial_last_week_is_not_compared():
    plan = make_plan([2, 2, 2, 1], [5, 5, 5, 3])
    context = remaining(make_plan([2]*4, [7]*4))
    last_week = context['remaining_weekly_distance'][-1]
    last_week['end_date'] = last_week['start_date']
    check(plan, context=context)


def test_valid_plan_does_not_retry(monkeypatch):
    good = make_plan([1, 1, 2, 2], [2.5]*4)
    rec, user, db, generate = setup_revision(monkeypatch, [good])
    feedbacks.revise_recommendation_from_feedback(rec.id, user, db)
    generate.assert_called_once()
    db.commit.assert_called_once()


def test_generation_failure_does_not_save(monkeypatch):
    rec, user, db, generate = setup_revision(monkeypatch, [])
    generate.side_effect = RuntimeError('Provider unavailable')
    with pytest.raises(HTTPException) as error:
        feedbacks.revise_recommendation_from_feedback(rec.id, user, db)
    assert error.value.status_code == 502
    generate.assert_called_once()
    db.add.assert_not_called()
    db.commit.assert_not_called()
