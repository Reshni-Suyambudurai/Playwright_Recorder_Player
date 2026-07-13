# Player Workflow

> How the playback engine works — from clicking Run to seeing the final result.

---

## 1. High-Level Flow

```
User clicks Run
      │
      ▼
[Frontend] POST /play/start  ──►  [Backend] creates PlaySession  ──►  returns play_session_id
      │
      ▼
[Frontend] opens WebSocket /ws/play/{play_session_id}
      │
      ▼
[Frontend] sends HELLO {clientId, ...}
      │
      ▼
[Backend] registers client, spawns asyncio Task: run_playback()
      │
      ├──── For each step ────────────────────────────────────────────────────
      │        │
      │        ├─► send PLAY_STEP_START  →  frontend highlights step in list
      │        │
      │        ├─► execute step (NAVIGATE / CLICK / TYPE / SCROLL / KEY)
      │        │        │
      │        │        ├─ CLICK: check selector → click element (or coords fallback)
      │        │        ├─ TYPE:  check selector → fill field  → press Enter if password
      │        │        └─ NAVIGATE: page.goto(url)
      │        │
      │        ├─► on failure → send PLAY_STEP_ERROR  →  break (stop all steps)
      │        │
      │        ├─► settle page (wait for URL change / networkidle)
      │        │
      │        ├─► take screenshot → send FRAME event
      │        │        └─ frontend: img.src = base64 JPEG  (direct DOM, no Angular zone)
      │        │
      │        └─► if step.pause → send PLAY_PAUSED → wait for PLAY_RESUME
      │
      └──── After last step ───────────────────────────────────────────────────
               │
               ▼
         send PLAY_DONE { stepCount, failedCount, failedSteps }
               │
               ▼
         close browser, detach DomWatcher
```

---

## 2. File Map

### Backend

| File | Role |
|---|---|
| `api/play.py` | REST endpoint `POST /play/start` — creates `PlaySession`, returns `play_session_id`. Also `DELETE /play/{id}` to cancel. |
| `models/playback.py` | `PlaySession` dataclass — holds browser/page/task references, status, pause_event. `PlayStatus` enum (PENDING / RUNNING / PAUSED / DONE / STOPPED / ERROR). |
| `websocket/playback_handler.py` | WebSocket event router for `/ws/play/{id}`. Handles `HELLO` → start task, `PLAY_RESUME` → unblock pause, `PLAY_STOP` → cancel task, `PING` → PONG. |
| `services/playback_service.py` | **Core engine.** `run_playback()` — the asyncio task that iterates steps, sends events, manages settle/screenshot cycle. `_execute_step()` dispatches each step type. |
| `services/browser_service.py` | Playwright wrapper. `launch_browser(headless, viewport)`, `perform_click()`, `perform_type()` (with selector pre-check), `perform_scroll()`, `navigate_to_url()`. |
| `services/screenshot_service.py` | `capture_and_send()` — takes JPEG screenshot (quality 60), base64-encodes it, sends as `FRAME` event via ConnectionManager. |
| `services/dom_watcher.py` | Attached to the page during playback. Fires screenshots automatically on DOM mutations (debounced). Suppressed during active step execution. |
| `websocket/connection_manager.py` | Maps `session_id:client_id` → WebSocket. `send_to_client()` delivers all events. |

### Frontend

| File | Role |
|---|---|
| `pages/runs/runs.ts` | Page component. Signals: `playStatus`, `currentStep`, `totalSteps`, `currentStepId`, `failedCount`, `hasLiveFrame`. Calls `playbackApi.startPlay()` then `connectWs()`. |
| `pages/runs/runs.html` | Template. `<img #frameImg>` always in DOM (hidden via CSS until first frame). Step list with active highlight. Overlays: running / paused / done / done_with_errors / error / stopped. |
| `pages/runs/runs.css` | Player layout styles. `.player-screen` uses `--bg-tertiary` (theme-aware). `.player-live-frame` uses `object-fit: contain`. |
| `services/playback.api.ts` | `startPlay(recordingJson)` → POST. `connectWs(playId, clientId, handlers)` → opens WebSocket, dispatches events to `onMessage(evt)`. |

---

## 3. WebSocket Event Reference

```
Frontend → Backend
──────────────────
HELLO          { clientId }                    starts playback task
PLAY_RESUME    {}                               unblocks a paused step
PLAY_STOP      {}                              cancels the task
PING           {}                               keep-alive

Backend → Frontend
──────────────────
WELCOME        { playId }                       HELLO acknowledged
PLAY_STEP_START  { stepId, index, total, type } step about to execute
PLAY_STEP_SKIPPED { stepId }                    shouldRun=false
PLAY_STEP_ERROR  { stepId, type, error }        step failed → playback stops
PLAY_PAUSED    { stepId, index }                step has pause=true
FRAME          { image, width, height }         JPEG base64 screenshot
PLAY_DONE      { stepCount, failedCount,        all steps finished
                 failedSteps[] }
PLAY_ERROR     { error }                        fatal engine error
```

---

## 4. Step Execution Detail

```
_execute_step(step, page)
      │
      ├─ NAVIGATE  ──►  page.goto(url, domcontentloaded)
      │
      ├─ CLICK
      │      ├─ selector exists?  ──►  element.click()  (accurate)
      │      └─ selector missing  ──►  mouse.click(x, y)  (coords fallback)
      │            └─ coords also fail  ──►  raise → PLAY_STEP_ERROR
      │
      ├─ TYPE
      │      ├─ selector pre-check: query_selector()
      │      │      └─ None  ──►  raise "element not found" → PLAY_STEP_ERROR
      │      ├─ page.fill(selector, text)
      │      └─ isPassword=true  ──►  keyboard.press("Enter")
      │
      ├─ SCROLL  ──►  mouse.move(x,y) + mouse.wheel(dx, dy)
      │
      └─ KEY     ──►  keyboard.press(key)
```

---

## 5. Screenshot Pipeline

```
Playwright headless page
      │
      │  page.screenshot(type=jpeg, quality=60, timeout=5s)
      ▼
raw JPEG bytes  (~30–50 KB)
      │
      │  base64.b64encode()
      ▼
base64 string  (~40–67 KB)
      │
      │  wrapped in { event_type: "FRAME", data: { image: "data:image/jpeg;base64,..." } }
      ▼
WebSocket text frame  →  Browser
      │
      │  requestAnimationFrame callback (throttled, no Angular zone)
      ▼
 img.src = data  (direct DOM write, no change detection)
```

> DomWatcher fires additional FRAME events on DOM mutations (e.g. after navigation),  
> so the preview updates even between explicit step screenshots.

---

## 6. Failure Handling

```
Step throws exception
      │
      ├─► PLAY_STEP_ERROR sent { stepId, type, error }
      ├─► screenshot of failure state sent (FRAME)
      ├─► break — no more steps run
      │
      └─► PLAY_DONE { failedCount: 1, failedSteps: [...] }
                │
                ▼
          Frontend overlay: ⚠ Done — N steps — 1 failed
```

**TYPE selector pre-check** is the primary failure detector for application-level errors  
(e.g. wrong password → login page stays → next TYPE target not found → immediate fail).

---

## 7. Status Flow

```
PENDING  ──► RUNNING ──► DONE
                │
                ├──► PAUSED ──► RUNNING (on PLAY_RESUME)
                │
                ├──► STOPPED  (on PLAY_STOP)
                │
                └──► ERROR    (fatal engine exception)
```
