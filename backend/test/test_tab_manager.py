import pytest

from app.models.session import RecordingSession
from app.utils import tab_manager


class DummyPage:
    def __init__(self, url="https://example.com"):
        self.url = url


class DummyWatcher:
    def __init__(self):
        self.detached = False

    async def detach(self):
        self.detached = True


def test_next_tab_id():
    session = RecordingSession(session_id="s1")
    session.tabs = {"tab-1": DummyPage()}
    assert tab_manager.next_tab_id(session) == "tab-2"


def test_register_tab():
    session = RecordingSession(session_id="s1")
    page = DummyPage("https://a.com")
    tab_manager.register_tab(session, page, "tab-1")
    assert session.tabs["tab-1"] is page


def test_get_active_page():
    session = RecordingSession(session_id="s1")
    page = DummyPage()
    session.tabs["tab-1"] = page
    session.active_tab_id = "tab-1"
    assert tab_manager.get_active_page(session) is page


def test_switch_tab():
    session = RecordingSession(session_id="s1")
    page = DummyPage()
    session.tabs["tab-1"] = page
    switched = tab_manager.switch_tab(session, "tab-1")
    assert switched is page


@pytest.mark.asyncio
async def test_detach_all_watchers():
    session = RecordingSession(session_id="s1")
    watcher = DummyWatcher()
    session.tab_watchers["tab-1"] = watcher
    await tab_manager.detach_all_watchers(session)
    assert watcher.detached is True
