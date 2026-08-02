import pytest

from app.services.screenshot_service import ScreenshotService


class FakeBrowserService:
    async def take_screenshot(self, page):
        return "data:image/jpeg;base64,abc"


class FakeConnectionManager:
    def __init__(self):
        self.calls = []

    async def send_to_client(self, session_id, client_id, message):
        self.calls.append((session_id, client_id, message))
        return True


@pytest.mark.asyncio
async def test_capture_and_send_returns_true_on_success():
    service = ScreenshotService(FakeBrowserService(), FakeConnectionManager())
    ok = await service.capture_and_send(object(), "s1", "c1", caller="TEST")
    assert ok is True
