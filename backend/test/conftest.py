import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# Lib Used for testing:
# pytest
# pytest-asyncio
# pytest-mock
# pytest-cov
# httpx

# Important libs used for this integration testing:

# pytest
# pytest-asyncio
# pytest-mock
# pytest-cov
# fastapi
# starlette
# httpx (pinned to 0.27.2 for compatibility with current starlette test client)

# Command 
# python -m pytest backend/test -q