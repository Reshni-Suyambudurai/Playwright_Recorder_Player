"""
FastAPI Application - Playwright Recorder/Player Backend
Using Synchronous Playwright API (No asyncio complexity!)

Architecture:
  - main.py: Application setup and router registration
  - routes/: API endpoint implementations (organized by function)
  - models/: Pydantic request/response schemas
  - services/: Browser automation service
  - static/: Web UI interface
"""
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from pathlib import Path
from app.routes import (
    browser_router,
    navigation_router,
    screenshot_router,
    dom_router,
    health_router,
    recording_router,
    playback_router,
)
from app.services.launchWeb import browser_manager

# Configure logging to debug.log file
log_file = Path(__file__).parent.parent / "debug.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(log_file)),
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Playwright Recorder Player",
    description="Web automation with Playwright and FastAPI",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# Mount static files (web UI)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Register API routers
app.include_router(browser_router, prefix="/api")
app.include_router(navigation_router, prefix="/api")
app.include_router(screenshot_router, prefix="/api")
app.include_router(dom_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(recording_router, prefix="/api")
app.include_router(playback_router, prefix="/api")

# ==================== ROOT ROUTES ====================

@app.get("/")
async def root():
    """Serve the main HTML page"""
    html_file = static_dir / "index.html"
    if html_file.exists():
        return FileResponse(str(html_file))
    return {"error": "index.html not found"}

# ==================== STARTUP & SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Application startup")
    print("[OK] Playwright Recorder Player API started")
    print(f"[OK] Viewport: {browser_manager.viewport['width']}x{browser_manager.viewport['height']}")
    print("[OK] Using Synchronous Playwright API (No asyncio issues!)")
    print("[OK] API Docs: http://localhost:8000/api/docs")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("Application shutdown")
    await run_in_threadpool(browser_manager.close)
    print("[OK] Browser closed and resources cleaned up")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
