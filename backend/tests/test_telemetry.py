from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import client_openai
from app.services import telemetry


class RecordingClient:
    def __init__(self):
        self.events = []
        self.create_score = Mock()

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        event = {'start': kwargs, 'updates': []}
        self.events.append(event)
        observation = SimpleNamespace(trace_id='a' * 32,
                                      update=lambda **data: event['updates'].append(data))
        yield observation


@pytest.fixture
def recorder(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(telemetry, 'telemetry_client', lambda: client)
    return client


def test_payloads_and_error_messages_never_exported(recorder):
    @telemetry.traced('private_step')
    def operation(private_input):
        raise ValueError(private_input)

    with pytest.raises(ValueError, match='private health information'):
        operation('private health information')
    assert 'private health information' not in repr(recorder.events)
    assert recorder.events[0]['updates'] == [{'level': 'ERROR', 'status_message': 'ValueError'}]
    assert telemetry.current_trace_id() is None


def test_nested_trace_context_restored(recorder):
    with telemetry.trace_step('root'):
        assert telemetry.current_trace_id() == 'a' * 32
        with telemetry.trace_step('child'):
            assert telemetry.current_trace_id() == 'a' * 32
        assert telemetry.current_trace_id() == 'a' * 32
    assert telemetry.current_trace_id() is None


def test_sdk_start_failure_does_not_block_work(monkeypatch):
    client = Mock()
    client.start_as_current_observation.side_effect = RuntimeError('secret')
    monkeypatch.setattr(telemetry, 'telemetry_client', lambda: client)
    with telemetry.trace_step('work'):
        assert telemetry.current_trace_id() is None


def test_disabled_and_missing_credentials(monkeypatch):
    telemetry.telemetry_client.cache_clear()
    monkeypatch.setenv('LANGFUSE_TRACING_ENABLED', 'false')
    assert telemetry.telemetry_client() is None
    telemetry.telemetry_client.cache_clear()
    monkeypatch.setenv('LANGFUSE_TRACING_ENABLED', 'true')
    monkeypatch.delenv('LANGFUSE_SECRET_KEY', raising=False)
    assert telemetry.telemetry_client() is None
    telemetry.telemetry_client.cache_clear()


def test_response_usage_excludes_cached_and_reasoning_tokens(recorder, monkeypatch):
    response = SimpleNamespace(output_parsed=object(), usage=SimpleNamespace(
        input_tokens=100, output_tokens=40,
        input_tokens_details=SimpleNamespace(cached_tokens=30),
        output_tokens_details=SimpleNamespace(reasoning_tokens=10)))
    parse = Mock(return_value=response)
    monkeypatch.setattr(client_openai.client.responses, 'parse', parse)
    result = client_openai._parse_response(model='gpt-5-mini', input='private survey',
        instructions='private instructions', metadata={'feature': 'test', 'prompt_version': 'v2'})
    assert result is response
    event = recorder.events[0]
    assert event['start']['version'] == 'v2'
    assert event['updates'][0]['usage_details'] == {
        'input': 70, 'input_cached_tokens': 30, 'output': 30, 'output_reasoning_tokens': 10}
    assert 'private' not in repr(recorder.events)
    assert parse.call_args.kwargs['input'] == 'private survey'


def test_embedding_records_usage_not_vectors_or_text(recorder, monkeypatch):
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=25), data=['private vector'])
    monkeypatch.setattr(client_openai.client.embeddings, 'create', Mock(return_value=response))
    assert client_openai._embed(model='text-embedding-3-small', input=['private text']) is response
    assert recorder.events[0]['updates'][0] == {'usage_details': {'input': 25}}
    assert 'private' not in repr(recorder.events)


def test_ratings_use_stable_id_and_skip_legacy_plans(recorder):
    plan = SimpleNamespace(id='plan1', langfuse_trace_id=None, feedback_rating=4)
    telemetry.record_rating(plan)
    recorder.create_score.assert_not_called()
    plan.langfuse_trace_id='b' * 32
    telemetry.record_rating(plan)
    plan.feedback_rating=5
    telemetry.record_rating(plan)
    assert recorder.create_score.call_count == 2
    assert {call.kwargs['score_id'] for call in recorder.create_score.call_args_list} == {'plan-rating-plan1'}
    assert recorder.create_score.call_args.kwargs['value'] == 5
    assert recorder.create_score.call_args.kwargs['trace_id'] == 'b' * 32


def test_rating_export_failure_is_nonfatal(recorder):
    recorder.create_score.side_effect = RuntimeError('secret')
    telemetry.record_rating(SimpleNamespace(id='plan', langfuse_trace_id='b'*32, feedback_rating=4))


def test_revision_persists_root_trace_id(recorder, monkeypatch):
    from tests.test_revision_load import make_plan, setup_revision
    from app.api.routes.feedbacks import revise_recommendation_from_feedback
    plan=make_plan([1,1,2,2], [2.5]*4)
    rec,user,db,_=setup_revision(monkeypatch,[plan])
    result=revise_recommendation_from_feedback(rec.id,user,db)
    assert result.langfuse_trace_id == 'a'*32
    assert telemetry.current_trace_id() is None


def test_flush_failure_is_nonfatal(monkeypatch):
    client=Mock()
    client.flush.side_effect=RuntimeError('private endpoint')
    monkeypatch.setattr(telemetry,'telemetry_client',lambda:client)
    telemetry.shutdown_telemetry()


def test_real_sdk_exports_linked_spans_without_sensitive_payloads(monkeypatch):
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv('LANGFUSE_TRACING_ENABLED', 'true')
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    sdk = Langfuse(public_key='pk-lf-offline-test', secret_key='sk-lf-offline-test',
                   tracing_enabled=True, tracer_provider=provider, span_exporter=exporter)
    monkeypatch.setattr(telemetry, 'telemetry_client', lambda: sdk)
    with telemetry.trace_step('root', metadata={'user_id': 'opaque-test-user'},
                              tags=('running-plan', 'revised-plan'), trace_name='Plan revision'):
        with pytest.raises(ValueError):
            with telemetry.trace_step('child', kind='generation', model='gpt-5-mini'):
                raise ValueError('private health details and password')
    sdk.flush()
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert set(spans) == {'root', 'child'}
    for span in spans.values():
        assert 'revised-plan' in span.attributes['langfuse.trace.tags']
        assert span.attributes['langfuse.trace.name'] == 'Plan revision'
    assert spans['child'].parent.span_id == spans['root'].context.span_id
    assert spans['child'].context.trace_id == spans['root'].context.trace_id
    assert 'private health details' not in repr([(s.attributes, s.events) for s in spans.values()])
    assert spans['child'].attributes['langfuse.observation.status_message'] == 'ValueError'
    provider.shutdown()


def test_generated_plan_rating_links_to_persisted_trace(recorder, monkeypatch, client, db_session):
    from uuid import UUID
    from tests.helpers import register_user, create_survey
    from tests.test_revision_load import make_plan
    from app.api.routes import recommendations
    from app.models.recommendation import Recommendation

    assert register_user(client).status_code == 201
    assert create_survey(client).status_code == 201
    monkeypatch.setattr(recommendations, 'generate_ai_recommendation',
                        lambda *args: make_plan([1, 1, 2, 2], [2.5]*4))
    generated = client.post('/recommendations/generate')
    assert generated.status_code == 201
    plan_id = generated.json()['id']
    assert 'langfuse_trace_id' not in generated.json()
    saved = db_session.get(Recommendation, UUID(plan_id))
    assert saved.langfuse_trace_id == 'a'*32
    rated = client.patch(f'/recommendations/{plan_id}/rating', json={'feedback_rating': 4})
    assert rated.status_code == 200
    assert recorder.create_score.call_args.kwargs['trace_id'] == saved.langfuse_trace_id
    recorder.create_score.side_effect = RuntimeError('Telemetry is down')
    rated = client.patch(f'/recommendations/{plan_id}/rating', json={'feedback_rating': 5})
    assert rated.status_code == 200
    db_session.refresh(saved)
    assert saved.feedback_rating == 5


def test_sdk_update_and_exit_failures_preserve_application_result(monkeypatch):
    observation = Mock(trace_id='a'*32)
    observation.update.side_effect = RuntimeError('update failed')
    manager = Mock()
    manager.__enter__ = Mock(return_value=observation)
    manager.__exit__ = Mock(side_effect=RuntimeError('exit failed'))
    client = Mock()
    client.start_as_current_observation.return_value = manager
    monkeypatch.setattr(telemetry, 'telemetry_client', lambda: client)
    @telemetry.traced('test')
    def operation():
        return SimpleNamespace(id='result')
    assert operation().id == 'result'
    assert telemetry.current_trace_id() is None
