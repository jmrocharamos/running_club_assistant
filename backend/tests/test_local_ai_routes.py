import httpx
from sqlalchemy import select

from app import client_ollama
from app.api.routes import chatbot
from app.models.recommendation import Recommendation
from app.services import ai_service
from tests.helpers import create_survey, register_user


def test_local_chat_and_summary_persist_through_routes(client, monkeypatch):
    register_user(client)
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(chatbot, "retrieve_knowledge", lambda *args: [])

    def post(url, **kwargs):
        schema = kwargs["json"]["format"]
        content = '{"reply":"Hello runner"}' if schema["title"] == "ChatReplyOutput" else '{"current_goal":"Finish a 5K", "preferences":[], "topics_of_interest":[], "progress":null}'
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "done": True, "done_reason": "stop", "message": {"content": content},
        })

    monkeypatch.setattr(client_ollama.httpx, "post", post)
    reply = client.post("/chatbot/", json={"message": "I want to finish a 5K"})
    assert reply.status_code == 200
    assert reply.json()["reply"] == "Hello runner"
    assert len(client.get("/chatbot/history").json()["messages"]) == 2
    assert client.post("/chatbot/end").status_code == 200
    history = client.get("/chatbot/history").json()
    assert history["messages"] == []
    assert history["current_goal"] == "Finish a 5K"


def test_invalid_local_plan_does_not_save(client, db_session, monkeypatch):
    register_user(client)
    create_survey(client)
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(client_ollama.httpx, "post", lambda url, **kwargs: httpx.Response(
        200, request=httpx.Request("POST", url), json={
            "done": True, "done_reason": "length", "message": {"content": '{}'},
        },
    ))
    assert client.post("/recommendations/generate").status_code == 502
    assert db_session.scalars(select(Recommendation)).all() == []
