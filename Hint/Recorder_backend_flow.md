# Playwright Recorder — Backend Flow

## Overview

The backend is a **FastAPI + Playwright** server. It manages a headless Chromium browser per recording session, streams live screenshots over WebSocket, records every user action as structured steps, and saves the final recording to SQLite + disk.

Screenshot streaming is handled by the **CaptureManager** — a per-session coordinator that owns all settle timing, the asyncio Lock, and a background dirty-flag worker for DOM mutations.

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
| `BrowserService` | Launches/closes Playwright Chromium, performs clicks/types/scrolls |
| `ConnectionManager` | Tracks WebSocket connections keyed by `session_id:client_id` |
| `ScreenshotService` | Calls `BrowserService.take_screenshot()` and sends a `FRAME` event |
| `WebSocketHandler` | Routes all WebSocket events to handler methods |
| `DatabaseService` | SQLite via `aiosqlite` — persists finished recordings |

The recording REST router is mounted at `/recording`.  
The WebSocket endpoint `/ws/{session_id}` is registered directly in `main.py`.

---

## REST API (`app/api/recording.py`)

| Endpoint | Description |
|---|---|
| `POST /recording/start` | Launches a new headless Chromium browser, creates a `RecordingSession`, returns `session_id` |
| `POST /recording/stop` | Detaches DomWatcher + CaptureManager worker, closes browser, removes session |
| `GET /recording/list` | Lists all saved recordings from SQLite |
| `GET /recording/{id}` | Returns full JSON for one recording |
| `DELETE /recording/{id}` | Deletes a recording from SQLite |

---

## WebSocket Lifecycle (`/ws/{session_id}`)

Handled by `app/websocket/websocket_handler.py`.

```
Client                               Backend (websocket_handler.py)
  |                                        |
  |-- HELLO { client_id } --------------->|  register_client(session_id, client_id, ws)
  |<-- WELCOME ----------------------------|  reply WELCOME
  |                                        |
  |-- START_RECORDING { url, name } ----->|  handle_start_recording()
  |                                        |   navigate_to_url(page, url)
  |                                        |   CaptureManager(screenshot_service, session_id, client_id)
  |                                        |   DomWatcher(cap_mgr) → attach(page)
  |                                        |     └─ starts CaptureManager worker loop
  |                                        |   cap_mgr.request(page, MANUAL) → first FRAME
  |<-- RECORDING_STARTED ------------------|
  |<-- FRAME (first screenshot) ----------|
  |                                        |
  |  [user actions via REST or WebSocket]  |
  |                                        |
  |-- CLICK_ACTION { x, y } ------------>|  handle_click_action()
  |                                        |   build_selector(page, x, y)
  |                                        |   if is_input → INPUT_DETECTED (no click)
  |                                        |   else → perform_click(page, x, y)
  |                                        |        → record CLICK step
  |                                        |        → cap_mgr.request(ACTION_CLICK) [async]
  |<-- ACTION_DONE / INPUT_DETECTED ------|  returned immediately (frame pending)
  |<-- FRAME (300ms after click) ---------|  CaptureManager FIXED_DELAY(300ms) → screenshot
  |<-- FRAME (next DOM worker tick) ------|  DomWatcher dirty flag → worker fires at 300ms
  |                                        |
  |-- TYPE_ACTION { text, selector } ---->|  handle_type_action()
  |                                        |   perform_type(page, selector, text)
  |                                        |   record TYPE step
  |                                        |   cap_mgr.request(ACTION_TYPE) [async]
  |<-- ACTION_DONE ----------------------|
  |<-- FRAME (300ms after type) ----------|
  |                                        |
  |-- SCROLL_ACTION { deltaY } ---------->|  handle_scroll_action()
  |                                        |   perform_scroll(page, x, y, dx, dy)
  |                                        |   record SCROLL step
  |                                        |   cap_mgr.request(ACTION_SCROLL) [async]
  |<-- ACTION_DONE ----------------------|
  |<-- FRAME (immediate, NONE settle) ----|
  |                                        |
  |-- KEY_ACTION { key } --------------->|  handle_key_action()
  |                                        |   keyboard.press(key)
  |                                        |   record KEY step
  |                                        |   cap_mgr.request(ACTION_CLICK or ACTION_TYPE)
  |<-- ACTION_DONE ----------------------|
  |                                        |
  |-- STOP_RECORDING -------------------->|  handle_stop_recording()
  |                                        |   DomWatcher.detach() → cap_mgr.stop()
  |                                        |   serialize steps → Recording JSON
  |                                        |   save to disk + SQLite
  |<-- RECORDING_STOPPED -----------------|
```

---

## CaptureManager (`app/services/capture_manager.py`)

**One instance per session** — created in `handle_start_recording`, stored in `session.capture_manager`.

### Responsibility
- Owns the `asyncio.Lock` that serialises all CDP screenshot calls.
- Owns the `_dirty` flag and background worker loop for DOM mutation frames.
- Applies per-reason settle strategies before taking a screenshot.

### Settle Strategies (`SettleStrategy` enum)

| Strategy | Behaviour |
|---|---|
| `NONE` | Capture immediately |
| `FIXED_DELAY(ms)` | `await asyncio.sleep(ms / 1000)` then capture |
| `WAIT_FOR_NAV(ms)` | `wait_for_load_state("domcontentloaded", timeout=ms)` |
| `WAIT_FOR_IDLE(ms)` | `wait_for_load_state("networkidle", timeout=ms)` |

### Default Settle per Reason

| CaptureReason | Settle | Delay |
|---|---|---|
| `ACTION_CLICK` | `FIXED_DELAY` | 300ms |
| `ACTION_TYPE` | `FIXED_DELAY` | 300ms |
| `ACTION_SCROLL` | `NONE` | 0ms |
| `STEP_DONE` | `FIXED_DELAY` | 300ms |
| `PAUSE_CLICK` | `FIXED_DELAY` | 300ms |
| `PAUSE_SCROLL` | `NONE` | 0ms |
| `PAUSE_TYPE` | `FIXED_DELAY` | 300ms |
| `DOM_MUTATION` | `NONE` | 0ms |
| `ERROR` | `NONE` | 0ms |
| `MANUAL` | `NONE` | 0ms |

### Priority Model

```
HIGH priority (ACTION_CLICK, TYPE, SCROLL, STEP_DONE, PAUSE_*, ERROR, MANUAL)
  → self._dirty = False   (suppress pending DOM capture for this tick)
  → acquire asyncio.Lock
  → apply settle strategy
  → take screenshot → send FRAME
  → release lock

LOW priority (DOM_MUTATION)
  → self._dirty = True    (zero tasks, zero lock contention)
  → returns immediately
  → background worker fires at next 300ms tick if still dirty
```

### DOM Capture Worker Loop

```python
# Started by DomWatcher.attach(), stopped by DomWatcher.detach()
while True:
    await asyncio.sleep(300ms)
    if self._dirty:
        self._dirty = False
        acquire lock → screenshot → FRAME
```

This guarantees at most one DOM frame per 300ms regardless of mutation frequency.

---

## DomWatcher (`app/services/dom_watcher.py`)

**Pure event detector** — no timing, no scheduling, no lock ownership.

```
attach(page, session_id, client_id)
  │
  ├─ page.on("load") → _on_page_event → _dirty = True
  ├─ page.on("domcontentloaded") → _on_page_event → _dirty = True
  │
  ├─ page.expose_function("__domChanged__", _on_dom_mutation)
  ├─ page.add_init_script(MutationObserver script)  ← survives navigation
  ├─ page.evaluate(MutationObserver script)          ← current page immediately
  │
  └─ capture_manager.start_worker(page)              ← launches background loop

_on_dom_mutation (called from JS MutationObserver)
  └─ capture_manager._dirty = True   ← only this — no tasks, no awaits

detach()
  └─ capture_manager.stop()          ← cancels worker task, clears dirty flag
```

---

## Action Handling — Fire-and-Forget Pattern

Every action (CLICK, TYPE, SCROLL, KEY) in `websocket_handler.py` follows this pattern:

```
1. Perform the browser action (click/type/scroll/key)
2. Record the step into session.recording_steps   (isolated try/except)
3. asyncio.ensure_future(cap_mgr.request(...))    ← background, non-blocking
4. Return ACTION_DONE immediately to frontend
```

`cap_mgr.request()` acquires the lock, applies FIXED_DELAY(300ms), takes the screenshot, and sends FRAME — all in the background while the frontend has already received ACTION_DONE.

---

## Screenshot Pipeline (`app/services/screenshot_service.py`)

```
capture_and_send(page, session_id, client_id, caller)
  │
  ├─ BrowserService.take_screenshot(page)
  │     ├─ CDP screenshot request → browser (logged: "→ sending CDP screenshot request")
  │     ├─ browser returns JPEG bytes (~30–50 KB) (logged: "← browser returned N bytes in Xms")
  │     └─ base64.b64encode() (logged: "base64 encode done in Xms")
  │
  ├─ Build FRAME event:
  │     { event_type: "FRAME", data: { image: "data:image/jpeg;base64,...",
  │                                    width: 1280, height: 720,
  │                                    source: "<caller>" } }
  │
  └─ ConnectionManager.send_to_client(session_id, client_id, frame_event)
        └─ WebSocket.send_json()  (logged: "ws_send=Xms  total=Xms")
```

The `source` field identifies which component triggered the frame:
`"CLICK"` | `"TYPE"` | `"SCROLL"` | `"STEP"` | `"DOM-WATCHER"` | `"MANUAL"` | `"ERROR"` | etc.

---

## Recording Steps (`app/models/recording.py`)

Each user action appends a `RecordingStep` to `session.recording_steps`:

| Step type | Captured fields |
|---|---|
| `NAVIGATE` | url, pageUrl, pageTitle, viewport, tab_id |
| `CLICK` | pageUrl, pageTitle, coords (x,y), button, selector, label |
| `TYPE` | pageUrl, text, selector, label, isPassword |
| `SCROLL` | pageUrl, coords, deltaX, deltaY |
| `KEY` | pageUrl, text (key name) |

Steps are grouped by tab: `{ "tab-1": [[step], [step], ...], "tab-2": [...] }`.

---

## Stop Recording (`handle_stop_recording`)

1. `DomWatcher.detach()` → `cap_mgr.stop()` (worker cancelled)
2. Build `Recording` object from `session.recording_steps`
3. Save JSON to `backend/storage/recordings/<id>.json` (file backup)
4. Save to SQLite via `DatabaseService.save_recording()`
5. Return `RECORDING_STOPPED` with step summary list
6. Reset `session.recording_steps`, `recording_id`, `recording_name`

---

## Multi-Tab Support

When the browser opens a new tab (`browser_context.on("page")`):
1. `_on_new_tab` fires automatically
2. A new `CaptureManager` + `DomWatcher` is created and attached to the new page
3. The triggering step gets `isTriggerNewTab: true`
4. A `NAVIGATE` step is appended for the new tab
5. `TAB_OPENED` event sent to frontend
6. Active tab switches to the new one automatically

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
│   │   ├── websocket_handler.py  # All WebSocket event handlers — action dispatch, step recording
│   │   ├── websocket_events.py   # EventType constants + Pydantic event models
│   │   └── connection_manager.py # session_id:client_id -> WebSocket mapping
│   ├── services/
│   │   ├── session_manager.py    # Create/get/remove RecordingSession
│   │   ├── browser_service.py    # Launch browser, take_screenshot, perform_click/type/scroll
│   │   ├── screenshot_service.py # capture_and_send() → FRAME event with timing logs
│   │   ├── capture_manager.py    # Per-session screenshot coordinator (lock + dirty worker)
│   │   ├── dom_watcher.py        # MutationObserver bridge → sets dirty flag on capture_manager
│   │   ├── recording_storage.py  # Save/load recording JSON files on disk
│   │   └── database.py           # SQLite via aiosqlite
│   ├── models/
│   │   ├── recording.py          # RecordingStep, RecordingMeta, Recording, Viewport, RecordingSession
│   │   └── playback.py           # PlaySession, PlayStatus
│   └── utils/
│       ├── tab_manager.py        # register_tab, switch_tab, get_active_page
│       └── selector_builder.py   # Build CSS/XPath selectors from element info at (x,y)
└── storage/recordings/           # JSON backup files per recording
```


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
