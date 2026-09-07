"""
run_mcp.py — Startup script for MCP v2 server.

This launches the thin proxy that forwards MCP tool calls to the FastAPI backend.
The backend must be running on http://localhost:8001 (or custom URL via env var).

Usage:
    python run_mcp.py                    # Default: http://localhost:8001
    BACKEND_URL=http://localhost:9000 python run_mcp.py  # Custom backend
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

# Add backend directory to sys.path so mcp_server package can be imported
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Setup logging: file + stderr
rotating_handler = logging.handlers.RotatingFileHandler(
    "mcp_server.log",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
)
rotating_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(name)s - %(levelname)s - %(message)s")
)

stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(name)s - %(levelname)s - %(message)s")
)

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(rotating_handler)
root_logger.addHandler(stderr_handler)

logger = logging.getLogger("mcp_server.run_mcp")

if __name__ == "__main__":
    from mcp_server.server import mcp, init_proxy
    
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8001")
    
    logger.info("=" * 70)
    logger.info("MCP Playback Server v2 (Thin Proxy)")
    logger.info("=" * 70)
    logger.info(f"Backend URL: {backend_url}")
    logger.info("MCP Protocol: stdin/stdout (JSON-RPC 2.0)")
    logger.info("Tools: start_playback, stop_playback")
    logger.info("=" * 70)
    
    try:
        # Initialize proxy with configured backend URL
        proxy = init_proxy(backend_url)
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        import asyncio
        if proxy is not None:
            asyncio.run(proxy.close())
        logger.info("MCP Playback Server Stopped")
        sys.exit(0)

