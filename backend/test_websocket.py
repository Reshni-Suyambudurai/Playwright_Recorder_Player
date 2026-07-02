"""
WebSocket testing guide and example client.

Usage:
    1. Start the backend: python -m app.main
    2. In another terminal, run this file: python test_websocket.py
    3. This will start two WebSocket clients connecting to the same session
"""
import asyncio
import websockets
import json
from datetime import datetime


async def test_single_client(session_id: str, client_name: str):
    """Test a single WebSocket client."""
    uri = f"ws://localhost:5000/ws/{session_id}"
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"\n[{client_name}] Connected to session: {session_id}")
            
            # Send HELLO
            hello_msg = {
                "event_type": "HELLO",
                "data": {
                    "client_id": client_name,
                    "session_id": session_id
                }
            }
            await websocket.send(json.dumps(hello_msg))
            print(f"[{client_name}] Sent HELLO")
            
            # Receive WELCOME
            welcome = await websocket.recv()
            print(f"[{client_name}] Received: {welcome}")
            
            # Send PING
            await asyncio.sleep(1)
            ping_msg = {
                "event_type": "PING",
                "data": {
                    "timestamp": datetime.now().isoformat()
                }
            }
            await websocket.send(json.dumps(ping_msg))
            print(f"[{client_name}] Sent PING")
            
            # Receive PONG
            pong = await websocket.recv()
            print(f"[{client_name}] Received: {pong}")
            
            # Keep connection open for a bit
            await asyncio.sleep(2)
            print(f"[{client_name}] Closing connection")
    
    except Exception as e:
        print(f"[{client_name}] Error: {str(e)}")


async def test_invalid_session():
    """Test connection with invalid session ID."""
    uri = "ws://localhost:5000/ws/invalid-session-id"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("[INVALID_TEST] Connection accepted (should have been rejected)")
    except Exception as e:
        print(f"[INVALID_TEST] Connection rejected (expected): {str(e)}")


async def test_malformed_json(session_id: str):
    """Test sending malformed JSON."""
    uri = f"ws://localhost:5000/ws/{session_id}"
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"\n[MALFORMED_TEST] Connected to session: {session_id}")
            
            # Send malformed JSON
            await websocket.send("{invalid json")
            print(f"[MALFORMED_TEST] Sent malformed JSON")
            
            # Receive error response
            error = await websocket.recv()
            print(f"[MALFORMED_TEST] Received: {error}")
    
    except Exception as e:
        print(f"[MALFORMED_TEST] Error: {str(e)}")


async def test_multi_client():
    """Test multiple clients connecting to the same session."""
    # Session ID must exist from REST API call first
    session_id = "test-session"
    
    print("=" * 60)
    print("WebSocket Multi-Client Test")
    print("=" * 60)
    
    # Test invalid session first
    await test_invalid_session()
    
    # Test multi-client connection
    print("\n--- Testing Multi-Client Connection ---")
    await asyncio.gather(
        test_single_client(session_id, "Client-1"),
        test_single_client(session_id, "Client-2")
    )
    
    # Test malformed JSON
    print("\n--- Testing Malformed JSON ---")
    await test_malformed_json(session_id)
    
    print("\n" + "=" * 60)
    print("Tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    print("Prerequisites:")
    print("1. Start backend: python -m app.main")
    print("2. Create a session via REST API: POST http://localhost:5000/recording/start")
    print("3. Copy the session_id and update the test_multi_client() function")
    print("\nThen run: python test_websocket.py")
