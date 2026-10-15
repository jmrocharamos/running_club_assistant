from datetime import date, timedelta
import copy
import time

import jwt
import pytest
from sqlalchemy import select

from app.api.routes import chatbot, recommendations, feedbacks
from app.api.routes.demo import BROWSER_COOKIE_NAME
from app.core.config import JWT_ALGORITHM, JWT_SECRET_KEY
from app.models.coach_memory import CoachMemory
from app.models.survey import Survey
from app.models.user import User
from app.services import demo_session_service as demos
from app.services import ai_service, embedding_service
from app.core.request_context import demo_deadline
from types import SimpleNamespace
from unittest.mock import Mock
from tests.helpers import register_user


@pytest.fixture(autouse=True)
def demo_enabled(monkeypatch):
    monkeypatch.setattr(demos, 'DEMO_ENABLED', True)


def start(client):
    response = client.post('/demo/start')
    assert response.status_code == 200, response.text
    assert response.json()['is_demo']
    return response.json()


def stub_chat(monkeypatch):
    monkeypatch.setattr(chatbot, 'retrieve_knowledge', lambda *_: [])
    monkeypatch.setattr(chatbot, 'get_chat_reply', lambda *_: {'reply': 'Hello demo runner'})
    monkeypatch.setattr(chatbot, 'summarize_conversation', lambda *_: {'recap': 'A demo chat'})


def test_start_seed_resume_and_quota_survive_refresh(client, db_session, monkeypatch):
    stub_chat(monkeypatch)
    first = start(client)
    assert client.get('/auth/me').json()['demo_expires_at'] == first['demo_expires_at']
    survey = client.get('/surveys/latest').json()
    assert survey['answers']['plan_duration_weeks'] == 4
    assert client.post('/demo/start').json()['demo_expires_at'] == first['demo_expires_at']
    for _ in range(5):
        assert client.post('/chatbot/', json={'message': 'Hello'}).status_code == 200
    assert client.post('/chatbot/', json={'message': 'One too many'}).status_code == 429
    status = client.get('/demo/status').json()
    assert status['remaining']['chat'] == 0
    assert len(client.get('/chatbot/history').json()['messages']) == 10
    assert len(db_session.scalars(select(User)).all()) == 1
    session_id = client.get('/chatbot/history').json()['active_session_id']
    assert client.post('/chatbot/end', json={'session_id': session_id}).status_code == 200
    assert client.post('/chatbot/end', json={'session_id': session_id}).status_code == 200
    assert client.get('/demo/status').json()['remaining']['summaries'] == 0


def test_demo_failures_still_consume_budget(client, monkeypatch):
    start(client)
    stub_chat(monkeypatch)
    def fail(*_):
        raise RuntimeError('temporary AI failure')
    monkeypatch.setattr(chatbot, 'get_chat_reply', fail)
    assert client.post('/chatbot/', json={'message': 'Hello'}).status_code == 502
    assert client.get('/demo/status').json()['remaining']['chat'] == 4
    assert client.get('/chatbot/history').json()['messages'] == []


def test_demo_isolation_and_account_changes_blocked(client, second_client):
    first = start(client)
    start(second_client)
    survey_id = client.get('/surveys/latest').json()['id']
    assert second_client.get(f'/surveys/{survey_id}').status_code == 404
    assert client.patch('/users/me', json={'full_name': 'Other'}).status_code == 403
    assert client.post('/auth/change-password', json={'current_password': 'anything', 'new_password': 'something-new'}).status_code == 403
    assert second_client.get('/auth/me').json()['id'] != first['id']


def test_expiry_checks_database_and_cleanup_only_removes_demo_data(client, second_client, db_session, monkeypatch):
    user = start(client)
    register_user(second_client)
    memory = db_session.scalar(select(CoachMemory).where(CoachMemory.user_id == user['id']))
    data = copy.deepcopy(memory.summary)
    data[demos.KEY]['expires_at'] = (demos.now() - timedelta(seconds=1)).isoformat()
    memory.summary = data
    db_session.commit()
    assert client.get('/auth/me').status_code == 401
    assert client.post('/chatbot/', json={'message': 'expired'}).status_code == 401
    demos.cleanup(db_session)
    assert db_session.scalars(select(Survey).where(Survey.user_id == user['id'])).all() == []
    assert second_client.get('/auth/me').status_code == 200
    memory = db_session.scalar(select(CoachMemory).where(CoachMemory.user_id == user['id']))
    data = copy.deepcopy(memory.summary)
    data[demos.KEY]['created_at'] = (demos.now() - timedelta(hours=2)).isoformat()
    memory.summary = data
    db_session.commit()
    demos.cleanup(db_session)
    assert db_session.get(User, user['id']) is None
    assert second_client.get('/auth/me').status_code == 200


def test_rate_limits_flag_and_signed_expiry(client, monkeypatch):
    for _ in range(3):
        start(client)
        assert client.post('/auth/logout').status_code == 200
    assert client.post('/demo/start').status_code == 429
    monkeypatch.setattr(demos, 'DEMO_ENABLED', False)
    assert not client.get('/demo/config').json()['enabled']
    assert client.post('/demo/start').status_code == 503


def test_start_limits_separate_browsers_behind_the_same_proxy(client, second_client):
    # Both TestClients have the same server-observed host, as on a reverse proxy.
    for _ in range(3):
        start(client)
        assert client.post('/auth/logout').status_code == 200
    assert client.post('/demo/start').status_code == 429
    start(second_client)
    assert second_client.cookies[BROWSER_COOKIE_NAME] != client.cookies[BROWSER_COOKIE_NAME]


def test_browser_marker_is_signed_and_cannot_authenticate(client):
    start(client)
    marker = client.cookies[BROWSER_COOKIE_NAME]
    client.cookies.clear()
    client.cookies.set('access_token', marker)
    assert client.get('/auth/me').status_code == 401
    client.cookies.clear()
    forged = jwt.encode({'kind': 'demo_browser', 'nonce': '0' * 32,
                         'exp': demos.now() + timedelta(hours=1)}, 'untrusted-key', algorithm=JWT_ALGORITHM)
    client.cookies.set(BROWSER_COOKIE_NAME, forged, domain='testserver.local', path='/')
    start(client)
    payload = jwt.decode(client.cookies[BROWSER_COOKIE_NAME], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    assert payload['nonce'] != '0' * 32


def test_global_active_limit_still_applies_to_distinct_browsers(client):
    for _ in range(5):
        start(client)
        client.cookies.clear()
    response = client.post('/demo/start')
    assert response.status_code == 429
    assert 'places are in use' in response.json()['detail']


def test_registered_user_not_replaced_and_demo_forces_openai(client, monkeypatch):
    register_user(client)
    assert client.post('/demo/start').status_code == 409
    monkeypatch.setattr(ai_service, 'AI_PROVIDER', 'ollama')
    monkeypatch.setattr(embedding_service, 'EMBEDDING_PROVIDER', 'ollama')
    marker = demo_deadline.set(demos.now().timestamp() + 900)
    try:
        assert embedding_service.get_embedding_index()[1] == 'text-embedding-3-small'
        called = []
        monkeypatch.setattr(ai_service, 'import_module', lambda name: called.append(name))
        ai_service._client()
        assert called == ['app.client_openai']
    finally:
        demo_deadline.reset(marker)
    assert embedding_service.get_embedding_index()[1] != 'text-embedding-3-small'


def test_expiry_during_generation_prevents_save(client, db_session, monkeypatch):
    user = start(client)
    deadline = demos.now() + timedelta(seconds=2)
    token = jwt.encode({'sub': user['id'], 'kind': 'demo', 'exp': deadline}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    client.cookies.set('access_token', token)
    stub_chat(monkeypatch)
    def slow(*_):
        time.sleep(2.1)
        return {'reply': 'Too late to save'}
    monkeypatch.setattr(chatbot, 'get_chat_reply', slow)
    assert client.post('/chatbot/', json={'message': 'Hello'}).status_code == 401
    memory = db_session.scalar(select(CoachMemory).where(CoachMemory.user_id == user['id']))
    assert memory.summary.get('chat', {}).get('current_conversation', []) == []


def test_demo_plan_feedback_revision_and_quotas(client, monkeypatch):
    start(client)
    day = date.today() + timedelta(days=1)
    content = {'summary': 'A sample plan', 'training_days': [{
        'date': day.isoformat(), 'day': day.strftime('%A').lower(), 'week_number': 1,
        'running': {'type': 'easy', 'distance_km': 2, 'intensity_level': 'easy', 'details': 'Comfortable'},
        'walking': None, 'strength': None, 'mobility': None, 'notes': None,
    }], 'weekly_distance': [{'week_number': 1, 'start_date': date.today().isoformat(),
                            'end_date': (day + timedelta(days=6 - day.weekday())).isoformat(), 'distance_km': 2}], 'safety_notes': []}
    plan = {'content': content, 'explanation': {'why_this_plan_fits': ['Sample']}}
    monkeypatch.setattr(recommendations, 'generate_ai_recommendation', lambda *_: copy.deepcopy(plan))
    result = client.post('/recommendations/generate')
    assert result.status_code == 201, result.text
    identity = result.json()['id']
    assert client.post('/recommendations/generate').status_code == 429
    assert client.post(f'/recommendations/{identity}/feedback', json={'feedback': 'This felt comfortable. Please keep the schedule.'}).status_code == 201
    monkeypatch.setattr(feedbacks, 'assess_feedback_safety', lambda *_: {'decision': 'continue_revision', 'plan_mode': 'normal_running'})
    monkeypatch.setattr(feedbacks, 'get_recommendation', lambda *_, **kwargs: copy.deepcopy(plan))
    revised = client.post(f'/recommendations/{identity}/revise')
    assert revised.status_code == 201, revised.text
    assert client.post(f'/recommendations/{identity}/revise').status_code == 429
    assert client.get('/demo/status').json()['remaining']['revisions'] == 0


@pytest.mark.parametrize('feature,cap', [('chatbot', 1024), ('running_plan', 16000), ('training_safety', 2048)])
def test_demo_model_calls_have_deadline_and_output_budget(monkeypatch, feature, cap):
    from app import client_openai
    parse = Mock(return_value=SimpleNamespace(output_parsed={}, usage=None))
    configured = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    options = Mock(return_value=configured)
    monkeypatch.setattr(client_openai, 'client', SimpleNamespace(with_options=options))
    context = demo_deadline.set(demos.now().timestamp() + 30)
    try:
        client_openai._parse_response(model='gpt-5-mini', metadata={'feature': feature}, input='Synthetic demo')
        assert 0 < options.call_args.kwargs['timeout'] <= 30
        assert options.call_args.kwargs['max_retries'] == 0
        assert parse.call_args.kwargs['max_output_tokens'] == cap
        assert parse.call_args.kwargs['reasoning']['effort'] == 'minimal'
    finally:
        demo_deadline.reset(context)
