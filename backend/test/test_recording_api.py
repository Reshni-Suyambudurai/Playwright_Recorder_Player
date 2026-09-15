import pytest
from fastapi import HTTPException

from app.api.recording import RecordingAPI
from app.models.session import RecordingSession


class FakeSessionManager:
    def __init__(self):
        self.session = None

    def create_session(self):
        self.session = RecordingSession(session_id="s1")
        return self.session

    def get_session(self, session_id):
        return self.session if self.session and self.session_id_matches(session_id) else None

    def session_id_matches(self, session_id):
        return self.session and self.session.session_id == session_id

    def remove_session(self, session_id):
        return True


class FakeBrowserService:
    async def launch_browser(self):
        return object(), object(), object()

    async def close_browser(self, browser):
        return None


class FakeConnectionManager:
    async def send_to_client(self, session_id, client_id, message):
        return True


@pytest.mark.asyncio
async def test_start_recording_returns_success_payload():
    api = RecordingAPI(FakeSessionManager(), FakeBrowserService(), FakeConnectionManager())
    result = await api.start_recording()
    assert result["success"] is True


@pytest.mark.asyncio
async def test_stop_recording_raises_not_found_for_missing_session():
    api = RecordingAPI(FakeSessionManager(), FakeBrowserService(), FakeConnectionManager())
    with pytest.raises(HTTPException):
        await api.stop_recording("missing")
