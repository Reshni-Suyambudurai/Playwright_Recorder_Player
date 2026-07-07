# Architecture Guide

A deep-dive into how the backend and frontend work, and what every file and folder does.

---

## How It All Works Together

```
Browser (Angular @ :8000)
        │
        │  HTTP  POST /recording/start  ──►  Creates session + launches Chromium
        │  HTTP  POST /recording/stop   ──►  Detaches DomWatcher → notifies client
        │                                   → closes Chromium → removes session
        │
        │  WebSocket  ws://localhost:8001/ws/{session_id}
        │  ┌──────────────────────────────────────────────────────┐
        │  │  Client → Server:  HELLO, NAVIGATE, CLICK_ACTION,   │
        │  │                    SCROLL_ACTION, TYPE_ACTION,       │
        │  │                    KEY_ACTION, START_RECORDING,      │
        │  │                    STOP_RECORDING, SWITCH_TAB, PING  │
        │  │                                                      │
        │  │  Server → Client:  WELCOME, FRAME, NAVIGATION_SUCCESS│
        │  │                    NAVIGATION_ERROR, ACTION_DONE,    │
        │  │                    INPUT_DETECTED, RECORDING_STARTED,│
        │  │                    RECORDING_STOPPED, TAB_OPENED,    │
        │  │                    TAB_SWITCHED, SESSION_CLOSED,     │
        │  │                    ERROR, PONG                       │
        │  └──────────────────────────────────────────────────────┘
        │
FastAPI Server (Python @ :8001)
        │
        ├──► Playwright controls a real Chromium browser (headless)
        ├──► DomWatcher captures screenshots on every DOM change (debounced 300 ms)
        └──► SQLite (via aiosqlite) persists recordings
```

**Full session flow:**

1. User clicks **Connect** → Angular calls `POST /recording/start`
2. Backend creates a session, launches headless Chromium, returns `session_id`
3. Angular opens a WebSocket; sends `HELLO`; server replies `WELCOME`
4. User navigates, clicks, types, scrolls — each action is sent as a WS event
5. Backend performs the action in Playwright; fire-and-forget `_bg_screenshot` waits for full `load` then sends a `FRAME` (JPEG base64)
6. `DomWatcher` independently watches for DOM mutations; sends a frame on settle + a follow-up frame 1.2s later to catch lazy-loaded content
7. Scroll events are **debounced 150 ms on the frontend** — accumulated deltas sent as one `SCROLL_ACTION`
8. User records actions via `START_RECORDING` / `STOP_RECORDING` — steps serialised to JSON and saved to SQLite + disk
9. When the session ends (via REST or WS disconnect) `DomWatcher` is detached before the browser closes; a `SESSION_CLOSED` event is pushed to the client

---

## Project Root

```
Playwright_Launch/
├── automation_frontend/   ← Angular 21 frontend
├── backend/               ← FastAPI + Playwright backend
├── database/              ← SQLite schema + DB file
├── Hint/                  ← Architecture docs (this file)
├── venv/                  ← Python virtual environment
├── requirements.txt       ← Python dependencies
├── debug.log              ← Live backend log (cleared on each run.py startup)
└── README.md
```

---

## Backend

### File & Folder Structure

```
backend/
├── run.py                         ← ONLY file you run; clears debug.log on startup
├── app/
│   ├── __init__.py
│   ├── main.py                    ← FastAPI app factory + service wiring
│   ├── api/
│   │   ├── __init__.py
│   │   └── recording.py           ← REST endpoints: /recording/start|stop|list|{id}
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── connection_manager.py  ← session_id:client_id → WebSocket registry
│   │   ├── websocket_events.py    ← EventType constants + Pydantic event models
│   │   └── websocket_handler.py   ← Routes all WS events + _bg_screenshot
│   ├── services/
│   │   ├── __init__.py
│   │   ├── browser_service.py     ← Playwright: launch, navigate, click, scroll, type, screenshot
│   │   ├── screenshot_service.py  ← capture_and_send: screenshot → FRAME WS event
│   │   ├── dom_watcher.py         ← MutationObserver + debounce + follow-up frame logic
│   │   ├── session_manager.py     ← In-memory dict of active RecordingSession objects
│   │   ├── recording_storage.py   ← Save/load Recording JSON to disk (file backup)
│   │   └── database.py            ← SQLite async via aiosqlite
│   ├── models/
│   │   ├── session.py             ← RecordingSession dataclass
│   │   └── recording.py           ← RecordingStep, RecordingMeta, Recording Pydantic models
│   └── utils/
│       ├── tab_manager.py         ← register_tab, switch_tab, get_active_page helpers
│       └── selector_builder.py    ← Build CSS/XPath selectors from element metadata
└── storage/
    └── recordings/                ← JSON backup files, one per recording (<id>.json)
```

---

### `run.py` — Entry Point

**The only file you run.**

1. Clears `debug.log` to empty (every run starts fresh)
2. Sets `asyncio.WindowsProactorEventLoopPolicy` on Windows (must happen before uvicorn creates its event loop — required by Playwright)
3. Starts uvicorn on port **8001** with `reload=False`

---

### `app/main.py` — App Factory

- Configures logging (console + `debug.log` append mode)
- Instantiates all service singletons and wires them: `SessionManager`, `BrowserService`, `ConnectionManager`, `ScreenshotService`, `WebSocketHandler`, `DatabaseService`
- Adds CORS middleware (`allow_origins=["*"]`)
- Mounts `/recording` REST router
- Registers `/ws/{session_id}` WebSocket endpoint
- Runs `db.init_db()` on startup via lifespan context

---

### `app/api/recording.py` — REST Endpoints

| Method | Path | What it does |
|--------|------|--------------|
| `POST` | `/recording/start` | Creates `RecordingSession`, calls `BrowserService.launch_browser()`, returns `session_id` |
| `POST` | `/recording/stop` | Detaches `DomWatcher`, sends `SESSION_CLOSED` WS event, closes browser, removes session |
| `GET` | `/recording/list` | Lists all recordings from SQLite |
| `GET` | `/recording/{id}` | Returns full JSON for one recording |
| `DELETE` | `/recording/{id}` | Deletes recording from SQLite |

---

### `app/websocket/connection_manager.py` — WebSocket Registry

Maintains two maps:
- `session_id → [WebSocket]` — for session-wide broadcast
- `"session_id:client_id" → WebSocket` — for targeted per-client sends

Key methods: `connect`, `disconnect`, `register_client`, `send_to_client`, `broadcast_to_session`

---

### `app/websocket/websocket_events.py` — Event Definitions

- `EventType` class — string constants for all 23 event names
- Pydantic models: `HelloData`, `WelcomeData`, `PingData`, `PongData`, `ErrorData`, `NavigateData`, `NavigationSuccessData`, `NavigationErrorData`, `WebSocketEvent`

---

### `app/websocket/websocket_handler.py` — Event Router + Action Handlers

Routes incoming WS events to handler methods and sends responses:

| Event | Handler | Description |
|-------|---------|-------------|
| `HELLO` | `handle_hello` | Validates session, registers client_id, replies `WELCOME` |
| `PING` | `handle_ping` | Replies `PONG` |
| `NAVIGATE` | `handle_navigate` | `page.goto()`, replies `NAVIGATION_SUCCESS/ERROR` |
| `START_RECORDING` | `handle_start_recording` | Navigate, attach `DomWatcher`, init step list, send first `FRAME` |
| `CLICK_ACTION` | `handle_click_action` | `page.mouse.click()`, record step (isolated try/except), fire `_bg_screenshot` |
| `TYPE_ACTION` | `handle_type_action` | Fill input via selector, record step, fire `_bg_screenshot` |
| `SCROLL_ACTION` | `handle_scroll_action` | `page.mouse.wheel()`, record step, fire `_bg_screenshot` |
| `KEY_ACTION` | `handle_key_action` | `page.keyboard.press()`, record step, fire `_bg_screenshot` |
| `PAGE_REFRESH` | `handle_page_refresh` | `page.reload()`, record NAVIGATE step, send `FRAME` |
| `PAGE_BACK` | `handle_page_back` | `page.go_back()`, record NAVIGATE step, send `FRAME` |
| `STOP_RECORDING` | `handle_stop_recording` | Detach watcher, serialise steps → JSON + SQLite, reply `RECORDING_STOPPED` |
| `SWITCH_TAB` | `handle_switch_tab` | Activate tab, send fresh `FRAME`, reply `TAB_SWITCHED` |

**`_bg_screenshot()`** — fire-and-forget background task:
- Suppresses `DomWatcher` via `dom_watcher.suppress_external(True)`
- Waits for full page `load` (CLICK/KEY with nav) or a fixed sleep (TYPE/SCROLL)
- Sends `FRAME` with `source` field identifying the caller
- Lifts suppression via `suppress_external(False)` in `finally`

---

### `app/services/browser_service.py` — Playwright Operations

| Method | Description |
|--------|-------------|
| `launch_browser()` | Starts Playwright, launches headless Chromium 1280×720, returns `(Browser, Context, Page)` |
| `navigate_to_url(page, url)` | `page.goto()` + best-effort `networkidle`; returns `{ url, title, status_code }` |
| `perform_click(page, x, y, button)` | `page.mouse.click()` at viewport coordinates |
| `perform_scroll(page, x, y, dx, dy)` | `page.mouse.move()` + `page.mouse.wheel()` |
| `perform_type(page, selector, text)` | `element.fill()` via CSS/id/xpath; handles `occurrence_index` for duplicate selectors |
| `perform_key(page, key)` | `page.keyboard.press()` for allowed keys |
| `take_screenshot(page)` | JPEG clip 1280×720 quality 60 → base64 data URI |
| `close_browser(browser)` | Graceful browser + Playwright shutdown |

---

### `app/services/screenshot_service.py` — Frame Sender

Single method `capture_and_send(page, session_id, client_id, caller)`:
1. Calls `BrowserService.take_screenshot()`
2. Builds FRAME event with `source: caller` (e.g. `"CLICK"`, `"DOM-WATCHER"`, `"DOM-WATCHER-FOLLOWUP"`)
3. Sends to client via `ConnectionManager.send_to_client()`

The `source` field lets you identify in DevTools which component sent each frame.

---

### `app/services/dom_watcher.py` — Auto Screenshot Trigger

Attached once per tab on `START_RECORDING`. Watches for DOM changes and sends frames independently of user actions.

**Triggers:** `page.on("load")`, `page.on("domcontentloaded")`, JS `MutationObserver` (via `add_init_script`)

**Debounce + capture flow:**
```
change fires → _schedule_capture() → cancel pending, schedule new
  → wait 300ms
  → if _in_flight: sleep 0.6s, reschedule (never drop)
  → wait_for_load_state("load", timeout=5s)
  → send FRAME  (source: "DOM-WATCHER")
  → sleep 1.2s
  → send FRAME  (source: "DOM-WATCHER-FOLLOWUP")  ← catches lazy/embedded content
```

**Suppression:** `suppress_external(True/False)` called by `_bg_screenshot` so both never fire simultaneously.

---

### `app/services/session_manager.py` — In-Memory Session Store

Holds `{ session_id → RecordingSession }` in a Python dict. Methods: `create_session`, `get_session`, `remove_session`, `list_active_sessions`, `list_all_sessions`.

---

### `app/services/database.py` — SQLite Persistence

Async SQLite via `aiosqlite`. DB file: `database/recorder.db`.

| Method | Description |
|--------|-------------|
| `init_db()` | Creates tables from `database/schema.sql` |
| `ensure_user(client_id)` | Upserts user row keyed by client ID |
| `save_recording(...)` | Inserts/replaces recording JSON blob |
| `list_recordings()` | Returns all recordings with metadata |
| `load_recording(record_id)` | Returns full parsed JSON for one recording |
| `delete_recording(record_id)` | Deletes one recording |

---

### `app/services/recording_storage.py` — File Backup

Serialises `Recording` objects to `storage/recordings/<id>.json`. Acts as disk backup alongside SQLite. Methods: `save`, `list_all`, `load`.

---

### `app/models/session.py` — Session Dataclass

`RecordingSession` holds all live state for one browser session:
- `browser`, `browser_context`, `page` — Playwright handles
- `dom_watcher` — active `DomWatcher` instance
- `recording_steps`, `recording_id`, `recording_name`, `recording_description`, `recording_intent`
- `tabs`, `tab_watchers`, `tab_meta`, `active_tab_id` — multi-tab tracking
- `client_id`, `current_url`

---

### `app/models/recording.py` — Recording Data Models

| Class | Purpose |
|-------|---------|
| `SelectorInfo` | CSS/XPath selector + `occurrence_index` |
| `Coords` | `{ x, y }` viewport coordinates |
| `Viewport` | `{ width: 1280, height: 720, deviceScaleFactor: 1.0 }` |
| `RecordingStep` | One recorded action (type, coords, selector, text, delta, button, …) |
| `RecordingMeta` | Flow metadata (id, title, description, intent, createdAt, updatedAt) |
| `Recording` | Full recording: `meta` + `steps: { tab_id → [[step_dict]] }` |

---

### `app/utils/tab_manager.py` — Tab Helpers

| Function | Description |
|----------|-------------|
| `next_tab_id(session)` | Returns `"tab-2"`, `"tab-3"`, etc. |
| `register_tab(session, page, tab_id)` | Stores page under tab_id, updates meta |
| `get_active_page(session)` | Returns currently active Playwright `Page` |
| `switch_tab(session, tab_id)` | Sets `active_tab_id`, returns new active page |
| `detach_all_watchers(session)` | Detaches every tab's `DomWatcher` |

---

### `app/utils/selector_builder.py` — Selector Builder

Builds the most reliable CSS/XPath selector for a clicked element based on metadata sent from the frontend (tag, id, class, label, text, occurrence index).

---

## Frontend

### File & Folder Structure

```
automation_frontend/src/
├── styles.css                    ← Global design system: CSS tokens, base reset, utilities
├── index.html                    ← Shell HTML; only <app-root>
├── main.ts                       ← Angular bootstrap
└── app/
    ├── app.ts                    ← Root component: imports Navbar, Sidebar, RouterOutlet
    ├── app.html                  ← Layout: sticky Navbar + Sidebar + <router-outlet>
    ├── app.css                   ← Shell flex layout styles
    ├── app.routes.ts             ← Route table: / flows/ runs/ settings/
    ├── app.config.ts             ← Angular providers (router, HttpClient)
    ├── app.spec.ts               ← Root component unit test
    │
    ├── components/
    │   ├── browser-view/         ← Live screenshot display + click/scroll/type forwarding
    │   ├── input-overlay/        ← Type-text prompt shown when input element is clicked
    │   ├── navbar/               ← Top bar: logo, title, dark/light toggle
    │   ├── recording-modal/      ← Modal for starting a recording (name, URL, intent)
    │   ├── sidebar/              ← Left nav: Browser, Flows, Runs, Settings links
    │   ├── spinner/              ← Reusable loading spinner
    │   ├── status/               ← Connection status indicator (Connected/Closed/Disconnected)
    │   ├── svg-icon/             ← Central SVG icon component (all SVGs live here)
    │   ├── tab-bar/              ← Multi-tab strip; clicking sends SWITCH_TAB
    │   └── tooltip/              ← Reusable tooltip directive/component
    │
    ├── pages/
    │   ├── browser/              ← / : Toolbar + BrowserView + live interaction
    │   ├── flows/                ← /flows: recorded flows list + step detail panel
    │   ├── runs/                 ← /runs: execution history (placeholder)
    │   └── settings/             ← /settings: app configuration (placeholder)
    │
    ├── services/
    │   ├── websocket.api.ts      ← Core WS layer: connect, send events, expose Observables
    │   ├── navigation.api.ts     ← navigate(url) wrapper; tracks navigation state signal
    │   ├── recordings.api.ts     ← HTTP: listRecordings(), getRecording(id), deleteRecording(id)
    │   ├── theme.api.ts          ← Dark/light toggle, persists to localStorage
    │   └── token-store.api.ts    ← Stores sensitive values (passwords) in memory only
    │
    ├── directives/
    │   └── tooltip/              ← Tooltip directive for hover hints
    │
    └── types/
        └── websocket.ts          ← All TS interfaces: EventType, ConnectionState, RecordingStep, etc.
```

---

### Shell Layout

```
┌────────────────────────────────────────────────────┐
│  Navbar  (sticky top bar)                          │
├──────────┬─────────────────────────────────────────┤
│          │                                         │
│ Sidebar  │   <router-outlet>                       │
│          │   active page renders here              │
│          │                                         │
└──────────┴─────────────────────────────────────────┘
```

---

### `app.routes.ts` — Route Table

| Path | Component | Purpose |
|------|-----------|---------|
| `/` | `BrowserPage` | Main browser control + live view |
| `/flows` | `FlowsPage` | Recorded flows list + detail |
| `/runs` | `RunsPage` | Execution history |
| `/settings` | `SettingsPage` | App configuration |
| `**` | redirect → `/` | Unknown routes fall back to home |

---

### Components

#### `browser-view/`
Displays live screenshots as `<img>`. Forwards clicks, scrolls (debounced 150ms + delta accumulation), and keyboard events as WS events. Shows loading overlay on `navigating$`, clears on next `FRAME`. Resets on `disconnected$`.

#### `input-overlay/`
Overlay that appears when backend sends `INPUT_DETECTED` (user clicked a text field). Collects typed text and sends `TYPE_ACTION`.

#### `navbar/`
Sticky top bar. Injects `ThemeApi`, renders logo/title and dark/light toggle button.

#### `recording-modal/`
Modal dialog for starting a new recording. Collects name, start URL, description, and intent before sending `START_RECORDING`.

#### `sidebar/`
Full-height left nav. Each item is a `routerLink` with an SVG icon. Active item highlighted via `routerLinkActive`.

#### `spinner/`
Standalone reusable loading spinner used while content is loading across the app.

#### `status/`
Reads signals from `WebsocketApi`. Three states:

| State | Colour | Condition |
|-------|--------|-----------|
| Connected | Green | `isConnected = true` |
| Session Closed | Dimmed | `isConnected = false` + `sessionClosed = true` |
| Disconnected | Red | `isConnected = false` + `sessionClosed = false` |

#### `svg-icon/`
Central SVG component. All SVG icons live here and are consumed via `<app-svg-icon name="...">`. Prevents SVG duplication across components.

#### `tab-bar/`
Renders a strip of open browser tabs. Clicking sends `SWITCH_TAB`. New tabs appear on `TAB_OPENED` events from the backend.

#### `tooltip/`
Directive/component that shows hover tooltips. Used on toolbar buttons and sidebar nav items.

---

### Pages

#### `pages/browser/`
Home page (`/`). Hosts `Toolbar`, `TabBar`, `BrowserView`, `Status`, `InputOverlay`, and `RecordingModal`.

#### `pages/flows/`
Left: card list of all saved recordings (name, step count, description, dates).
Right: step detail for selected flow, grouped by URL/tab, independently scrollable.

#### `pages/runs/`
Execution history. Placeholder for future run results and logs.

#### `pages/settings/`
App settings. Placeholder for future configuration options.

---

### Services

#### `websocket.api.ts` — Core WebSocket Layer

Opens `ws://localhost:8001/ws/{session_id}`. On connect sends `HELLO`. Parses incoming events and routes to typed RxJS `Subject` per event type.

**Observables exposed:**

| Observable | Emits when |
|------------|------------|
| `frame$` | `FRAME` received (new screenshot) |
| `navigating$` | Action event about to be sent |
| `disconnected$` | WS closes, `disconnect()` called, or `SESSION_CLOSED` received |
| `navigationSuccess$` / `navigationError$` | Navigate results |
| `recordingStarted$` / `recordingStopped$` | Recording lifecycle |
| `inputDetected$` | Backend detected a text input was clicked |
| `tabOpened$` / `tabSwitched$` | Multi-tab events |
| `actionDone$` | Any action completed |

#### `navigation.api.ts`
High-level wrapper: `navigate(url)` sends `NAVIGATE` over WS. Tracks `navigationState` signal.

#### `recordings.api.ts`
HTTP service: `listRecordings()`, `getRecording(id)`, `deleteRecording(id)` calling the REST API.

#### `theme.api.ts`
`toggle()` flips `isDark` signal, adds/removes `html.dark` class, persists to `localStorage`. On startup reads `localStorage` or OS preference.

#### `token-store.api.ts`
Stores sensitive runtime values (e.g. passwords) **in memory only** — never written to localStorage or included in recorded steps.

---

### `types/websocket.ts` — Shared TypeScript Interfaces

| Type | Purpose |
|------|---------|
| `EventType` | Union of all event name strings |
| `ConnectionState` | `{ isConnected, sessionId, clientId, lastUpdate, error, sessionClosed }` |
| `RecordingStep` | Shape of one recorded action |
| `RecordingDetail` | Full recording: `meta` + `steps: Record<tab_id, group[][]>` |
| `RecordingListItem` | Summary row: id, name, description, stepCount, createdAt, updatedAt |
| `TabGroup` | `{ tabId, url, steps }` — computed grouping used by Flows page |

---

### `styles.css` — Global Design System

| Section | What's defined |
|---------|----------------|
| `:root` | CSS tokens: colours, spacing, radii, shadows, font sizes, transitions |
| `html.dark` | Dark-mode overrides for surface and text tokens |
| Base reset | `box-sizing`, `html/body height: 100%`, `app-root display: flex` |
| `.btn-*` | Button variants: primary, secondary, ghost, success, danger + size modifiers |
| Form elements | `input`, `textarea`, `select` focus rings |
| `.card` / `.badge` | Card surface and badge colour variants |
| Scrollbar | Custom webkit scrollbar (5px, rounded) |
| Utilities | `.flex-center`, `.truncate`, `.gap-*`, `.shadow-*`, `.rounded-*` |

---

## Database

```
database/
├── schema.sql      ← Table definitions: Users + Recordings
└── recorder.db     ← SQLite database file (auto-created on first run)
```

- `Users(userId, clientId, createdAt)` — one row per browser client
- `Recordings(recordId, userId FK, recordingJson, flowName, createdAt, updatedAt)` — full recording JSON blob per row

---

## Key Design Decisions

| Decision | Reason |
|----------|--------|
| Fire-and-forget `_bg_screenshot` | Returns `ACTION_DONE` to frontend instantly; screenshot waits for `load` in background |
| Shared `_in_flight` flag | Prevents `_bg_screenshot` and `DomWatcher` from racing and sending duplicate frames |
| DomWatcher follow-up frame (1.2s) | Captures lazy-loaded images and embedded widgets that load after the initial `load` event |
| `source` field on every FRAME | Identifies which component sent each frame (CLICK / DOM-WATCHER / DOM-WATCHER-FOLLOWUP) for debugging |
| `debug.log` cleared on startup | Every `run.py` start produces a fresh log — no hunting for the latest session at the bottom |
| `token-store.api.ts` in memory only | Passwords never leave the browser session or appear in recorded steps |

---

## How It All Works Together

```
Browser (Angular @ :4200)
        │
        │  HTTP  POST /recording/start  ──►  Creates session + launches Chromium
        │  HTTP  POST /recording/stop   ──►  Detaches DomWatcher → notifies client
        │                                   → closes Chromium → removes session
        │
        │  WebSocket  ws://localhost:8000/ws/{session_id}
        │  ┌──────────────────────────────────────────────────────┐
        │  │  Client → Server:  HELLO, NAVIGATE, CLICK_ACTION,   │
        │  │                    SCROLL_ACTION, TYPE_ACTION,       │
        │  │                    KEY_ACTION, START_RECORDING,      │
        │  │                    STOP_RECORDING, SWITCH_TAB, PING  │
        │  │                                                      │
        │  │  Server → Client:  WELCOME, FRAME, NAVIGATION_SUCCESS│
        │  │                    NAVIGATION_ERROR, ACTION_DONE,    │
        │  │                    INPUT_DETECTED, RECORDING_STARTED,│
        │  │                    RECORDING_STOPPED, TAB_OPENED,    │
        │  │                    TAB_SWITCHED, SESSION_CLOSED,     │
        │  │                    ERROR, PONG                       │
        │  └──────────────────────────────────────────────────────┘
        │
FastAPI Server (Python @ :8000)
        │
        ├──► Playwright controls a real Chromium browser (headless)
        ├──► DomWatcher captures screenshots on every DOM change (debounced 300 ms)
        └──► SQLite (via aiosqlite) persists recordings
```

**Full session flow:**

1. User clicks **Connect** → Angular calls `POST /recording/start`
2. Backend creates a session, launches headless Chromium, returns `session_id`
3. Angular opens a WebSocket; sends `HELLO`; server replies `WELCOME`
4. User navigates, clicks, types, scrolls — each action is sent as a WS event
5. Backend performs the action in Playwright; `DomWatcher` detects DOM changes and sends `FRAME` screenshots (JPEG base64) back to the client
6. Scroll events are **debounced 150 ms on the frontend** — accumulated deltas are sent as a single `SCROLL_ACTION` when scrolling pauses
7. User can record actions (`START_RECORDING` / `STOP_RECORDING`) — the backend serialises steps to JSON and saves to SQLite
8. When the session ends (via REST or WS disconnect) `DomWatcher` is detached before the browser closes; a `SESSION_CLOSED` event is pushed to the client

---

## Backend

```
backend/
├── run.py
└── app/
    ├── main.py
    ├── api/
    │   └── recording.py
    ├── websocket/
    │   ├── connection_manager.py
    │   ├── websocket_events.py
    │   └── websocket_handler.py
    ├── services/
    │   ├── browser_service.py
    │   ├── screenshot_service.py
    │   ├── dom_watcher.py
    │   ├── session_manager.py
    │   ├── recording_storage.py
    │   └── database.py
    ├── models/
    │   ├── session.py
    │   └── recording.py
    ├── session/
    ├── storage/
    │   └── recordings/   ← JSON file backups
    └── utils/
```

---

### `run.py` — Entry Point

**The only file you run.** Sets `asyncio.WindowsProactorEventLoopPolicy` on Windows (required by Playwright) before uvicorn starts.

---

### `app/main.py` — App Factory

- Configures logging (console + `debug.log`)
- Initialises all service singletons and wires them together
- Mounts `/recording` REST router; passes `connection_manager` to it so the REST layer can send WS events (e.g. `SESSION_CLOSED`)
- Registers `/ws/{session_id}` WebSocket endpoint
- On `WebSocketDisconnect` → detaches `DomWatcher` before removing the WS connection

---

### `app/api/recording.py` — REST Endpoints

| Method | Path | What it does |
|--------|------|--------------|
| `POST` | `/recording/start` | Creates session, launches Chromium, returns `session_id` |
| `POST` | `/recording/stop` | **Detaches DomWatcher first**, sends `SESSION_CLOSED` WS event to client, closes browser, removes session |

Receives a `ConnectionManager` reference so it can push WS events even from HTTP handlers.

---

### `app/websocket/connection_manager.py` — WebSocket Registry

Maintains `{ session_id → { client_id → WebSocket } }` map.

- `connect` / `disconnect` — register/deregister connections
- `send_to_client(session_id, client_id, message)` — targeted send to one client
- `broadcast_to_session(session_id, message)` — send to all clients in a session

---

### `app/websocket/websocket_handler.py` — Event Router

Routes incoming WS events to handler methods:

| Event | Handler | Description |
|-------|---------|-------------|
| `HELLO` | `handle_hello` | Validates session, replies `WELCOME` |
| `PING` | `handle_ping` | Replies `PONG` |
| `NAVIGATE` | `handle_navigate` | `page.goto()` with `wait_until=load` + best-effort `networkidle`; sends `NAVIGATION_SUCCESS/ERROR` |
| `CLICK_ACTION` | `handle_click_action` | `page.mouse.click()`, records step, sends `FRAME` |
| `SCROLL_ACTION` | `handle_scroll_action` | `page.mouse.wheel()` with **accumulated delta**, records step, sends `FRAME` |
| `TYPE_ACTION` | `handle_type_action` | Focuses element, types text, records step |
| `KEY_ACTION` | `handle_key_action` | `page.keyboard.press()` for Enter/Tab/Escape/etc. |
| `START_RECORDING` | `handle_start_recording` | Attaches `DomWatcher`, initialises step list |
| `STOP_RECORDING` | `handle_stop_recording` | Detaches watcher, serialises steps → JSON file + SQLite |
| `SWITCH_TAB` | `handle_switch_tab` | Activates the requested tab |

---

### `app/services/browser_service.py` — Playwright Operations

| Method | Description |
|--------|-------------|
| `launch_browser()` | Starts Playwright, launches headless Chromium, returns `(Browser, Context, Page)` |
| `navigate_to_url(page, url)` | `page.goto()` + best-effort `networkidle`; returns title + status |
| `perform_click(page, x, y)` | Mouse click at viewport coordinates |
| `perform_scroll(page, x, y, dx, dy)` | `page.mouse.move()` + `page.mouse.wheel()` |
| `perform_type(page, selector, text)` | Fills / types into an element |
| `take_screenshot(page)` | JPEG screenshot → base64 string |
| `close_browser(browser)` | Gracefully closes browser + stops Playwright |

---

### `app/services/dom_watcher.py` — Auto Screenshot Trigger

Attaches Playwright event listeners + a JS `MutationObserver` to the active page. Any DOM change schedules a debounced screenshot (default 300 ms). Multiple rapid changes collapse into one screenshot.

**Shutdown safety:**
- `detach()` cancels any pending debounce task and sets `_active = False`
- Every Playwright call inside `_debounced_capture` catches `TargetClosedError` silently (sets `_active = False`) so no error is logged after the browser closes
- `_active` is re-checked **after** the debounce sleep to handle `detach()` calls that arrive mid-wait

---

### `app/services/screenshot_service.py` — Frame Sender

Calls `browser_service.take_screenshot()` and pushes a `FRAME` event containing a base64 JPEG to the requesting client via `connection_manager.send_to_client()`.

---

### `app/services/session_manager.py` — In-Memory Session Store

Holds active sessions in a Python dict. Each session object carries:
- `browser`, `browser_context`, `page` — Playwright handles
- `dom_watcher` — attached watcher instance
- `recording_steps`, `recording_id`, `recording_name` — recording state
- `active_tab_id`, `tabs` — multi-tab tracking
- `client_id`, `current_url`

---

### `app/services/database.py` — SQLite Persistence

Async SQLite via `aiosqlite`. DB file: `database/recorder.db`.

| Method | Description |
|--------|-------------|
| `init_db()` | Creates tables from `database/schema.sql` |
| `ensure_user(client_id)` | Upserts a user row keyed by client ID |
| `save_recording(...)` | Inserts / replaces a recording JSON blob |
| `list_recordings()` | Returns all recordings enriched with `description`, `stepCount`, `createdAt`, `updatedAt` |
| `load_recording(record_id)` | Returns the full parsed JSON for one recording |

Schema: `Users(userId, clientId, ...)` + `Recordings(recordId, userId FK, json, flowName)`.

---

### `app/services/recording_storage.py` — File Backup

Serialises `Recording` objects to JSON files in `storage/recordings/`. Acts as a backup alongside SQLite.

---

### `app/models/recording.py` — Recording Data Model

| Class | Purpose |
|-------|---------|
| `RecordingStep` | One recorded action (type, coords, selector, delta, text, …) |
| `RecordingMeta` | Flow metadata (id, title, description, intent, createdAt, updatedAt) |
| `Recording` | Full recording: meta + `steps: dict[tab_id → list[group]]` |

Steps are grouped: each user action is one group (`list[RecordingStep]`), supporting future parallelism.

---

## Frontend

```
automation_frontend/src/
├── styles.css              ← Global design system
├── index.html
├── main.ts
└── app/
    ├── app.ts / .html / .css / .routes.ts / .config.ts
    ├── components/
    │   ├── browser-view/   ← Live screenshot display + interaction
    │   ├── input-overlay/  ← Type prompt overlay on input detection
    │   ├── tab-bar/        ← Multi-tab switcher
    │   ├── navbar/
    │   ├── sidebar/
    │   ├── toolbar/
    │   └── status/
    ├── pages/
    │   ├── browser/        ← / (home): Toolbar + BrowserView
    │   ├── flows/          ← /flows: recorded flows card list + detail panel
    │   ├── runs/
    │   └── settings/
    ├── services/
    │   ├── websocket.api.ts
    │   ├── navigation.api.ts
    │   ├── recordings.api.ts
    │   └── theme.api.ts
    └── types/
        └── websocket.ts
```

---

### `components/browser-view/`

Displays live screenshots as `<img>` elements and forwards user interactions to the backend.

**Scroll optimisation — debounce + delta accumulation:**
```
Wheel event fires (×N per gesture)
  → accumulate deltaX / deltaY
  → reset 150 ms debounce timer
  → after 150 ms silence: send ONE SCROLL_ACTION with total delta
```
Previously N WS round-trips per scroll gesture; now exactly one.

**Loading overlay:** shown on `navigating$` emission, cleared on next `FRAME`.

**Disconnect cleanup:** subscribes to `disconnected$` → clears frame, overlay, tabs, scroll accumulators.

---

### `components/tab-bar/`

Renders a tab strip. Each tab has a label derived from its page title. Clicking a tab sends `SWITCH_TAB`. New tabs appear on `TAB_OPENED` events from the backend (triggered by `target=_blank` links).

---

### `components/status/`

Displays real-time session state with three distinct indicators:

| State | Colour | Condition |
|-------|--------|-----------|
| Connected | Green | `isConnected = true` |
| Session Closed | Green (dimmed) | `isConnected = false` + `sessionClosed = true` |
| Disconnected | Red | `isConnected = false` + `sessionClosed = false` |

`sessionClosed` is set when the backend sends `SESSION_CLOSED` (e.g. after `/recording/stop`). It resets to `false` on the next manual `connect()`.

---

### `pages/flows/`

**Left panel** — card list showing all saved recordings.
Each card displays: flow name · step count · description · `Created` + `Updated` dates (inline).

**Right panel** — detail view for the selected flow.
Steps are **grouped by URL** (tab): each group shows the NAVIGATE URL as a sticky header with a step count badge, followed by every step in that tab (all types: NAVIGATE, CLICK, TYPE, SCROLL, etc.).
The panel scrolls vertically independently of the left list.

---

### `services/websocket.api.ts`

Core real-time layer.

**Observables exposed:**

| Observable | Emits when |
|------------|------------|
| `frame$` | FRAME event received (new screenshot) |
| `navigating$` | Any user action is about to be sent (shows loading overlay) |
| `disconnected$` | WS closes, `disconnect()` called, or `SESSION_CLOSED` received |
| `navigationSuccess$` / `navigationError$` | Navigate result |
| `recordingStarted$` / `recordingStopped$` | Recording lifecycle |
| `inputDetected$` | Backend detected a text input was clicked |
| `tabOpened$` / `tabSwitched$` | Multi-tab events |
| `actionDone$` | Any action completed |

**`SESSION_CLOSED` handling:**
When received → sets `connectionState.sessionClosed = true`, fires `disconnected$`. All components subscribed to `disconnected$` reset their state automatically.

---

### `services/recordings.api.ts`

HTTP service that calls the REST API:
- `listRecordings()` → `GET /recording/list`
- `getRecording(id)` → `GET /recording/{id}`

---

### `types/websocket.ts`

Single source of truth for the WS protocol:

| Type | Purpose |
|------|---------|
| `EventType` | Union of all 23 event names |
| `ConnectionState` | `{ isConnected, sessionId, clientId, lastUpdate, error, sessionClosed? }` |
| `RecordingStep` | Shape of one recorded action |
| `RecordingDetail` | Full recording with `meta` + `steps: Record<tab_id, group[][]>` |
| `RecordingListItem` | Summary row: id, name, description, stepCount, createdAt, updatedAt |
| `TabGroup` | `{ tabId, url, steps }` — computed grouping used by the Flows page |

---

### `styles.css` — Global Design System

| Token group | Examples |
|-------------|----------|
| Primary | `--color-primary-500: #2563EB` (blue) |
| Secondary | `--color-secondary-500: #10B981` (green) |
| Neutral | `--color-neutral: #64748B` |
| Surfaces | `--bg-primary`, `--bg-secondary`, `--bg-tertiary` |
| Text | `--text-primary`, `--text-secondary`, `--text-tertiary` |
| Border | `--border-color` |
| Radii | `--rounded-sm/md/lg` |
| Transitions | `--transition-fast` |

Dark-mode overrides live under `html.dark { … }` and are toggled by `ThemeApi`.


**Flow for connecting and navigating:**

1. User clicks **Connect** → Angular calls `POST /recording/start`
2. Backend creates a session, launches a headless Chromium browser, returns `session_id`
3. Angular opens a WebSocket to `ws://localhost:8001/ws/{session_id}`
4. Angular sends a `HELLO` event; server replies with `WELCOME`
5. User types a URL and clicks **Navigate** → Angular sends a `NAVIGATE` event over the WebSocket
6. Backend uses Playwright to navigate the real browser to that URL
7. Server replies with `NAV_SUCCESS` or `NAV_ERROR`; Angular updates the UI

---

## Backend

```
backend/
├── run.py
└── app/
    ├── main.py
    ├── api/
    │   └── recording.py
    ├── websocket/
    │   ├── connection_manager.py
    │   ├── websocket_events.py
    │   └── websocket_handler.py
    ├── services/
    │   ├── browser_service.py
    │   └── session_manager.py
    ├── models/
    │   └── session.py
    ├── session/
    ├── storage/
    └── utils/
```

### `run.py` — Entry Point

**The only file you run.** It must be started with `python run.py`.

Why it exists separately from `main.py`:  
On **Windows**, Playwright needs `asyncio.WindowsProactorEventLoopPolicy` to be set **before** uvicorn creates any event loop. Setting it inside `main.py` is too late. `run.py` sets the policy first, then imports and starts uvicorn.

```
python run.py
    │
    ├── sets WindowsProactorEventLoopPolicy  (Windows only)
    └── uvicorn.run("app.main:app", port=8001, reload=False)
                                                   ↑
                                       reload=False is required —
                                       reload=True spawns subprocesses
                                       that reset the event loop policy
```

---

### `app/main.py` — App Factory

Creates the FastAPI application, wires everything together, and defines routes.

**What it does:**
- Configures structured logging (to both console and `debug.log`)
- Instantiates shared singletons: `SessionManager`, `BrowserService`, `ConnectionManager`, `WebSocketHandler`
- Adds CORS middleware (allows Angular on `:4200` to call the API)
- Mounts the `/recording` REST router
- Registers the WebSocket endpoint at `/ws/{session_id}`
- Defines `/health` endpoint

**The WebSocket endpoint** receives raw messages, parses the `event` field, and delegates to `WebSocketHandler`.

---

### `app/api/recording.py` — REST Endpoints

| Method | Path | What it does |
|--------|------|--------------|
| `POST` | `/recording/start` | Creates a new session, calls `BrowserService.launch_browser()`, stores browser/page in session, returns `session_id` |
| `POST` | `/recording/stop` | Looks up session by `session_id`, closes browser and page, removes session from memory |

---

### `app/websocket/connection_manager.py` — WebSocket Registry

Keeps a dictionary of `{ session_id → WebSocket }`.

- `connect(session_id, websocket)` — registers a connection
- `disconnect(session_id)` — removes a connection
- `send_json(session_id, data)` — sends a JSON message to a specific client

All WebSocket sends go through this class so there is one place managing active connections.

---

### `app/websocket/websocket_events.py` — Event Type Definitions

Defines the event protocol as Python dataclasses / enums:

- `EventType` — string constants: `HELLO`, `WELCOME`, `PING`, `PONG`, `NAVIGATE`, `NAV_SUCCESS`, `NAV_ERROR`, `ERROR`
- `HelloData`, `WelcomeData`, `PingData`, `PongData`, `NavigateData`, `ErrorData` — typed payloads for each event

---

### `app/websocket/websocket_handler.py` — Event Router

Receives a parsed event dict and routes it to the right handler method:

| Event received | Handler | What happens |
|----------------|---------|--------------|
| `HELLO` | `handle_hello` | Validates session exists, replies `WELCOME` |
| `PING` | `handle_ping` | Replies `PONG` (keep-alive) |
| `NAVIGATE` | `handle_navigate` | Calls `BrowserService.navigate_to_url()`, replies `NAV_SUCCESS` or `NAV_ERROR` |

---

### `app/services/browser_service.py` — Playwright Operations

Wraps the Playwright async API.

| Method | What it does |
|--------|--------------|
| `launch_browser()` | Starts Playwright, launches Chromium (headless), creates a context and page, returns `(Browser, BrowserContext, Page)` |
| `navigate_to_url(page, url)` | Calls `page.goto(url)`, returns `{ url, title, status }` |
| `close_browser(browser, playwright)` | Gracefully closes browser and stops Playwright |

---

### `app/services/session_manager.py` — In-Memory Session Store

Holds active sessions in a Python `dict`.

| Method | What it does |
|--------|--------------|
| `create_session()` | Generates a UUID, stores empty session dict, returns `session_id` |
| `get_session(session_id)` | Returns the session dict or `None` |
| `update_session(session_id, data)` | Merges new data into the session (stores `browser`, `page`, etc.) |
| `delete_session(session_id)` | Removes the session |

Sessions are not persisted — they live only while the server is running.

---

### `app/models/session.py` — Pydantic Models

Pydantic v2 schemas used for request/response validation:

- `StartRecordingRequest` / `StartRecordingResponse` — for `/recording/start`
- `StopRecordingRequest` — for `/recording/stop`
- `SessionInfo` — shape of a session object

---

### `app/session/`, `app/storage/`, `app/utils/`

| Folder | Purpose |
|--------|---------|
| `session/` | Session lifecycle helpers (state transitions) |
| `storage/` | File-based save/load for recordings and screenshots (future use) |
| `utils/` | Shared helper functions (URL validation, formatting, etc.) |

---

### `debug.log`

Every log line from the backend (INFO, DEBUG, ERROR) is written here in addition to the terminal. Useful for debugging without watching the terminal.

---

## Frontend

```
automation_frontend/src/
├── styles.css              ← Global design system (loaded by angular.json)
├── index.html              ← Shell HTML; only contains <app-root>
├── main.ts                 ← Angular bootstrap
└── app/
    ├── app.ts              ← Root component (shell layout)
    ├── app.html            ← Shell template: navbar + sidebar + <router-outlet>
    ├── app.css             ← Shell layout (flex column, full height)
    ├── app.routes.ts       ← Route table
    ├── app.config.ts       ← Angular providers (router, http)
    │
    ├── components/
    │   ├── navbar/         ← Top bar: title + theme toggle
    │   ├── sidebar/        ← Left nav: Browser, Flows, Runs, Settings
    │   ├── toolbar/        ← URL input + Connect / Disconnect / Navigate buttons
    │   └── status/         ← Connection + navigation status display
    │
    ├── pages/
    │   ├── browser/        ← Default route (/): hosts Toolbar + Status
    │   ├── flows/          ← /flows: list of recorded automation flows
    │   ├── runs/           ← /runs: execution history
    │   └── settings/       ← /settings: app configuration
    │
    ├── services/
    │   ├── websocket.api.ts   ← Manages the WebSocket connection + events
    │   ├── navigation.api.ts  ← High-level navigate() calls, wraps WebsocketApi
    │   └── theme.api.ts       ← Dark/light mode toggle, persists to localStorage
    │
    └── types/
        └── websocket.ts    ← All TypeScript interfaces (EventType, ConnectionState, etc.)
```

---

### Shell Layout (`app.ts` / `app.html`)

```
┌────────────────────────────────────────────────────┐
│  Navbar  (54px, sticky)                            │
├──────────┬─────────────────────────────────────────┤
│          │                                         │
│ Sidebar  │   <router-outlet>                       │
│ (220px)  │   renders the active page here          │
│          │                                         │
└──────────┴─────────────────────────────────────────┘
```

`app.ts` imports `Navbar`, `Sidebar`, and `RouterOutlet`. All pages render **inside** the router-outlet, so the navbar and sidebar are always visible.

---

### `app.routes.ts` — Route Table

| Path | Component | Purpose |
|------|-----------|---------|
| `/` | `BrowserComponent` | Main browser control page |
| `/flows` | `Flows` | Recorded flows list |
| `/runs` | `Runs` | Execution history |
| `/settings` | `SettingsComponent` | App settings |
| `**` | redirect → `/` | Unknown routes go home |

---

### Components

#### `navbar/`
- `navbar.ts` — injects `ThemeApi`, exposes `isDark` signal
- `navbar.html` — left: logo + "Recorder & Player" title; right: sun/moon toggle button
- `navbar.css` — sticky bar styles, hover ring on toggle button

#### `sidebar/`
- `sidebar.ts` — defines `navItems` array (label, route, icon)
- `sidebar.html` — renders `routerLink` items with SVG icons; active item highlighted using `routerLinkActive`
- `sidebar.css` — full-height flex column, active item uses primary-blue tint

#### `toolbar/`
- `toolbar.ts` — handles Connect, Disconnect, Navigate button clicks; reads `environment.apiBaseUrl`
- `toolbar.html` — URL text input + three action buttons + connection status badge
- `toolbar.css` — horizontal flex bar with input stretching to fill space

#### `status/`
- `status.ts` — reads signals from `WebsocketApi` and `NavigationApi`
- `status.html` — displays real-time connection state and last navigation result
- `status.css` — status badge and message styles

---

### Pages

#### `pages/browser/`
The **home page** (`/`). Composes `Toolbar` and `Status` components. This is where the user connects, navigates, and sees live feedback.

#### `pages/flows/`
Lists saved automation flows. Currently shows an empty state. Will display recorded flow cards.

#### `pages/runs/`
Shows execution history. Currently shows an empty state. Will display run results and logs.

#### `pages/settings/`
Application settings page. Placeholder for future configuration options.

---

### Services

#### `websocket.api.ts` — WebSocket Service

The core real-time layer. Uses the browser's native `WebSocket` API.

```
connect(sessionId)
    │
    ├── opens ws://localhost:8001/ws/{sessionId}
    ├── on open → sends HELLO event
    ├── on message → parses event type, routes to Subject
    └── updates connectionState signal

Exposes Observables:
    navigationSuccess$  ← emits on NAV_SUCCESS
    navigationError$    ← emits on NAV_ERROR
    error$              ← emits on ERROR
```

State is tracked in a `WritableSignal<ConnectionState>` — components read it reactively.

#### `navigation.api.ts` — Navigation Service

High-level wrapper over `WebsocketApi`.

- `navigate(url)` — sends a `NAVIGATE` event over the WebSocket
- Subscribes to `navigationSuccess$` and `navigationError$` to update `navigationState` signal
- Components only interact with `NavigationApi`, never directly with WebSocket events

#### `theme.api.ts` — Theme Service

- On startup: reads `localStorage` (or falls back to OS preference) to set initial theme
- `toggle()` — flips `isDark` signal, adds/removes `html.dark` class, saves to `localStorage`
- The `html.dark` class activates all dark-mode CSS variables defined in `styles.css`

---

### `types/websocket.ts` — Shared TypeScript Interfaces

Single source of truth for the WebSocket protocol types:

| Type | Purpose |
|------|---------|
| `EventType` | Enum of all event names (`HELLO`, `WELCOME`, `NAVIGATE`, etc.) |
| `WebSocketEvent<T>` | Generic wrapper `{ event: EventType, data: T, timestamp }` |
| `ConnectionState` | `{ isConnected, isConnecting, sessionId, error }` |
| `NavigationState` | `{ isLoading, lastUrl, lastTitle, error }` |
| `HelloData` / `WelcomeData` | HELLO / WELCOME event payloads |
| `NavigateData` | `{ url }` — sent with NAVIGATE event |
| `NavigationSuccessData` | `{ url, title, status }` — received on success |
| `NavigationErrorData` | `{ url, error }` — received on failure |

---

### `styles.css` — Global Design System

Loaded globally via `angular.json`. Every component can use these tokens.

| Section | What's defined |
|---------|---------------|
| `:root` | CSS custom properties — colors, spacing, shadows, radii, font sizes, transitions |
| `html.dark` | Dark-mode overrides for surface and text tokens |
| Base reset | `* { box-sizing }`, `html/body { height: 100% }`, `app-root { display: flex }` |
| Typography | `h1–h6`, `p`, `a`, `code` base styles |
| `.btn-*` | Button variants: primary, secondary, ghost, success, danger + size modifiers |
| Form elements | `input`, `textarea`, `select` focus rings |
| `.card` / `.badge` | Card surface and badge color variants |
| `.status-indicator` | Animated connection dot |
| Scrollbar | Custom webkit scrollbar (5px, rounded) |
| Utilities | `.flex-center`, `.truncate`, `.gap-*`, `.shadow-*`, `.rounded-*` etc. |

---

### `src/environments/`

| File | Used when |
|------|-----------|
| `environment.ts` | `ng serve` (development) |
| `environment.prod.ts` | `ng build --configuration production` |

Both export `apiBaseUrl` and `wsBaseUrl`. All services import from here instead of hardcoding `localhost`.
