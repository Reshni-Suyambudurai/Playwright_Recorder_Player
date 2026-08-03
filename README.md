# Playwright Recorder & Player

## Overview

**Playwright Recorder & Player** is a no-code browser automation tool designed for non-technical users to record and replay end-to-end UI testing workflows and repetitive tasks.

**Use Case**: Any non-technical person can now:
- Record real browser interactions (clicks, typing, navigation) without writing code
- Save recorded flows to a library
- Replay flows anytime to automate repetitive testing tasks
- View detailed step-by-step execution with visual validation

**Built With**: FastAPI (backend) + Angular 21 (frontend) + Playwright (browser automation)

---

## Quick Setup

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** and **npm**
- **Angular CLI** - `npm install -g @angular/cli`
- **Visual Studio Code** (IDE used for development)

### Installation

**1. Backend Setup**
```bash
cd backend
pip install -r ../requirements.txt
playwright install chromium
```

**2. Frontend Setup**
```bash
cd automation_frontend
npm install
```

---

## Running the Application

### Start Backend (Terminal 1)
```bash
cd backend
python run.py
# Backend runs at: http://localhost:8000
```

### Start Frontend (Terminal 2)
```bash
cd automation_frontend
ng serve
# Frontend runs at: http://localhost:4200
```

Open `http://localhost:4200` in your browser to start.

---

## Architecture

### High-Level Flow
```
User Interface (Browser)
        |
   Angular 21 (Frontend)
        |
   Realtime Communication
        |
   FastAPI Server (Backend)
        |
   Playwright Browser Automation
        |
   SQLite Database (Recording Storage)
```

### Key Components

**Frontend (Angular 21):**
- **Browser Tab**: Live screenshot streaming + interactive recording
- **Flows Tab**: View, edit, and manage saved recordings
- **Runs Tab**: Replay flows and monitor execution
- Real-time visual feedback during recording and playback

**Backend (FastAPI):**
- **WebSocket Handler**: Bidirectional communication for real-time events
- **Browser Service**: Playwright-based Chromium automation
- **Session Manager**: Multi-session support
- **Recording Storage**: SQLite database + JSON file backup
- **Selector Builder**: Smart element detection (ID -> CSS -> XPath)
- **Playback Service**: Replay recorded flows with validation

---

## Tools Used

### Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Frontend Framework** | Angular | 21 |
| **Frontend Language** | TypeScript | Latest |
| **Backend Framework** | FastAPI | Latest |
| **Browser Automation** | Playwright | Latest (async) |
| **Database** | SQLite | 3.x |
| **Real-time Comm** | WebSocket | Native (FastAPI + Browser API) |
| **Server** | Uvicorn (ASGI) | Latest |
| **IDE** | Visual Studio Code | Latest |

### Development Tools
- **TypeScript** - Type-safe frontend code
- **Pydantic v2** - Data validation (backend)
- **aiosqlite** - Async database access
- **pytest** - Unit and integration tests (71 tests passing)

---

## Data Sourcing

### Where Data Comes From

1. **Live Browser Interactions** (Recording)
   - User clicks, types, scrolls, navigates in the browser
   - Playwright captures these actions in real-time
   - Backend extracts element metadata (selectors, DOM snapshot)

2. **Element Detection** (Smart Selectors)
   - Backend analyzes the DOM to find stable selectors
   - Priority: ID -> data-testid -> aria-label -> name -> CSS -> XPath
   - Fallback: Element fingerprinting (tag, role, text, aria-label)

3. **Storage**
   - **SQLite Database** - Persists recording metadata
   - **JSON Files** - Stores detailed step data (selectors, coordinates, text input)
   - Location: `backend/storage/recordings/`

4. **Validation Data** (During Playback)
   - Live DOM inspection during replay
   - Element matching with recorded selectors
   - Fingerprint comparison for safe fallbacks

---

## Demo Instructions

### Part 1: Record a Flow

1. **Start the Application**
   - Open `http://localhost:4200`
   - You should see the "Browser" tab with a live screenshot area

2. **Connect to Browser**
   - Click "Connect" button
   - Wait for the connection status to show "Connected" (green indicator)

3. **Navigate to a Website**
   - Enter a URL in the address bar (e.g., `https://example.com`)
   - Click "Navigate"
   - Live screenshot appears showing the website

4. **Start Recording**
   - Click "Start Recording" button
   - Give your flow a name (e.g., "Test Login Flow")

5. **Perform Actions** (directly on the live screenshot)
   - **Click** anywhere on the screenshot -> a popup appears asking to confirm
   - **Type** in text fields -> enter text in the overlay that appears
   - **Scroll** with mouse wheel on the screenshot
   - **Navigate** to new URLs using the address bar

6. **Stop Recording**
   - Click "Stop Recording" when done
   - All actions are saved to the database

7. **View Recorded Flow**
   - Click the "Flows" tab
   - Click a flow card to see all recorded steps
   - Each step shows: action type, selector, coordinates, input text

### Part 2: Replay a Flow

1. **Open Flows Tab**
   - Go to "Flows" tab
   - Select a recorded flow from the list

2. **Inspect Steps** (optional)
   - Expand each tab section to see steps
   - Review selectors and element details

3. **Replay Flow**
   - Click the "Runs" tab
   - Select the recording from dropdown
   - Click "Run" button
   - Watch playback execute each step with live screenshot updates

4. **Monitor Execution**
   - Step counter shows progress (e.g., "Step 3 / 15")
   - Status overlay shows current action type
   - If an error occurs, step details appear in red

5. **Pause / Resume** (during playback)
   - Click "Pause" to pause execution
   - Click "Resume" to continue
   - While paused, you can interact with the page (click elements, type, scroll)

### Part 3: Manage Flows

1. **View Flow Library**
   - Flows tab shows all recordings as cards
   - Each card displays: name, step count, created date, updated date

2. **Delete a Flow**
   - Hover over a flow card
   - Click the trash icon
   - Confirm deletion

3. **Edit Flow Steps** (in Runs tab)
   - Select a flow in the dropdown
   - Modify text inputs (e.g., change password before replay)
   - Toggle "Should Run" to skip/include specific steps
   - Click "Save to DB" to persist changes

---

## Demo Workflow Summary (3-5 Minutes)

```
1. Connect -> 2. Navigate to https://example.com
3. Start Recording -> 4. Click some elements, fill a form
5. Stop Recording -> 6. Go to Flows tab, inspect steps
7. Go to Runs tab -> 8. Replay the flow
9. Watch playback execute each step with validation
```

---

## Features

- **Live browser view** - Real-time JPEG screenshot stream over WebSocket
- **Action recording** - Captures navigate, click, type, scroll, and key actions
- **Multi-tab support** - Follows `target=_blank` links; tab bar in UI
- **Flow library** - Recordings saved to SQLite; browsable in Flows page
- **Smart selectors** - Detects stable element IDs; falls back to semantic XPath
- **Element fingerprinting** - Validates elements during playback (targetMeta)
- **Validation history** - Shows validation results during recording and playback
- **Dark / light mode** - Persisted to localStorage
- **Session lifecycle** - Clear "Session Closed" feedback
- **Optimised scroll** - frontend debounces + accumulates scroll deltas (150 ms); sends one WS message per gesture instead of one per wheel tick

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
        │   ├── flows/          # /flows - recorded flow cards + step detail
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