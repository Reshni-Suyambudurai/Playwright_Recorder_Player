import pytest

import app.services.playback_service as playback_module
from app.services.playback_service import PlaybackService


class FakeElement:
    def __init__(self, text=None, attributes=None, children=None, box=None):
        self.clicked = None
        self.text = text
        self.attributes = attributes or {}
        self.children = children or []
        self.box = box

    async def click(self, button="left"):
        self.clicked = button

    async def inner_text(self):
        return self.text

    async def text_content(self):
        return self.text

    async def get_attribute(self, name):
        return self.attributes.get(name)

    async def query_selector_all(self, selector):
        return self.children

    async def bounding_box(self):
        return self.box


class FakePage:
    def __init__(self, matches=None, url="https://example.com/page", selector_map=None):
        self._matches = matches or []
        self._selector_map = selector_map or {}
        self.waited_for = None
        self.selector_timeouts = []
        self.url = url

    async def wait_for_selector(self, selector, timeout=None):
        self.waited_for = (selector, timeout)
        self.selector_timeouts.append(timeout)
        if not self._matches:
            raise Exception("selector not found")
        return self._matches[0]

    async def query_selector_all(self, selector):
        self.waited_for = (selector, self.waited_for[1] if self.waited_for else None)
        if selector in self._selector_map:
            return self._selector_map[selector]
        return self._matches

    async def query_selector(self, selector):
        matches = await self.query_selector_all(selector)
        return matches[0] if matches else None


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
    assert page.selector_timeouts == list(playback_module.CLICK_SELECTOR_TIMEOUTS_MS)


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


@pytest.mark.asyncio
async def test_step_click_zero_match_recovers_dropdown_by_recorded_value():
    browser_service = FakeBrowserService()
    service = PlaybackService(browser_service, None, None)
    option = FakeElement(text="Meeting")
    page = FakePage(
        matches=[],
        selector_map={
            "xpath=//*[contains(@class,'zdropdownlist__text') and normalize-space(.)='meeting']": [option],
        },
    )
    step = {
        "type": "CLICK",
        "button": "left",
        "selector": {"strategy": "css", "value": ".missing", "occurrence_index": 0},
        "coords": {"x": 508, "y": 399},
        "targetMeta": {
            "text": "Meeting",
            "normalizedText": "meeting",
            "classHints": ["zdropdownlist__text"],
        },
    }

    await service._step_click(step, page)

    assert option.clicked == "left"
    assert browser_service.clicks == []


@pytest.mark.asyncio
async def test_step_click_zero_match_dropdown_recovery_miss_fails_strict():
    browser_service = FakeBrowserService()
    service = PlaybackService(browser_service, None, None)
    page = FakePage(matches=[])
    step = {
        "type": "CLICK",
        "selector": {"strategy": "css", "value": ".missing", "occurrence_index": 0},
        "coords": {"x": 508, "y": 399},
        "targetMeta": {
            "text": "Meeting",
            "normalizedText": "meeting",
            "classHints": ["zdropdownlist__text"],
        },
    }

    with pytest.raises(Exception, match="matched 0 elements"):
        await service._step_click(step, page)

    assert browser_service.clicks == []


@pytest.mark.asyncio
async def test_step_click_replays_dropdown_selection_using_current_popup_id():
    option = FakeElement(text="Client A")
    controller = FakeElement(attributes={"aria-owns": "zselect-62394687-listbox"})
    page = FakePage(selector_map={
        "#dayclientselect1-container": [controller],
        "#zselect-62394687-listbox": [FakeElement(children=[option])],
    })
    service = PlaybackService(FakeBrowserService(), None, None)
    step = {
        "type": "CLICK",
        "button": "left",
        "dropdownSelection": {
            "controllerSelector": {
                "strategy": "id", "value": "dayclientselect1-container", "occurrence_index": 0,
            },
            "text": "Client A",
            "normalizedText": "client a",
            "optionIndex": 0,
        },
    }

    await service._step_click(step, page)

    assert controller.clicked is None
    assert option.clicked == "left"


@pytest.mark.asyncio
async def test_dropdown_selection_uses_coordinates_before_occurrence_index():
    first_option = FakeElement(text="Wrong Client")
    selected_option = FakeElement(text="Client A")
    first_controller = FakeElement(
        attributes={"aria-owns": "first-popup"},
        box={"x": 0, "y": 0, "width": 100, "height": 40},
    )
    selected_controller = FakeElement(
        attributes={"aria-owns": "selected-popup"},
        box={"x": 150, "y": 0, "width": 100, "height": 40},
    )
    page = FakePage(selector_map={
        ".client-selector": [first_controller, selected_controller],
        "#first-popup": [FakeElement(children=[first_option])],
        "#selected-popup": [FakeElement(children=[selected_option])],
    })
    service = PlaybackService(FakeBrowserService(), None, None)
    step = {
        "type": "CLICK",
        "coords": {"x": 200, "y": 20},
        "dropdownSelection": {
            "controllerSelector": {
                "strategy": "css", "value": ".client-selector", "occurrence_index": 0,
            },
            "text": "Client A",
            "optionIndex": 0,
        },
    }

    await service._step_click(step, page)

    assert first_controller.clicked is None
    assert selected_controller.clicked is None
    assert selected_option.clicked == "left"