"""API routes module"""
from .browser_routes import router as browser_router
from .navigation_routes import router as navigation_router
from .screenshot_routes import router as screenshot_router
from .dom_routes import router as dom_router
from .health_routes import router as health_router
from .recording_routes import router as recording_router
from .playback_routes import router as playback_router

__all__ = [
    "browser_router",
    "navigation_router",
    "screenshot_router",
    "dom_router",
    "health_router",
    "recording_router",
    "playback_router",
]
