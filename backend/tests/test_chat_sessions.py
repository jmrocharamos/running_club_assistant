from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import engine
from time import monotonic, sleep

from app.api.routes import chatbot
from app.models.coach_memory import CoachMemory
from tests.helpers import register_user


def fake_ai(monkeypatch, summary=None):
    monkeypatch.setattr(chatbot, "retrieve_knowledge", lambda *args: [])
    monkeypatch.setattr(chatbot, "get_chat_reply", lambda *args: {"reply": "Consider strength training."})
    monkeypatch.setattr(chatbot, "summarize_conversation", lambda *args: summary or {
        "recap": "Discussed training preferences and strength work.",
        "current_goal": "Finish a 5K", "preferences": ["Trails"],
        "memory_evidence": [
            {"field": "current_goal", "runner_quote": "I want to finish a 5K", "operation": "replace"},
            {"field": "preferences", "runner_quote": "I like trails", "operation": "add"},
        ],
        "next_steps": [
            {"text": "Book a gym session", "runner_quote": "I will book a gym session"},
            {"text": "Start strength training", "runner_quote": "Consider strength training."},
        ],
        "open_questions": ["Which gym session fits?"],
    })


def send(client):
    response = client.post("/chatbot/", json={"message": "I want to finish a 5K. I like trails. I will book a gym session."})
    assert response.status_code == 200
    return response.json()["active_session_id"]


def end(client, session_id):
    response = client.post("/chatbot/end", json={"session_id": session_id})
    assert response.status_code == 200
    return response.json()


def test_legacy_memory_recaps_actions_and_controls(client, db_session, monkeypatch):
    register_user(client)
    memory = CoachMemory(user_id=client.get('/auth/me').json()['id'], summary={"chat": {
        "current_goal": "Marathon", "preferences": ["Morning runs"],
        "topics_of_interest": ["Shoes"], "progress": "Completed a first run",
    }})
    db_session.add(memory)
    db_session.commit()
    fake_ai(monkeypatch)
    session_id = send(client)
    result = end(client, session_id)
    state = result["summary"]["chat"]
    session = result["session"]
    assert state["current_conversation"] == []
    assert state["preferences"] == ["Morning runs", "Trails"]
    assert state["progress"] == "Completed a first run"
    assert state["topics_of_interest"] == ["Shoes"]
    assert session["started_at"] and session["ended_at"]
    assert [step["text"] for step in session["next_steps"]] == ["Book a gym session"]
    assert session["memory_changes"][0]["before"] == "Marathon"
    assert session["memory_changes"][0]["runner_quote"] == "I want to finish a 5K"
    step = session["next_steps"][0]
    changed = client.patch(f'/chatbot/sessions/{session_id}/steps/{step["id"]}', json={"completed": True, "revision": state["revision"]})
    assert changed.status_code == 200
    state = changed.json()["chat"]
    assert state["session_history"][0]["next_steps"][0]["completed"]
    deleted = client.delete(f'/chatbot/sessions/{session_id}?revision={state["revision"]}')
    assert deleted.status_code == 200
    state = deleted.json()["chat"]
    assert state["session_history"] == []
    assert state["current_goal"] == "Finish a 5K"
    changed = client.patch('/chatbot/memory', json={"revision": state["revision"], "current_goal": None,
        "preferences": [], "topics_of_interest": [], "progress": None})
    assert changed.status_code == 200
    assert client.get('/chatbot/history').json()['current_goal'] is None


def test_retains_ten_summaries_and_end_is_idempotent(client, monkeypatch):
    register_user(client)
    fake_ai(monkeypatch)
    ids = [end(client, send(client))["session"]["id"] for _ in range(12)]
    history = client.get('/chatbot/history').json()
    assert [session["id"] for session in history["session_history"]] == list(reversed(ids[-10:]))
    assert client.post('/chatbot/end').json()['session'] is None
    new_id = send(client)
    repeated = end(client, ids[-1])
    assert repeated["session"]["id"] == ids[-1]
    assert repeated["summary"]["chat"]["active_session_id"] == new_id
    assert len(repeated["summary"]["chat"]["current_conversation"]) == 2
    assert client.post('/chatbot/end', json={"session_id": ids[0]}).status_code == 409


@pytest.mark.parametrize('invalid', [True, False])
def test_failed_summary_preserves_conversation(client, monkeypatch, invalid):
    register_user(client)
    fake_ai(monkeypatch)
    session_id = send(client)
    def fail(*args):
        if invalid:
            return {"next_steps": [{"text": "invalid"}]}
        raise RuntimeError('model unavailable')
    monkeypatch.setattr(chatbot, 'summarize_conversation', fail)
    assert client.post('/chatbot/end', json={"session_id": session_id}).status_code == 502
    history = client.get('/chatbot/history').json()
    assert len(history['messages']) == 2
    assert history['session_history'] == []


def test_memory_conflicts_and_user_isolation(client, second_client, monkeypatch):
    register_user(client)
    fake_ai(monkeypatch)
    session_id = send(client)
    assert client.patch('/chatbot/memory', json={"revision": 1}).status_code == 409
    result = end(client, session_id)
    revision = result['summary']['chat']['revision']
    assert client.patch('/chatbot/memory', json={"revision": revision - 1}).status_code == 409
    register_user(second_client, username='other', email='other@example.com')
    assert second_client.get('/chatbot/history').json()['session_history'] == []
    assert second_client.delete(f'/chatbot/sessions/{session_id}?revision=0').status_code == 404
    step = result['session']['next_steps'][0]
    assert second_client.patch(f'/chatbot/sessions/{session_id}/steps/{step["id"]}', json={"revision": 0, "completed": True}).status_code == 404


def test_end_and_send_do_not_lose_new_messages(client, second_client, monkeypatch):
    register_user(client)
    second_client.cookies.update(client.cookies)
    fake_ai(monkeypatch)
    session_id = send(client)
    entered, release = Event(), Event()
    def summary(*args):
        entered.set()
        assert release.wait(5)
        return {"recap": "First conversation"}
    monkeypatch.setattr(chatbot, 'summarize_conversation', summary)
    with ThreadPoolExecutor(max_workers=2) as pool:
        closing = pool.submit(client.post, '/chatbot/end', json={"session_id": session_id})
        assert entered.wait(5)
        sending = pool.submit(second_client.post, '/chatbot/', json={"message": "A new conversation"})
        try:
            deadline = monotonic() + 3
            while True:
                with engine.connect() as connection:
                    waiting = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname = current_database() AND wait_event = 'advisory')"))
                if waiting:
                    break
                assert monotonic() < deadline, "Concurrent send did not wait for the session to finish"
                sleep(0.01)
        finally:
            release.set()
        assert closing.result(timeout=10).status_code == 200
        assert sending.result(timeout=10).status_code == 200
    history = client.get('/chatbot/history').json()
    assert history['messages'][0]['content'] == "A new conversation"
    assert len(history['session_history']) == 1


def test_no_memory_change_without_runner_evidence(client, monkeypatch):
    register_user(client)
    fake_ai(monkeypatch, {"recap": "Discussed running", "current_goal": "Invented marathon",
                         "memory_evidence": [{"field": "current_goal", "runner_quote": " ", "operation": "replace"}]})
    state = end(client, send(client))['summary']['chat']
    assert state['current_goal'] is None
    assert state['session_history'][0]['memory_changes'] == []


def test_partial_memory_edit_and_explicit_correction(client, monkeypatch):
    register_user(client)
    fake_ai(monkeypatch)
    state = end(client, send(client))['summary']['chat']
    response = client.patch('/chatbot/memory', json={"revision": state['revision'], "current_goal": "Run a 10K"})
    assert response.status_code == 200
    assert response.json()['chat']['preferences'] == ['Trails']
    fake_ai(monkeypatch, {"current_goal": None, "recap": "A changed goal", "memory_evidence": [
        {"field": "current_goal", "runner_quote": "I no longer have a running goal", "operation": "clear"}
    ]})
    session_id = client.post('/chatbot/', json={"message": "I no longer have a running goal"}).json()['active_session_id']
    state = end(client, session_id)['summary']['chat']
    assert state['current_goal'] is None
    assert state['preferences'] == ['Trails']


def test_database_save_failure_preserves_active_chat(client, monkeypatch):
    register_user(client)
    fake_ai(monkeypatch)
    session_id = send(client)
    original = Session.commit
    def fail_commit(db):
        if any(isinstance(row, CoachMemory) and row.summary.get('chat', {}).get('session_history') for row in db.dirty):
            raise RuntimeError('simulated write failure')
        return original(db)
    monkeypatch.setattr(Session, 'commit', fail_commit)
    with TestClient(app, raise_server_exceptions=False) as failing:
        failing.cookies.update(client.cookies)
        assert failing.post('/chatbot/end', json={"session_id": session_id}).status_code == 500
    state = client.get('/chatbot/history').json()
    assert len(state['messages']) == 2
    assert state['session_history'] == []
