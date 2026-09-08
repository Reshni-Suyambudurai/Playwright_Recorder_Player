"""
MCP Server Package — Model Context Protocol v2 server for Playwright playback.
Thin proxy that forwards tool calls to FastAPI backend via HTTP.
"""

from mcp_server.server import mcp, init_proxy

__all__ = [
    "mcp",
    "init_proxy",
]

