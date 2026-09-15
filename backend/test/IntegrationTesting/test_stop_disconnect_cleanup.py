from fastapi.testclient import TestClient

from app.main import create_app
from app.services.database import DatabaseService


class DummyWatcher:
    def __init__(self):
        self.detached = False

    async def detach(self):
        self.detached = True


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
    return app, TestClient(app)


def test_websocket_disconnect_triggers_cleanup(monkeypatch):
    app, client = _build_client(monkeypatch)
    calls = {"detach_all_watchers": 0}
    session = None

    async def fake_detach_all_watchers(session):
        calls["detach_all_watchers"] += 1

    monkeypatch.setattr("app.main.tab_manager.detach_all_watchers", fake_detach_all_watchers)

    with client:
        start = client.post("/recording/start")
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        session = app.session_manager.get_session(session_id)
        session.dom_watcher = DummyWatcher()

        with client.websocket_connect(f"/ws/{session_id}") as ws:
            ws.send_json({
                "event_type": "HELLO",
                "client_id": "client-1",
                "data": {"client_id": "client-1"},
            })
            _ = ws.receive_json()

    assert calls["detach_all_watchers"] == 1
    assert session is not None and session.dom_watcher is None
