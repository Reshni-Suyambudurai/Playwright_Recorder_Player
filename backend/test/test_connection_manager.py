import pytest

from app.websocket.connection_manager import ConnectionManager


@pytest.mark.asyncio
async def test_connect_adds_websocket():
    manager = ConnectionManager()
    ws = object()
    await manager.connect("s1", ws)
    assert manager.get_connection_count("s1") == 1


def test_register_client_maps_socket():
    manager = ConnectionManager()
    ws = object()
    manager.register_client("s1", "c1", ws)
    assert manager._client_connections["s1:c1"] is ws


@pytest.mark.asyncio
async def test_disconnect_removes_mappings():
    manager = ConnectionManager()
    ws = object()
    await manager.connect("s1", ws)
    manager.register_client("s1", "c1", ws)
    await manager.disconnect(ws)
    assert manager.get_connection_count("s1") == 0


@pytest.mark.asyncio
async def test_send_to_client_success():
    manager = ConnectionManager()

    class WS:
        async def send_json(self, message):
            return None

    ws = WS()
    manager.register_client("s1", "c1", ws)
    sent = await manager.send_to_client("s1", "c1", {"ok": True})
    assert sent is True


@pytest.mark.asyncio
async def test_broadcast_to_session_sends_message():
    manager = ConnectionManager()

    class WS:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    ws = WS()
    await manager.connect("s1", ws)
    await manager.broadcast_to_session("s1", {"event": "x"})
    assert ws.messages[0]["event"] == "x"


@pytest.mark.asyncio
async def test_broadcast_all_sends_to_all_sessions():
    manager = ConnectionManager()

    class WS:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    ws1, ws2 = WS(), WS()
    await manager.connect("s1", ws1)
    await manager.connect("s2", ws2)
    await manager.broadcast_all({"event": "all"})
    assert ws1.messages and ws2.messages


@pytest.mark.asyncio
async def test_get_session_connections_returns_list():
    manager = ConnectionManager()
    ws = object()
    await manager.connect("s1", ws)
    assert ws in manager.get_session_connections("s1")


@pytest.mark.asyncio
async def test_get_active_sessions_contains_session():
    manager = ConnectionManager()
    await manager.connect("s1", object())
    assert "s1" in manager.get_active_sessions()


@pytest.mark.asyncio
async def test_get_session_id_returns_expected_value():
    manager = ConnectionManager()
    ws = object()
    await manager.connect("s1", ws)
    assert manager.get_session_id(ws) == "s1"


@pytest.mark.asyncio
async def test_get_connection_count_returns_count():
    manager = ConnectionManager()
    await manager.connect("s1", object())
    assert manager.get_connection_count("s1") == 1


@pytest.mark.asyncio
async def test_get_total_connection_count_returns_total():
    manager = ConnectionManager()
    await manager.connect("s1", object())
    await manager.connect("s2", object())
    assert manager.get_total_connection_count() == 2
