# Playwright Recorder & Player

A browser automation tool with real-time screenshot streaming, action recording, multi-tab support, and flow playback — built with **FastAPI** (backend) and **Angular 21** (frontend).

---

## Features

- **Live browser view** — real-time JPEG screenshot stream over WebSocket
- **Action recording** — captures navigate, click, type, scroll, and key actions
- **Multi-tab support** — follows `target=_blank` links; tab bar in the UI
- **Flow library** — recordings saved to SQLite; browsable in the Flows page
- **Optimised scroll** — frontend debounces + accumulates scroll deltas (150 ms); sends one WS message per gesture instead of one per wheel tick
- **Session lifecycle events** — backend sends `SESSION_CLOSED` when the session ends; UI shows green “Session Closed” state
- **Dark / light mode** — persisted to localStorage

---

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** and **npm**
- **Angular CLI** — `npm install -g @angular/cli`

---

## Installation

### 1. Backend

```bash
cd backend
pip install -r ../requirements.txt
playwright install chromium
```

### 2. Frontend

```bash
cd automation_frontend
npm install
```

---

## Running the App

### Start the Backend

```bash
cd backend
python run.py
```

Backend runs at: `http://localhost:8000`

### Start the Frontend

Open a new terminal:

```bash
cd automation_frontend
ng serve
```

Frontend runs at: `http://localhost:4200`

---

## Usage

1. Open `http://localhost:4200` in your browser
2. Click **Connect** to start a browser session (launches headless Chromium)
3. Enter a URL and click **Navigate**
4. **Click**, **scroll**, or **type** directly on the live screenshot
5. Click **Start Recording** to capture a flow; **Stop Recording** to save it
6. Open the **Flows** tab to browse saved recordings and inspect every step grouped by URL
7. Click **Disconnect** when done — the status panel shows **Session Closed** in green

---

## Project Structure

```
.
├── backend/
│   ├── run.py                  # Entry point (sets Windows event loop policy)
│   └── app/
│       ├── main.py              # App factory: services, routes, WS endpoint
│       ├── api/
│       │   └── recording.py     # POST /recording/start|stop
│       ├── websocket/
│       │   ├── connection_manager.py
│       │   └── websocket_handler.py  # Routes WS events to handlers
│       ├── services/
│       │   ├── browser_service.py    # Playwright operations
│       │   ├── screenshot_service.py # FRAME event sender
│       │   ├── dom_watcher.py        # Debounced auto-screenshot on DOM change
│       │   ├── session_manager.py
│       │   ├── database.py           # SQLite via aiosqlite
│       │   └── recording_storage.py  # JSON file backup
│       └── models/
│           ├── session.py
│           └── recording.py
│
├── database/
│   └── recorder.db             # SQLite database (auto-created)
│
└── automation_frontend/
    └── src/app/
        ├── components/
        │   ├── browser-view/   # Live screenshot + click/scroll/type interaction
        │   ├── tab-bar/        # Multi-tab strip
        │   ├── input-overlay/  # Floating type prompt
        │   ├── toolbar/        # URL bar + Connect/Disconnect/Navigate
        │   ├── navbar/
        │   ├── sidebar/
        │   └── status/         # Connection / session-closed / nav status
        ├── pages/
        │   ├── browser/        # / (home)
        │   ├── flows/          # /flows — recorded flow cards + step detail
        │   ├── runs/
        │   └── settings/
        ├── services/
        │   ├── websocket.api.ts    # WS connection, all observables
        │   ├── navigation.api.ts
        │   ├── recordings.api.ts   # HTTP calls for flow list/detail
        │   └── theme.api.ts
        └── types/
            └── websocket.ts        # All TS interfaces
```

---

## WebSocket Event Reference

| Direction | Event | Purpose |
|-----------|-------|---------|
| Client → Server | `HELLO` | Handshake |
| Server → Client | `WELCOME` | Session confirmed |
| Client → Server | `NAVIGATE` | Load URL |
| Server → Client | `NAVIGATION_SUCCESS` / `NAVIGATION_ERROR` | Navigate result |
| Server → Client | `FRAME` | Base64 JPEG screenshot |
| Client → Server | `CLICK_ACTION` | Click at (x, y) |
| Client → Server | `SCROLL_ACTION` | Scroll with accumulated delta |
| Client → Server | `TYPE_ACTION` | Type text into element |
| Client → Server | `KEY_ACTION` | Press named key |
| Client → Server | `START_RECORDING` / `STOP_RECORDING` | Recording lifecycle |
| Server → Client | `RECORDING_STARTED` / `RECORDING_STOPPED` | Recording lifecycle |
| Server → Client | `INPUT_DETECTED` | Text input was clicked |
| Client → Server | `SWITCH_TAB` | Activate a tab |
| Server → Client | `TAB_OPENED` / `TAB_SWITCHED` | Tab events |
| Server → Client | `SESSION_CLOSED` | Server closed the session |
| Both | `PING` / `PONG` | Keep-alive |
| Server → Client | `ERROR` | Error details |

