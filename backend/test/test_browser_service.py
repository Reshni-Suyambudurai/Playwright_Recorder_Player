import base64

import pytest

import app.services.browser_service as browser_module
from app.services.browser_service import BrowserService


class FakeMouse:
    def __init__(self):
        self.clicked = None
        self.moved = None
        self.wheeled = None

    async def click(self, x, y, button="left"):
        self.clicked = (x, y, button)

    async def move(self, x, y):
        self.moved = (x, y)

    async def wheel(self, dx, dy):
        self.wheeled = (dx, dy)


class FakeKeyboard:
    def __init__(self):
        self.typed = None
        self.pressed = None

    async def type(self, text):
        self.typed = text

    async def press(self, key):
        self.pressed = key


class FakeElement:
    def __init__(self):
        self.value = None

    async def fill(self, text):
        self.value = text


class FakePage:
    def __init__(self):
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()
        self.filled = None

    async def screenshot(self, **kwargs):
        return b"img"

    async def fill(self, selector, text):
        self.filled = (selector, text)

    async def query_selector_all(self, query):
        return [FakeElement(), FakeElement()]

    async def goto(self, url, wait_until=None, timeout=None):
        class R:
            status = 200
        return R()

    async def wait_for_load_state(self, state, timeout=None):
        return None

    async def title(self):
        return "Page"


@pytest.mark.asyncio
async def test_launch_browser_returns_handles(monkeypatch):
    service = BrowserService()

    class FakeContext:
        async def new_page(self):
            return "page"

    class FakeBrowser:
        async def new_context(self, viewport=None):
            return FakeContext()

    class FakeChromium:
        async def launch(self, headless=True):
            return FakeBrowser()

    class FakePW:
        chromium = FakeChromium()

        async def stop(self):
            return None

    class Factory:
        async def start(self):
            return FakePW()

    monkeypatch.setattr(browser_module, "async_playwright", lambda: Factory())
    browser, context, page = await service.launch_browser()
    assert browser is not None and context is not None and page == "page"


@pytest.mark.asyncio
async def test_take_screenshot_returns_data_uri():
    service = BrowserService()
    data = await service.take_screenshot(FakePage())
    assert data.startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_perform_click_calls_mouse_click():
    service = BrowserService()
    page = FakePage()
    await service.perform_click(page, 1, 2)
    assert page.mouse.clicked == (1, 2, "left")


@pytest.mark.asyncio
async def test_perform_scroll_calls_move_and_wheel():
    service = BrowserService()
    page = FakePage()
    await service.perform_scroll(page, 10, 20, 0, 30)
    assert page.mouse.moved == (10, 20)


@pytest.mark.asyncio
async def test_perform_type_fills_id_selector():
    service = BrowserService()
    page = FakePage()
    await service.perform_type(page, {"strategy": "id", "value": "name"}, "abc")
    assert page.filled == ("#name", "abc")


@pytest.mark.asyncio
async def test_perform_key_presses_keyboard_key():
    service = BrowserService()
    page = FakePage()
    await service.perform_key(page, "Enter")
    assert page.keyboard.pressed == "Enter"


@pytest.mark.asyncio
async def test_close_browser_closes_browser_and_playwright():
    service = BrowserService()

    class FakeBrowser:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    class FakePW:
        def __init__(self):
            self.stopped = False

        async def stop(self):
            self.stopped = True

    browser = FakeBrowser()
    service._playwright = FakePW()
    await service.close_browser(browser)
    assert browser.closed is True


@pytest.mark.asyncio
async def test_navigate_to_url_returns_success_payload():
    service = BrowserService()
    page = FakePage()
    result = await service.navigate_to_url(page, "example.com")
    assert result["success"] is True
