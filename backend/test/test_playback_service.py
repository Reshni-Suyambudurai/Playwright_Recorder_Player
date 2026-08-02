import pytest

import app.services.playback_service as playback_module
from app.services.playback_service import PlaybackService


class FakeElement:
    def __init__(self):
        self.clicked = None

    async def click(self, button="left"):
        self.clicked = button


class FakePage:
    def __init__(self, matches=None, url="https://example.com/page"):
        self._matches = matches or []
        self.waited_for = None
        self.url = url

    async def wait_for_selector(self, selector, timeout=None):
        self.waited_for = (selector, timeout)
        if not self._matches:
            raise Exception("selector not found")
        return self._matches[0]

    async def query_selector_all(self, selector):
        self.waited_for = (selector, self.waited_for[1] if self.waited_for else None)
        return self._matches


class FakeBrowserService:
    def __init__(self):
        self.clicks = []

    async def perform_click(self, page, x, y, button="left"):
        self.clicks.append((x, y, button))


@pytest.mark.asyncio
async def test_step_click_raises_when_selector_matches_zero_elements():
    browser_service = FakeBrowserService()
    service = PlaybackService(browser_service, None, None)
    page = FakePage(matches=[])
    step = {
        "type": "CLICK",
        "selector": {"strategy": "css", "value": ".missing", "occurrence_index": 0},
        "coords": {"x": 12, "y": 24},
    }

    with pytest.raises(Exception, match="matched 0 elements"):
        await service._step_click(step, page)

    assert browser_service.clicks == []


@pytest.mark.asyncio
async def test_step_click_zero_match_uses_coords_when_target_meta_matches(monkeypatch):
    async def fake_build_selector(page, x, y):
        return {
            "target_meta": {
                "tag": "div",
                "normalizedText": "find care",
                "ariaLabel": "find care",
            }
        }

    monkeypatch.setattr(playback_module, "build_selector", fake_build_selector)

    browser_service = FakeBrowserService()
    service = PlaybackService(browser_service, None, None)
    page = FakePage(matches=[])
    step = {
        "type": "CLICK",
        "selector": {"strategy": "css", "value": ".missing", "occurrence_index": 0},
        "coords": {"x": 20, "y": 30},
        "targetMeta": {
            "tag": "div",
            "normalizedText": "find care",
            "ariaLabel": "find care",
        },
    }

    await service._step_click(step, page)

    assert browser_service.clicks == [(20, 30, "left")]


@pytest.mark.asyncio
async def test_step_click_zero_match_raises_when_target_meta_mismatch(monkeypatch):
    async def fake_build_selector(page, x, y):
        return {
            "target_meta": {
                "tag": "button",
                "normalizedText": "different",
                "ariaLabel": "different",
            }
        }

    monkeypatch.setattr(playback_module, "build_selector", fake_build_selector)

    browser_service = FakeBrowserService()
    service = PlaybackService(browser_service, None, None)
    page = FakePage(matches=[])
    step = {
        "type": "CLICK",
        "selector": {"strategy": "css", "value": ".missing", "occurrence_index": 0},
        "coords": {"x": 20, "y": 30},
        "targetMeta": {
            "tag": "div",
            "normalizedText": "find care",
            "ariaLabel": "find care",
        },
    }

    with pytest.raises(Exception, match="matched 0 elements"):
        await service._step_click(step, page)

    assert browser_service.clicks == []


@pytest.mark.asyncio
async def test_step_click_falls_back_to_coords_when_occurrence_index_is_out_of_range():
    browser_service = FakeBrowserService()
    service = PlaybackService(browser_service, None, None)
    page = FakePage(matches=[FakeElement()])
    step = {
        "type": "CLICK",
        "selector": {"strategy": "css", "value": ".item", "occurrence_index": 2},
        "coords": {"x": 33, "y": 44},
        "button": "right",
    }

    await service._step_click(step, page)

    assert browser_service.clicks == [(33, 44, "right")]


@pytest.mark.asyncio
async def test_step_click_uses_coords_when_selector_is_absent():
    browser_service = FakeBrowserService()
    service = PlaybackService(browser_service, None, None)
    page = FakePage(matches=[])
    step = {
        "type": "CLICK",
        "coords": {"x": 7, "y": 9},
    }

    await service._step_click(step, page)

    assert browser_service.clicks == [(7, 9, "left")]