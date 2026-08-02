import asyncio

import pytest

import app.services.capture_manager as capture_module
from app.services.capture_manager import CaptureManager, CaptureReason, SettleStrategy


class FakeScreenshotService:
    def __init__(self):
        self.calls = []

    async def capture_and_send(self, page, session_id, client_id, caller="?"):
        self.calls.append((page, session_id, client_id, caller))
        return True


class FakePage:
    def __init__(self):
        self.states = []

    async def wait_for_load_state(self, state, timeout=0):
        self.states.append((state, timeout))


@pytest.mark.asyncio
async def test_start_worker_creates_task(monkeypatch):
    service = FakeScreenshotService()
    mgr = CaptureManager(service, "s1", "c1")
    monkeypatch.setattr(capture_module, "DOM_POLL_MS", 10)
    mgr.start_worker(FakePage())
    await asyncio.sleep(0.02)
    assert mgr._worker_task is not None
    mgr.stop()


@pytest.mark.asyncio
async def test_stop_clears_dirty_and_task(monkeypatch):
    service = FakeScreenshotService()
    mgr = CaptureManager(service, "s1", "c1")
    monkeypatch.setattr(capture_module, "DOM_POLL_MS", 10)
    mgr._dirty = True
    mgr.start_worker(FakePage())
    mgr.stop()
    assert mgr._dirty is False


@pytest.mark.asyncio
async def test_request_high_priority_captures(monkeypatch):
    service = FakeScreenshotService()
    mgr = CaptureManager(service, "s1", "c1")
    page = FakePage()
    ok = await mgr.request(page, CaptureReason.ACTION_SCROLL, settle=SettleStrategy.NONE)
    assert ok is True


@pytest.mark.asyncio
async def test_request_dom_mutation_sets_dirty():
    service = FakeScreenshotService()
    mgr = CaptureManager(service, "s1", "c1")
    page = FakePage()
    await mgr.request(page, CaptureReason.DOM_MUTATION)
    assert mgr._dirty is True


@pytest.mark.asyncio
async def test_capture_now_wait_for_nav_uses_page_state():
    service = FakeScreenshotService()
    mgr = CaptureManager(service, "s1", "c1")
    page = FakePage()
    ok = await mgr._capture_now(page, CaptureReason.STEP_DONE, SettleStrategy.WAIT_FOR_NAV, 5)
    assert ok is True


@pytest.mark.asyncio
async def test_dom_capture_worker_consumes_dirty(monkeypatch):
    service = FakeScreenshotService()
    mgr = CaptureManager(service, "s1", "c1")
    monkeypatch.setattr(capture_module, "DOM_POLL_MS", 10)
    page = FakePage()
    mgr.start_worker(page)
    mgr._page = page
    mgr._dirty = True
    mgr._wake_event.set()
    await asyncio.sleep(0.05)
    assert service.calls
    mgr.stop()
