import asyncio

import pytest

from app.models.playback import PlaySession, PlayStatus
from app.websocket.playback_handler import PlaybackHandler


class FakeConnectionManager:
    def __init__(self):
        self.registered = None
        self.sent = []

    def register_client(self, play_id, client_id, websocket):
        self.registered = (play_id, client_id)

    async def send_to_client(self, play_id, client_id, payload):
        self.sent.append((play_id, client_id, payload))
        return True


class FakePlaybackService:
    async def run_playback(self, session, play_id, client_id):
        await asyncio.sleep(0)


class FakeBrowserService:
    async def perform_type(self, page, selector, text):
        return None


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)


class FakeMouse:
    def __init__(self):
        self.clicks = []

    async def click(self, x, y):
        self.clicks.append((x, y))


class FakePage:
    url = "https://example.test"

    def __init__(self):
        self.mouse = FakeMouse()

    async def title(self):
        return "Example"


@pytest.mark.asyncio
async def test_handle_event_hello_registers_client():
    cm = FakeConnectionManager()
    handler = PlaybackHandler(cm, FakePlaybackService(), FakeBrowserService())
    ws = FakeWebSocket()
    session = PlaySession(play_id="p1", recording_json={"steps": {}})
    await handler.handle_event("p1", ws, session, {"event_type": "HELLO", "data": {"client_id": "c1"}})
    assert cm.registered == ("p1", "c1")


def test_handle_resume_sets_pause_event():
    cm = FakeConnectionManager()
    handler = PlaybackHandler(cm, FakePlaybackService(), FakeBrowserService())
    session = PlaySession(play_id="p1", recording_json={"steps": {}})
    session.status = PlayStatus.PAUSED
    handler._handle_resume(session)
    assert session.pause_event.is_set() is True


@pytest.mark.asyncio
async def test_handle_stop_sets_stopped_status():
    cm = FakeConnectionManager()
    handler = PlaybackHandler(cm, FakePlaybackService(), FakeBrowserService())
    session = PlaySession(play_id="p1", recording_json={"steps": {}})
    await handler._handle_stop(session)
    assert session.status == PlayStatus.STOPPED


@pytest.mark.asyncio
async def test_pause_click_records_step(monkeypatch):
    async def fake_build_selector(page, x, y):
        return {
            "is_input": False,
            "selector": {"strategy": "id", "value": "reason-select"},
        }

    monkeypatch.setattr("app.websocket.playback_handler.build_selector", fake_build_selector)

    handler = PlaybackHandler(FakeConnectionManager(), FakePlaybackService(), FakeBrowserService())
    session = PlaySession(play_id="p1", recording_json={"steps": {}})
    session.status = PlayStatus.PAUSED
    session.page = FakePage()
    session.enable_pause_recording = True
    session.current_step_id = 7

    await handler.handle_event(
        "p1",
        FakeWebSocket(),
        session,
        {"event_type": "PAUSE_CLICK", "data": {"x": 365, "y": 279}},
    )

    captured = session.pause_step_insertion_points[7]
    assert len(captured) == 1
    assert captured[0].type == "CLICK"
    assert captured[0].button == "left"
    assert captured[0].selector.value == "reason-select"
