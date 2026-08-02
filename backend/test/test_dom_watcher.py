import pytest

from app.services.dom_watcher import DomWatcher


class FakeCaptureManager:
    def __init__(self):
        self.started_with = None
        self.stopped = False
        self._dirty = False
        self._page = None

    def start_worker(self, page):
        self.started_with = page

    def stop(self):
        self.stopped = True


class FakePage:
    def __init__(self):
        self.handlers = {}
        self.exposed = {}
        self.init_scripts = []
        self.evaluated_scripts = []

    def on(self, event_name, callback):
        self.handlers[event_name] = callback

    async def expose_function(self, name, callback):
        self.exposed[name] = callback

    async def add_init_script(self, script):
        self.init_scripts.append(script)

    async def evaluate(self, script):
        self.evaluated_scripts.append(script)


@pytest.mark.asyncio
async def test_attach_registers_handlers_and_starts_worker():
    manager = FakeCaptureManager()
    watcher = DomWatcher(manager)
    page = FakePage()
    await watcher.attach(page, "s1", "c1")
    assert manager.started_with is page


@pytest.mark.asyncio
async def test_detach_stops_worker():
    manager = FakeCaptureManager()
    watcher = DomWatcher(manager)
    watcher._active = True
    await watcher.detach()
    assert manager.stopped is True


def test_on_page_event_marks_dirty():
    manager = FakeCaptureManager()
    watcher = DomWatcher(manager)
    watcher._active = True
    watcher._page = object()
    watcher._on_page_event()
    assert manager._dirty is True


@pytest.mark.asyncio
async def test_on_dom_mutation_marks_dirty():
    manager = FakeCaptureManager()
    watcher = DomWatcher(manager)
    watcher._active = True
    watcher._page = object()
    await watcher._on_dom_mutation()
    assert manager._dirty is True
