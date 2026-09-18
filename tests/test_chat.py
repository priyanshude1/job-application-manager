from fastapi.testclient import TestClient

from api.main import app
from api.routers import chat


class FakeAgentGraph:
    def __init__(self):
        self.states = []

    def invoke(self, initial_state):
        self.states.append(initial_state)
        return {
            **initial_state,
            "messages": [
                *initial_state["messages"],
                {
                    "role": "assistant",
                    "content": f"Handled: {initial_state['messages'][-1]['content']}",
                },
            ],
            "final_response": f"Handled: {initial_state['messages'][-1]['content']}",
        }


def test_chat_routes_are_registered():
    routes = {route.path for route in app.routes}

    assert "/chat" in routes
    assert "/chat/sessions" in routes
    assert "/chat/sessions/{session_id}" in routes


def test_chat_creates_session_and_returns_graph_response(monkeypatch):
    fake_graph = FakeAgentGraph()
    monkeypatch.setattr(chat, "agent_graph", fake_graph)
    chat.sessions.clear()

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Handled: Hello"
    assert body["session_id"] in chat.sessions
    assert chat.sessions[body["session_id"]][-1] == {
        "role": "assistant",
        "content": "Handled: Hello",
    }
    assert len(fake_graph.states) == 1
    assert fake_graph.states[0]["tool_call_count"] == 0


def test_chat_reuses_session_history(monkeypatch):
    fake_graph = FakeAgentGraph()
    monkeypatch.setattr(chat, "agent_graph", fake_graph)
    chat.sessions.clear()

    with TestClient(app) as client:
        first = client.post("/chat", json={"message": "First message"})
        session_id = first.json()["session_id"]
        second = client.post(
            "/chat",
            json={"message": "Second message", "session_id": session_id},
        )

    assert second.status_code == 200
    assert second.json()["session_id"] == session_id
    assert len(fake_graph.states) == 2
    assert [message["content"] for message in fake_graph.states[1]["messages"]] == [
        "First message",
        "Handled: First message",
        "Second message",
    ]


def test_chat_rejects_empty_message(monkeypatch):
    fake_graph = FakeAgentGraph()
    monkeypatch.setattr(chat, "agent_graph", fake_graph)
    chat.sessions.clear()

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "Message cannot be empty"
    assert fake_graph.states == []


def test_chat_lists_and_deletes_sessions(monkeypatch):
    fake_graph = FakeAgentGraph()
    monkeypatch.setattr(chat, "agent_graph", fake_graph)
    chat.sessions.clear()

    with TestClient(app) as client:
        created = client.post("/chat", json={"message": "Keep this session"})
        session_id = created.json()["session_id"]

        listed = client.get("/chat/sessions")
        deleted = client.delete(f"/chat/sessions/{session_id}")
        listed_after_delete = client.get("/chat/sessions")

    assert listed.status_code == 200
    assert session_id in listed.json()["sessions"]
    assert deleted.status_code == 200
    assert session_id not in chat.sessions
    assert listed_after_delete.json()["sessions"] == []


def test_chat_delete_missing_session_returns_404():
    chat.sessions.clear()

    with TestClient(app) as client:
        response = client.delete("/chat/sessions/missing-session")

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"
