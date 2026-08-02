import asyncio

import pytest

import app.services.capture_manager as capture_module
from app.services.capture_manager import CaptureManager, CaptureReason, SettleStrategy
from app.services.dom_watcher import DomWatcher
from app.services.screenshot_service import ScreenshotService


class FakeBrowserService:
    async def take_screenshot(self, page):
        return "data:image/jpeg;base64,abc"


class FakeConnectionManager:
    def __init__(self):
        self.messages = []

    async def send_to_client(self, session_id, client_id, message):
        self.messages.append(message)
        return True


class FakePage:
    def __init__(self):
        self.handlers = {}

    def on(self, event_name, callback):
        self.handlers[event_name] = callback

    async def expose_function(self, name, callback):
        return None

    async def add_init_script(self, script):
        return None

    async def evaluate(self, script):
        return None

    async def wait_for_load_state(self, state, timeout=0):
        return None


@pytest.mark.asyncio
async def test_action_and_dom_watcher_frames_flow(monkeypatch):
    monkeypatch.setattr(capture_module, "DOM_POLL_MS", 10)

    conn = FakeConnectionManager()
    screenshot_service = ScreenshotService(FakeBrowserService(), conn)
    manager = CaptureManager(screenshot_service, "s1", "c1")
    watcher = DomWatcher(manager)
    page = FakePage()

    await watcher.attach(page, "s1", "c1")

    await manager.request(page, CaptureReason.ACTION_CLICK, settle=SettleStrategy.NONE)
    await watcher._on_dom_mutation()
    manager._wake_event.set()

    await asyncio.sleep(0.05)
    manager.stop()

    sources = [m["data"]["source"] for m in conn.messages]
    assert "CLICK" in sources and "DOM-WATCHER" in sources
