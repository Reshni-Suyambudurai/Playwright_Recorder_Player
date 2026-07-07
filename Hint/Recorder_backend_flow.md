# Playwright Recorder — Backend Flow

## Overview

The backend is a **FastAPI + Playwright** server. It manages a headless Chromium browser per session, streams live screenshots over WebSocket, records every user action as structured steps, and saves the final recording to SQLite + disk.

---

## Startup (`run.py`)

1. Clears `debug.log` so every run starts with a fresh log file.
2. Sets `WindowsProactorEventLoopPolicy` (required for Playwright subprocess support on Windows).
3. Starts **Uvicorn** on port **8001** with `reload=False`.

---

## App Initialisation (`app/main.py`)

On startup, the following singletons are created and wired together:

| Service | Role |
|---|---|
| `SessionManager` | In-memory dict of active `RecordingSession` objects |
| `BrowserService` | Launches/closes Playwright Chromium, takes JPEG screenshots |
| `ConnectionManager` | Tracks WebSocket connections keyed by `session_id:client_id` |
| `ScreenshotService` | Calls `BrowserService.take_screenshot()` and sends a `FRAME` event |
| `WebSocketHandler` | Routes all WebSocket events to handler methods |
| `DatabaseService` | SQLite via `aiosqlite` — persists finished recordings |

The recording REST router is mounted at `/recording`.

---

## REST API (`app/api/recording.py`)

| Endpoint | Description |
|---|---|
| `POST /recording/start` | Launches a new headless Chromium browser, creates a `RecordingSession`, returns `session_id` |
| `POST /recording/stop` | Detaches DomWatcher, closes browser, removes session |
| `GET /recording/list` | Lists all saved recordings from SQLite |
| `GET /recording/{id}` | Returns full JSON for one recording |
| `DELETE /recording/{id}` | Deletes a recording from SQLite |

---

## WebSocket Lifecycle (`/ws/{session_id}`)

```
Client                          Backend
  |                                |
  |-- HELLO { client_id } ------->|  register client_id -> WebSocket mapping
  |<-- WELCOME -------------------|
  |                                |
  |-- START_RECORDING { url } --->|  navigate, attach DomWatcher, send first FRAME
  |<-- RECORDING_STARTED ---------|
  |<-- FRAME (first screenshot) --|
  |                                |
  |  [user actions: click/type/scroll/key]
  |                                |
  |-- CLICK_ACTION { x, y } ----->|  perform click, record step
  |<-- ACTION_DONE ---------------|  (returned immediately, frame pending)
  |<-- FRAME (after load) --------|  (_bg_screenshot waits for full page load)
  |<-- FRAME (follow-up) ---------|  (DomWatcher: 1.2s after, catches lazy content)
  |                                |
  |-- STOP_RECORDING ------------->|  serialize steps, save to SQLite + disk
  |<-- RECORDING_STOPPED ---------|
```

---

## Recording Session Model

A `RecordingSession` holds:
- `session_id`, `page`, `browser`, `browser_context`
- `current_url`, `recording_steps: list[RecordingStep]`
- `recording_id`, `recording_name`, `recording_description`, `recording_intent`
- `dom_watcher: DomWatcher` — the active watcher for the primary tab
- `tabs`, `tab_watchers`, `tab_meta`, `active_tab_id` — multi-tab state
- `client_id` — registered after HELLO handshake

---

## Action Handling — Fire-and-Forget Pattern

Every action (CLICK, TYPE, SCROLL, KEY) follows this pattern:

```
1. Perform the browser action (click/type/scroll/key)
2. Record the step into session.recording_steps  (isolated try/except)
3. asyncio.ensure_future(_bg_screenshot(...))    ← background, non-blocking
4. Return ACTION_DONE immediately to frontend
```

`_bg_screenshot` runs independently:
- Suppresses DomWatcher via `dom_watcher.suppress_external(True)`
- Waits for full page `load` (up to 5s) for CLICK/KEY(Enter), or a fixed sleep for TYPE/SCROLL
- Takes screenshot, sends FRAME with `source: "CLICK"` / `"TYPE"` / etc.
- Lifts suppression via `dom_watcher.suppress_external(False)`

---

## DomWatcher (`app/services/dom_watcher.py`)

Attached once per tab when recording starts. Sends frames independently of user actions.

**Triggers:**
- `page.on("load")` — full page load / reload
- `page.on("domcontentloaded")` — DOM parsed
- `MutationObserver` (JS injected via `add_init_script`) — any DOM tree change

**Debounce + Capture Flow:**
```
mutation/load fires
  -> _schedule_capture() — cancel pending debounce, schedule new one
  -> wait 300ms (DEBOUNCE_MS)
  -> if _in_flight: sleep 0.6s, reschedule (never drop)
  -> wait_for_load_state("load", timeout=5s)
  -> capture_and_send(caller="DOM-WATCHER")            ← FRAME source: "DOM-WATCHER"
  -> sleep 1.2s
  -> capture_and_send(caller="DOM-WATCHER-FOLLOWUP")   ← catches lazy/embedded content
```

**Suppression (shared `_in_flight`):**
- `_bg_screenshot` calls `suppress_external(True/False)` to prevent DomWatcher racing with action screenshots.
- When suppressed and a debounce fires, DomWatcher reschedules (waits 0.6s) instead of dropping.

---

## Screenshot Pipeline (`app/services/screenshot_service.py`)

```
capture_and_send(page, session_id, client_id, caller)
  -> BrowserService.take_screenshot(page)
      -> page.screenshot(type="jpeg", quality=60, clip 1280x720)
      -> base64 encode -> "data:image/jpeg;base64,..."
  -> build FRAME event:
      {
        event_type: "FRAME",
        data: {
          image: "<base64>",
          width: 1280,
          height: 720,
          timestamp: "<ISO>",
          source: "<caller>"   <- "CLICK" | "DOM-WATCHER" | "DOM-WATCHER-FOLLOWUP" | etc.
        }
      }
  -> ConnectionManager.send_to_client(session_id, client_id, frame_event)
```

The `source` field identifies which component sent the frame (useful for testing/debugging).

---

## Recording Steps (`app/models/recording.py`)

Each user action appends a `RecordingStep` to `session.recording_steps`:

| Step type | Captured fields |
|---|---|
| `NAVIGATE` | url, pageUrl, pageTitle, viewport, tab_id |
| `CLICK` | pageUrl, pageTitle, coords (x,y), button, selector, label, tag |
| `TYPE` | pageUrl, text, selector, label, tag, isPassword |
| `SCROLL` | pageUrl, coords, deltaX, deltaY |
| `KEY` | pageUrl, text (key name) |

Steps are grouped by tab: `{ "tab-1": [[step], [step], ...], "tab-2": [...] }`.

---

## Stop Recording (`handle_stop_recording`)

1. Detach DomWatcher
2. Build `Recording` object from `session.recording_steps`
3. Save JSON to `backend/storage/recordings/<id>.json` (file backup)
4. Save to SQLite via `DatabaseService.save_recording()`
5. Return `RECORDING_STOPPED` with step summary list
6. Reset `session.recording_steps`, `recording_id`, `recording_name`

---

## Multi-Tab Support

When the browser opens a new tab (`browser_context.on("page")`):
1. `_on_new_tab` fires automatically
2. A new `DomWatcher` is created and attached to the new page
3. The triggering step gets `isTriggerNewTab: true`
4. A `NAVIGATE` step is appended for the new tab
5. `TAB_OPENED` event sent to frontend with updated tab list
6. Active tab switches automatically to the new one

Tab switch (`SWITCH_TAB`) updates `session.active_tab_id`, sends a fresh frame from the switched-to tab.

---

## File Structure

```
backend/
├── run.py                        # Entry point: clears log, sets loop policy, starts uvicorn
├── app/
│   ├── main.py                   # FastAPI app factory, service wiring, WebSocket endpoint
│   ├── api/
│   │   └── recording.py          # REST: /recording/start|stop|list|{id}
│   ├── websocket/
│   │   ├── websocket_handler.py  # All WebSocket event handlers + _bg_screenshot
│   │   ├── websocket_events.py   # EventType constants + Pydantic event models
│   │   └── connection_manager.py # session_id:client_id -> WebSocket mapping
│   ├── services/
│   │   ├── session_manager.py    # Create/get/remove RecordingSession
│   │   ├── browser_service.py    # Launch browser, take_screenshot, perform actions
│   │   ├── screenshot_service.py # capture_and_send -> FRAME event
│   │   ├── dom_watcher.py        # MutationObserver + debounce + follow-up frame
│   │   ├── recording_storage.py  # Save/load recording JSON files on disk
│   │   └── database.py           # SQLite via aiosqlite
│   ├── models/
│   │   └── recording.py          # RecordingStep, RecordingMeta, Recording, Viewport
│   └── utils/
│       ├── tab_manager.py        # register_tab, switch_tab, get_active_page
│       └── selector_builder.py   # Build CSS/XPath selectors from element info
└── storage/recordings/           # JSON backup files per recording
```

---

## Known Minor Issue

`handle_pong` in `websocket_handler.py` uses `print()` instead of `logger`. No functional impact but inconsistent with the rest of the codebase logging.
