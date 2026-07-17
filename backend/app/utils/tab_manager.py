"""
TabManager — helpers for managing multiple Playwright pages (tabs) per session.

This file manages browser tabs (open, switch, get active tab, and clean up tab watchers) during a recording session.

It doesn't open tabs or close tabs itself. It only manages information about them.
"""
import logging
from playwright.async_api import Page
from app.models.session import RecordingSession

logger = logging.getLogger("playwright_recorder.utils.tab_manager")


def next_tab_id(session: RecordingSession) -> str:
    """Return the next sequential tab ID (tab-1, tab-2, ...)."""
    return f"tab-{len(session.tabs) + 1}"


def register_tab(session: RecordingSession, page: Page, tab_id: str) -> None:
    """Store a new page under tab_id and update meta."""
    session.tabs[tab_id] = page
    session.tab_meta[tab_id] = {"title": "", "url": page.url}
    logger.info(f"Tab registered: {tab_id}  url={page.url}")


def get_active_page(session: RecordingSession) -> Page | None:
    """Return the currently active Playwright Page, or None."""
    return session.tabs.get(session.active_tab_id)


def switch_tab(session: RecordingSession, tab_id: str) -> Page | None:
    """Set active_tab_id and return the new active Page."""
    if tab_id not in session.tabs:
        return None
    session.active_tab_id = tab_id
    logger.info(f"Switched to tab: {tab_id}")
    return session.tabs[tab_id]


async def detach_all_watchers(session: RecordingSession) -> None:
    """Detach every DomWatcher attached to any tab."""
    for tab_id, watcher in list(session.tab_watchers.items()):
        try:
            await watcher.detach()
        except Exception as e:
            logger.warning(f"Error detaching watcher for {tab_id}: {e}")
    session.tab_watchers.clear()
