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


def test_recording_start_and_stop_flow(monkeypatch):
    client = _build_client(monkeypatch)
    with client:
        start = client.post("/recording/start")
        assert start.status_code == 200
        assert start.json()["success"] is True
        session_id = start.json()["session_id"]

        stop = client.post("/recording/stop", json={"session_id": session_id})
        assert stop.status_code == 200
        assert stop.json()["success"] is True
