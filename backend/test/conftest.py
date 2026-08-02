import sys
from pathlib import Path


# Ensure "app" imports resolve when running tests from repo root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class FakeWebSocket:
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    async def send_json(self, message):
        if self.fail:
            raise RuntimeError("send failed")
        self.messages.append(message)
