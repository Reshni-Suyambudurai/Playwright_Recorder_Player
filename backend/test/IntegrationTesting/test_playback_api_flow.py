from fastapi.testclient import TestClient

from app.main import create_app
from app.services.database import DatabaseService


def _build_client(monkeypatch):
    async def fake_init_db(self):
        return None

    monkeypatch.setattr(DatabaseService, "init_db", fake_init_db)
    return TestClient(create_app())


def test_play_start_and_stop_flow(monkeypatch):
    client = _build_client(monkeypatch)
    with client:
        bad = client.post("/play/start", json={})
        assert bad.status_code == 400

        payload = {
            "version": "1.0",
            "meta": {"id": "r1", "title": "flow"},
            "steps": {"tab-1": [[{"id": 1, "type": "NAVIGATE", "url": "https://example.com"}]]},
        }
        start = client.post("/play/start", json=payload)
        assert start.status_code == 200
        play_id = start.json()["play_session_id"]

        stop = client.delete(f"/play/{play_id}")
        assert stop.status_code == 200
        assert stop.json()["success"] is True
