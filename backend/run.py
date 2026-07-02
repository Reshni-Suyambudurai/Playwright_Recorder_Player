"""
Entry point for running the backend server.
Sets the correct asyncio event loop policy BEFORE uvicorn starts.
On Windows, ProactorEventLoop is required for Playwright subprocess support.
"""
import asyncio
import sys

# MUST be set before any uvicorn/asyncio imports create an event loop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    print("Windows: ProactorEventLoop policy set")

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,  # reload=True creates subprocesses that reset the loop policy
    )
