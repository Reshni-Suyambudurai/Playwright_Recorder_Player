from fastapi.testclient import TestClient

from app.main import create_app
from app.services.database import DatabaseService


def _build_client(monkeypatch):
    async def fake_init_db(self):
        return None

    async def fake_launch_browser(*args, **kwargs):
        return object(), object(), object()

    async def fake_close_browser(*args, **kwargs):
        return None

    monkeypatch.setattr(DatabaseService, "init_db", fake_init_db)
    app = create_app()
    monkeypatch.setattr(app.browser_service, "launch_browser", fake_launch_browser)
    monkeypatch.setattr(app.browser_service, "close_browser", fake_close_browser)
    return TestClient(app)


def test_websocket_hello_and_ping_routing(monkeypatch):
    client = _build_client(monkeypatch)
    with client:
        start = client.post("/recording/start")
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        with client.websocket_connect(f"/ws/{session_id}") as ws:
            ws.send_json({
                "event_type": "HELLO",
                "client_id": "client-1",
                "data": {"client_id": "client-1"},
            })
            welcome = ws.receive_json()
            assert welcome["event_type"] == "WELCOME"

            ws.send_json({
                "event_type": "PING",
                "client_id": "client-1",
                "data": {"timestamp": "t1"},
            })
            pong = ws.receive_json()
            assert pong["event_type"] == "PONG"
